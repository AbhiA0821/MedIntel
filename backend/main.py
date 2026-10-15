import os
import time
import threading
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from database.connection import get_connection
from database.monitoring_queries import (
    get_live_monitoring_state,
    get_hospital_monitoring_summary,
    get_pipeline_status_metrics,
    update_pipeline_status_metrics,
    get_active_alerts,
    get_alert_history,
    set_live_update_interval,
    get_registered_doctor_devices,
    register_doctor_device,
    deactivate_doctor_device,
    create_doctor_registration_nonce,
    create_patient,
    update_patient,
    delete_patient,
    get_patient_by_id,
    search_patients
)
from simulator.patient_simulator import generate_and_store_vitals, process_background_alert_pipeline
from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR

app = FastAPI(
    title="MedIntel Live Monitoring API",
    version="1.0.0",
    description="Single-Owner REST API for MedIntel Patient Vital Signs & Clinical Alerts"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# Simulator Lifecycle Manager State
# =====================================================
_simulator_thread = None
_simulator_stop_event = threading.Event()
_simulator_status = "STOPPED"
_simulator_running = False
_simulator_lock = threading.Lock()


def _background_simulator_worker():
    global _simulator_running, _simulator_status, _simulator_thread
    print("[SIMULATOR MANAGER] Background simulator thread started.", flush=True)
    con = get_connection()
    try:
        cycle_count = 1
        while not _simulator_stop_event.is_set():
            from database.monitoring_queries import get_live_update_interval
            interval = get_live_update_interval(con=con)
            t0 = time.monotonic()

            new_ids = generate_and_store_vitals()
            process_background_alert_pipeline(con=con)
            cycle_dur = time.monotonic() - t0

            update_pipeline_status_metrics(status="RUNNING", cycle_duration=cycle_dur, con=con)
            print(f"[SIMULATOR MANAGER] Cycle {cycle_count}: Generated {len(new_ids)} vitals in {cycle_dur:.3f}s", flush=True)

            remaining = max(0.1, interval - cycle_dur)
            step = 0.2
            slept = 0.0
            while slept < remaining and not _simulator_stop_event.is_set():
                time.sleep(min(step, remaining - slept))
                slept += step
            cycle_count += 1
    except Exception as e:
        print(f"[SIMULATOR MANAGER ERROR] Worker loop crashed: {e}", flush=True)
    finally:
        _simulator_running = False
        _simulator_status = "STOPPED"
        _simulator_thread = None
        update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0, con=con)
        con.close()
        print("[SIMULATOR MANAGER] Background simulator thread stopped.", flush=True)


def _start_simulator_worker():
    """Starts exactly ONE simulator background thread if stopped."""
    global _simulator_thread, _simulator_running, _simulator_status
    with _simulator_lock:
        if _simulator_running or (_simulator_thread is not None and _simulator_thread.is_alive()):
            return False, "Simulator is already running."
        _simulator_stop_event.clear()
        _simulator_running = True
        _simulator_status = "RUNNING"
        _simulator_thread = threading.Thread(target=_background_simulator_worker, daemon=True)
        _simulator_thread.start()
        return True, "Simulator started successfully."


def _stop_simulator_worker():
    """Stops the running simulator cleanly."""
    global _simulator_thread, _simulator_running, _simulator_status
    with _simulator_lock:
        if not _simulator_running and (_simulator_thread is None or not _simulator_thread.is_alive()):
            _simulator_status = "STOPPED"
            _simulator_thread = None
            update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0)
            return False, "Simulator is already stopped."
        _simulator_stop_event.set()
        if _simulator_thread is not None:
            _simulator_thread.join(timeout=6.0)
            _simulator_thread = None
        _simulator_running = False
        _simulator_status = "STOPPED"
        update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0)
        return True, "Simulator stopped successfully."


@app.on_event("startup")
def on_startup():
    """Verify database readiness and start background patient telemetry if configured."""
    global _simulator_running, _simulator_status

    # 1. Database readiness verification and safe initialization
    try:
        from database.connection import get_connection, get_db_path
        from database.setup_database import init_database
        from scripts.seed_demo_population import seed_demo_population
        from scripts.seed_oauth_users import sync_users

        current_db_path = get_db_path()
        if not current_db_path.exists():
            print(f"[STARTUP] Database file {current_db_path} does not exist. Initializing schema...", flush=True)
            init_database(current_db_path)
            seed_demo_population(force=False)
            sync_users()

        con = get_connection()
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        required_tables = {"Patients", "VitalSigns", "AlertHistory", "AuthorizedDoctors"}
        if not required_tables.issubset(set(tables)):
            print("[STARTUP] Required tables missing. Initializing schema...", flush=True)
            init_database(current_db_path)
            seed_demo_population(force=False)
            sync_users()
        else:
            p_count = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
            if p_count == 0:
                print("[STARTUP] Database schema exists but Patients table is empty. Seeding initial population...", flush=True)
                seed_demo_population(force=False)
                sync_users()
    except Exception as e:
        print(f"[STARTUP CRITICAL] Database initialization failed: {e}", flush=True)
        raise RuntimeError(f"Database readiness verification failed on startup: {e}") from e

    # 2. Configurable Auto-Start Simulator
    auto_start = os.getenv("AUTO_START_SIMULATOR", "false").lower() in ("true", "1", "yes")
    standalone_runner = os.getenv("MEDINTEL_STANDALONE_SIMULATOR", "false").lower() in ("true", "1", "yes")

    if auto_start and not standalone_runner:
        started, msg = _start_simulator_worker()
        print(f"[STARTUP] In-process simulator auto-start: {msg}", flush=True)
    else:
        _simulator_running = False
        _simulator_status = "STOPPED"
        try:
            update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0)
        except Exception:
            pass
        if standalone_runner:
            print("[STARTUP] In-process simulator auto-start bypassed (managed by standalone runner).", flush=True)
        else:
            print("[STARTUP] In-process simulator auto-start disabled (AUTO_START_SIMULATOR!=true).", flush=True)


@app.on_event("shutdown")
def on_shutdown():
    """Graceful simulator shutdown on server termination."""
    _stop_simulator_worker()
    print("[SHUTDOWN] MedIntel background workers terminated cleanly.", flush=True)



class IntervalUpdateRequest(BaseModel):
    interval_seconds: int


class DoctorAuthRequest(BaseModel):
    email: str
    password: str | None = None
    firebase_uid: str | None = None


class RegisterDeviceRequest(BaseModel):
    device_id: str
    doctor_id: str
    doctor_name: str | None = None
    specialty: str | None = None
    fcm_token: str
    firebase_uid: str | None = None


class DeactivateDeviceRequest(BaseModel):
    fcm_token: str


class CreateNonceRequest(BaseModel):
    doctor_id: str


class PatientCreateRequest(BaseModel):
    first_name: str
    last_name: str
    age: int
    gender: str
    ward: str
    room_no: str = "201"
    bed_no: str = "1"
    blood_group: str = "O+"
    specialty: str = "GENERAL MEDICINE"
    assigned_doctor_id: str | None = None
    patient_id: int | None = None


class PatientUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    age: int | None = None
    gender: str | None = None
    ward: str | None = None
    room_no: str | None = None
    bed_no: str | None = None
    blood_group: str | None = None
    specialty: str | None = None
    assigned_doctor_id: str | None = None


@app.get("/")
def read_root():
    return {
        "service": "MedIntel Live Monitoring API",
        "status": "ONLINE",
        "docs": "/docs"
    }


@app.get("/health")
@app.get("/api/v1/health")
def health_check_endpoint():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": "MedIntel API",
        "version": "2.0.0"
    }


@app.get("/api/v1/patients")
def get_patients_endpoint(doctor_id: str | None = None, specialty: str | None = None):
    """Returns all monitored patients, filtered by doctor specialty when requested."""
    try:
        return get_live_vitals_endpoint(doctor_id=doctor_id, specialty=specialty)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patients/search")
def search_patients_endpoint(query: str):
    """Searches patients by Patient ID or Name."""
    try:
        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Search query parameter is required.")
        matches = search_patients(query.strip())
        return {
            "query": query,
            "count": len(matches),
            "matches": matches
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/critical_patients")
@app.get("/api/v1/patients/critical")
def get_critical_patients_endpoint(doctor_id: str | None = None, specialty: str | None = None):
    """Returns all currently critical patients, filtered by doctor specialty when requested."""
    try:
        from database.monitoring_queries import get_critical_patients
        from services.severity_engine import classify_severity
        from services.reason_detection import get_patient_reasons
        from services.recommendation_engine import get_recommendations
        from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR

        if not doctor_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required: 'doctor_id' parameter must be provided to access critical patient records."
            )

        doc_clean = str(doctor_id).strip().upper()
        if doc_clean not in AUTHORITATIVE_DOCTORS:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: Identity '{doctor_id}' is not authorized."
            )

        auth_doc = AUTHORITATIVE_DOCTORS[doc_clean]
        if auth_doc.get("role") == "DOCTOR":
            specialty = auth_doc.get("specialty")
        elif auth_doc.get("role") == "RECEPTIONIST" or doc_clean == "REC001":
            specialty = None

        raw_patients = get_critical_patients(doctor_id=doc_clean, specialty=specialty)
        critical_list = []
        for p in raw_patients:
            sev = classify_severity(p)
            if sev == "CRITICAL":
                p_spec = (p[16] if len(p) > 16 else "GENERAL MEDICINE").upper()
                p_doc_id = p[17] if len(p) > 17 else None
                doc_info = AUTHORITATIVE_DOCTORS.get(p_doc_id) if p_doc_id else None
                if not doc_info:
                    doc_info = SPECIALTY_TO_DOCTOR.get(p_spec, AUTHORITATIVE_DOCTORS.get("DOC003"))

                critical_list.append({
                    "patient_id": f"P{p[0]}",
                    "pid_raw": p[0],
                    "name": f"{p[1]} {p[2]}",
                    "heart_rate": p[3],
                    "spo2": p[4],
                    "temperature": p[5],
                    "systolic_bp": p[6],
                    "diastolic_bp": p[7],
                    "respiratory_rate": p[8],
                    "ward": p[9],
                    "room_no": p[10],
                    "bed_no": p[11],
                    "age": p[12] if len(p) > 12 else 45,
                    "gender": p[13] if len(p) > 13 else "Male",
                    "severity": "CRITICAL",
                    "reasons": get_patient_reasons(p),
                    "recommendations": get_recommendations(p),
                    "specialty": doc_info.get("specialty", p_spec),
                    "assigned_doctor_id": doc_info.get("doctor_id", "DOC003"),
                    "assigned_doctor_name": doc_info.get("doctor_name", "Dr. Shreya Sutar"),
                    "assigned_doctor_specialty": doc_info.get("specialty", p_spec),
                    "assigned_doctor": doc_info.get("doctor_name", "Dr. Shreya Sutar")
                })
        return {
            "status": "SUCCESS",
            "count": len(critical_list),
            "critical_patients": critical_list
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patients/{patient_id}")
def get_patient_endpoint(patient_id: str, doctor_id: str | None = None):
    """Retrieves single patient details with backend-enforced doctor specialty authorization."""
    try:
        if str(patient_id).strip().lower() in ["critical", "search"]:
            raise HTTPException(status_code=404, detail=f"Invalid patient ID: {patient_id}")
        p = get_patient_by_id(patient_id)
        if not p:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found.")

        # Backend-enforced specialty authorization
        if not doctor_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required: 'doctor_id' parameter must be provided."
            )

        from services.alert_router import AUTHORITATIVE_DOCTORS
        doc_clean = str(doctor_id).strip().upper()
        if doc_clean not in AUTHORITATIVE_DOCTORS:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: Identity '{doctor_id}' is not authorized."
            )

        doc_info = AUTHORITATIVE_DOCTORS[doc_clean]
        if doc_info.get("role") == "DOCTOR":
            doc_specialty = doc_info.get("specialty", "").upper()
            p_specialty = p.get("specialty", "").upper()
            if doc_specialty and p_specialty and doc_specialty != p_specialty:
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: Patient {patient_id} ({p_specialty}) is not under authorized care of {doc_info['doctor_name']} ({doc_specialty})."
                )

        return {
            "status": "SUCCESS",
            "patient": p
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/patients")
def create_patient_endpoint(req: PatientCreateRequest):
    """Creates a new patient record in DuckDB database."""
    try:
        if not req.first_name or not req.first_name.strip():
            raise HTTPException(status_code=400, detail="Patient first name is required.")
        if not req.last_name or not req.last_name.strip():
            raise HTTPException(status_code=400, detail="Patient last name is required.")
        if req.age < 0 or req.age > 120:
            raise HTTPException(status_code=400, detail="Age must be between 0 and 120.")
        if not req.ward or not req.ward.strip():
            raise HTTPException(status_code=400, detail="Ward is required.")

        res = create_patient(
            first_name=req.first_name.strip(),
            last_name=req.last_name.strip(),
            age=req.age,
            gender=req.gender.strip(),
            ward=req.ward.strip(),
            room_no=req.room_no.strip(),
            bed_no=req.bed_no.strip(),
            blood_group=req.blood_group.strip(),
            specialty=req.specialty.strip(),
            assigned_doctor_id=req.assigned_doctor_id.strip() if req.assigned_doctor_id else None,
            patient_id=req.patient_id
        )
        return {
            "status": "SUCCESS",
            "message": "Patient added successfully.",
            "patient_id": f"{res['patient_id']}",
            "pid_raw": res['pid_raw'],
            "patient": res
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/patients/{patient_id}")
def update_patient_endpoint(patient_id: str, req: PatientUpdateRequest):
    """Updates an existing patient record while preserving doctor/specialty consistency."""
    try:
        clean_id = int(str(patient_id).upper().replace("P", ""))
        res = update_patient(
            patient_id=clean_id,
            first_name=req.first_name.strip() if req.first_name else None,
            last_name=req.last_name.strip() if req.last_name else None,
            age=req.age,
            gender=req.gender.strip() if req.gender else None,
            blood_group=req.blood_group.strip() if req.blood_group else None,
            ward=req.ward.strip() if req.ward else None,
            room_no=req.room_no.strip() if req.room_no else None,
            bed_no=req.bed_no.strip() if req.bed_no else None,
            specialty=req.specialty.strip() if req.specialty else None,
            assigned_doctor_id=req.assigned_doctor_id.strip() if req.assigned_doctor_id else None
        )
        return {
            "status": "SUCCESS",
            "message": "Patient updated successfully.",
            "patient": res
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/patients/{patient_id}")
def delete_patient_endpoint(patient_id: str):
    """Deletes a patient record from DuckDB database."""
    try:
        clean_id = int(str(patient_id).upper().replace("P", ""))
        delete_patient(clean_id)
        return {
            "status": "SUCCESS",
            "message": f"Patient P{clean_id} deleted successfully.",
            "patient_id": f"P{clean_id}"
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/simulator/status")
def get_simulator_status_endpoint():
    """Returns simulator running state, PID, and update interval."""
    metrics = get_pipeline_status_metrics()
    return {
        "status": _simulator_status,
        "running": _simulator_running,
        "pid": os.getpid() if _simulator_running else None,
        "update_interval": metrics.get("update_interval", 3),
        "last_cycle_duration": metrics.get("last_cycle_duration", 0.0)
    }


@app.post("/api/v1/simulator/start")
def start_simulator_endpoint():
    """Starts exactly ONE simulator process/thread if stopped."""
    started, message = _start_simulator_worker()
    return {
        "status": "RUNNING",
        "message": message,
        "pid": os.getpid()
    }


@app.post("/api/v1/simulator/stop")
def stop_simulator_endpoint():
    """Stops the running simulator cleanly."""
    stopped, message = _stop_simulator_worker()
    return {
        "status": "STOPPED",
        "message": message
    }


@app.get("/api/v1/hospital/summary")
@app.get("/api/v1/monitoring/summary")
def get_hospital_summary_endpoint(doctor_id: str | None = None):
    """Returns authoritative summary statistics. If doctor_id is provided, includes scoped assignment counts alongside hospital summary."""
    try:
        from database.monitoring_queries import get_hospital_monitoring_summary, get_live_monitoring_state
        from services.alert_router import AUTHORITATIVE_DOCTORS
        hospital_summary = get_hospital_monitoring_summary()

        assigned_summary = None
        if doctor_id:
            doc_clean = str(doctor_id).strip().upper()
            if doc_clean == "REC001":
                # Receptionist gets complete hospital-wide active metrics
                assigned_summary = {
                    "doctor_id": "REC001",
                    "doctor_name": "Reception Desk",
                    "role": "RECEPTIONIST",
                    "specialty": "HOSPITAL ADMISSIONS",
                    "total_assigned": hospital_summary.get("total_patients", 102),
                    "critical_count": hospital_summary.get("critical_count", 0),
                    "moderate_count": hospital_summary.get("moderate_count", 0),
                    "low_count": hospital_summary.get("low_count", 0),
                    "active_alerts_count": hospital_summary.get("active_alerts_count", 0)
                }
            elif doc_clean in AUTHORITATIVE_DOCTORS:
                auth_doc = AUTHORITATIVE_DOCTORS[doc_clean]
                doc_spec = auth_doc.get("specialty", "GENERAL MEDICINE")
                doc_state = get_live_monitoring_state(doctor_id=doc_clean, specialty=doc_spec)
                assigned_summary = {
                    "doctor_id": doc_clean,
                    "doctor_name": auth_doc.get("doctor_name", f"Doctor {doc_clean}"),
                    "role": auth_doc.get("role", "DOCTOR"),
                    "specialty": doc_spec,
                    "total_assigned": doc_state.get("total_patients", 0),
                    "critical_count": doc_state.get("critical_count", 0),
                    "moderate_count": doc_state.get("moderate_count", 0),
                    "low_count": doc_state.get("low_count", 0),
                    "active_alerts_count": doc_state.get("critical_count", 0)
                }

        return {
            "status": "SUCCESS",
            "hospital_summary": hospital_summary,
            "assigned_summary": assigned_summary,
            "total_patients": hospital_summary.get("total_patients", 102),
            "critical_count": assigned_summary.get("critical_count") if assigned_summary else hospital_summary.get("critical_count", 0),
            "moderate_count": assigned_summary.get("moderate_count") if assigned_summary else hospital_summary.get("moderate_count", 0),
            "low_count": assigned_summary.get("low_count") if assigned_summary else hospital_summary.get("low_count", 0),
            "active_alerts_count": assigned_summary.get("active_alerts_count") if assigned_summary else hospital_summary.get("active_alerts_count", 0),
            "total_assigned": assigned_summary.get("total_assigned") if assigned_summary else hospital_summary.get("total_patients", 102)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/live_vitals")
@app.get("/api/v1/monitoring/vitals")
def get_live_vitals_endpoint(doctor_id: str | None = None, specialty: str | None = None):
    """Returns the latest vitals, severities, trends, and clinical reasons for active patients, filtered by doctor specialty when requested."""
    try:
        from services.alert_router import AUTHORITATIVE_DOCTORS
        if doctor_id:
            doc_clean = str(doctor_id).strip().upper()
            if doc_clean in AUTHORITATIVE_DOCTORS:
                auth_doc = AUTHORITATIVE_DOCTORS[doc_clean]
                if auth_doc.get("role") == "DOCTOR":
                    # Server-side authoritative: enforce doctor specialty, overriding client tampering
                    specialty = auth_doc.get("specialty")

        state = get_live_monitoring_state(doctor_id=doctor_id, specialty=specialty)
        return {
            "status": "SUCCESS",
            "total_patients": state["total_patients"],
            "total_vitals_count": state["total_vitals_count"],
            "critical_count": state["critical_count"],
            "moderate_count": state["moderate_count"],
            "low_count": state["low_count"],
            "hospital_summary": state.get("hospital_summary", {}),
            "latest_db_update": state["latest_db_update"],
            "patients": [
                {
                    "patient_id": f"P{p[0]}",
                    "pid_raw": p[0],
                    "name": f"{p[1]} {p[2]}",
                    "heart_rate": p[3],
                    "spo2": p[4],
                    "temperature": p[5],
                    "systolic_bp": p[6],
                    "diastolic_bp": p[7],
                    "respiratory_rate": p[8],
                    "ward": p[9],
                    "room_no": p[10],
                    "bed_no": p[11],
                    "age": p[12] if len(p) > 12 else 45,
                    "gender": p[13] if len(p) > 13 else "Male",
                    "severity": state["patient_severities"].get(p[0], "LOW"),
                    "trend": state["patient_trends"].get(p[0], "STABLE"),
                    "reasons": state["patient_reasons"].get(p[0], []),
                    "recommendation": (state["patient_recommendations"].get(p[0]) or ["Routine monitoring"])[0],
                    "assigned_specialty": state["patient_routings"].get(p[0], {}).get("specialty", "GENERAL MEDICINE"),
                    "assigned_doctor_id": state["patient_routings"].get(p[0], {}).get("assigned_doctor_id", "DOC003"),
                    "assigned_doctor_name": state["patient_routings"].get(p[0], {}).get("assigned_doctor_name") or state["patient_routings"].get(p[0], {}).get("assigned_doctor") or state["patient_routings"].get(p[0], {}).get("doctor_name", "Dr. Shreya Sutar"),
                    "assigned_doctor_specialty": state["patient_routings"].get(p[0], {}).get("assigned_doctor_specialty") or state["patient_routings"].get(p[0], {}).get("specialty", "GENERAL MEDICINE"),
                    "assigned_doctor": state["patient_routings"].get(p[0], {}).get("assigned_doctor_name") or state["patient_routings"].get(p[0], {}).get("assigned_doctor") or state["patient_routings"].get(p[0], {}).get("doctor_name", "Dr. Shreya Sutar")
                }
                for p in state["patients"]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/v1/pipeline_status")
def get_pipeline_status_endpoint():
    """Returns real-time pipeline status metrics."""
    try:
        metrics = get_pipeline_status_metrics()
        return {
            "status": "SUCCESS",
            "metrics": metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/alerts/active")
def get_active_alerts_endpoint(doctor_id: str | None = None, specialty: str | None = None):
    """Returns currently active critical alerts, filtered by doctor specialty when requested."""
    try:
        if not doctor_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required: 'doctor_id' parameter must be provided to access active alerts."
            )

        doc_clean = str(doctor_id).strip().upper()
        if doc_clean not in AUTHORITATIVE_DOCTORS:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: Identity '{doctor_id}' is not authorized."
            )

        auth_doc = AUTHORITATIVE_DOCTORS[doc_clean]
        if auth_doc.get("role") == "DOCTOR":
            specialty = auth_doc.get("specialty")
        elif auth_doc.get("role") == "RECEPTIONIST" or doc_clean == "REC001":
            specialty = None

        from services.voice.alert_voice import build_concise_spoken_text
        raw_alerts = get_active_alerts(doctor_id=doc_clean, specialty=specialty)
        formatted = []
        for a in raw_alerts:
            if isinstance(a, (list, tuple)):
                p_name = a[17] if len(a) > 17 and a[17] else f"Patient P{a[1]}"
                v_text = build_concise_spoken_text({
                    "patient_id": a[1],
                    "patient_name": p_name,
                    "ward": a[6],
                    "room_no": str(a[7]) if a[7] is not None else "",
                    "bed_no": str(a[8]) if a[8] is not None else "",
                    "severity": a[2]
                })
                formatted.append({
                    "alert_id": a[0],
                    "patient_id": f"P{a[1]}" if a[1] is not None and not str(a[1]).startswith("P") else str(a[1]),
                    "pid_raw": int(str(a[1]).replace("P", "")) if a[1] is not None else 0,
                    "patient_name": p_name,
                    "severity": a[2],
                    "reason": a[3],
                    "recommendation": a[4],
                    "priority": a[5],
                    "ward": a[6],
                    "room_no": str(a[7]) if a[7] is not None else "",
                    "bed_no": str(a[8]) if a[8] is not None else "",
                    "specialty": a[9],
                    "assigned_doctor": a[10],
                    "created_at": str(a[11]) if a[11] else None,
                    "notification_status": a[12] if len(a) > 12 else None,
                    "acknowledged": a[13] if len(a) > 13 else False,
                    "active": a[16] if len(a) > 16 else True,
                    "voice_text": v_text
                })
            elif isinstance(a, dict):
                formatted.append(a)
        return {
            "status": "SUCCESS",
            "active_alerts_count": len(formatted),
            "alerts": formatted
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/alerts/history")
def get_alert_history_endpoint(limit: int = 50, doctor_id: str | None = None, specialty: str | None = None):
    """Returns recent alert history log, filtered by doctor specialty when requested."""
    try:
        from services.alert_router import AUTHORITATIVE_DOCTORS
        if doctor_id:
            doc_clean = str(doctor_id).strip().upper()
            if doc_clean in AUTHORITATIVE_DOCTORS:
                auth_doc = AUTHORITATIVE_DOCTORS[doc_clean]
                if auth_doc.get("role") == "DOCTOR":
                    specialty = auth_doc.get("specialty")

        history = get_alert_history(limit=limit, doctor_id=doctor_id, specialty=specialty)
        return {
            "status": "SUCCESS",
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/update_interval")
def update_interval_endpoint(req: IntervalUpdateRequest):
    """Updates the global live update interval (1, 3, 5, 10 seconds)."""
    try:
        if req.interval_seconds < 1 or req.interval_seconds > 60:
            raise HTTPException(status_code=400, detail="Interval must be between 1 and 60 seconds.")
        set_live_update_interval(req.interval_seconds)
        return {
            "status": "SUCCESS",
            "message": f"Live update interval set to {req.interval_seconds} seconds.",
            "interval_seconds": req.interval_seconds
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/trigger_cycle")
def trigger_cycle_endpoint():
    """Triggers one background vital generation + alert processing cycle."""
    try:
        from simulator.simulator_runner import run_simulation_cycle
        new_ids, dur = run_simulation_cycle()
        return {
            "status": "SUCCESS",
            "generated_vitals_count": len(new_ids),
            "cycle_duration_seconds": round(dur, 3)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class GoogleAuthorizeRequest(BaseModel):
    email: str
    email_verified: bool = True


@app.post("/api/v1/auth/google_authorize")
def google_authorize_endpoint(req: GoogleAuthorizeRequest):
    """
    Authorizes a verified Google email against the authoritative MedIntel user registry.
    Returns 403 Forbidden if the email is not in the registry or email is unverified.
    """
    if not req.email_verified:
        raise HTTPException(status_code=403, detail="Unverified Google email identities cannot access MedIntel.")

    from services.alert_router import authorize_google_user
    user = authorize_google_user(req.email)
    if not user:
        raise HTTPException(status_code=403, detail=f"Access denied: Google account '{req.email}' is not authorized for MedIntel.")

    return {
        "status": "SUCCESS",
        "authorized": True,
        "user": user
    }


@app.post("/api/v1/auth/login")
def doctor_login_endpoint(req: DoctorAuthRequest):
    """Authenticates doctor or staff against AuthorizedDoctors database within the single-owner API process."""
    try:
        con = get_connection()
        try:
            email_clean = req.email.strip().lower()
            row = con.execute("""
                SELECT doctor_id, doctor_name, email, firebase_uid, specialty, role, active
                FROM AuthorizedDoctors
                WHERE (LOWER(email) = ? OR LOWER(doctor_id) = ?) AND active = TRUE;
            """, [email_clean, email_clean]).fetchone()

            if not row:
                from services.alert_router import authorize_google_user, AUTHORITATIVE_DOCTORS
                auth_user = authorize_google_user(email_clean)
                if not auth_user and email_clean.upper() in AUTHORITATIVE_DOCTORS:
                    auth_user = AUTHORITATIVE_DOCTORS[email_clean.upper()]
                if auth_user:
                    row = (
                        auth_user["doctor_id"],
                        auth_user["doctor_name"],
                        auth_user["email"],
                        f"FB-{auth_user['doctor_id']}",
                        auth_user["specialty"],
                        auth_user["role"],
                        True
                    )
                else:
                    raise HTTPException(status_code=404, detail=f"Doctor/Staff account '{req.email}' not found or inactive in database.")

            db_doc_id, db_name, db_email, db_fb_uid, db_specialty, db_role, db_active = row

            if not db_active:
                raise HTTPException(status_code=403, detail="Account is inactive.")

            # Clinical access PINs / passwords for authorized medical and reception staff:
            DOC_PINS = {
                "DOC001": ["1025", "viraj123", "medintel123"],
                "DOC002": ["4912", "smarath123", "medintel123"],
                "DOC003": ["1503", "shreya123", "medintel123"],
                "REC001": ["0821", "rec123", "medintel123"]
            }
            valid_pins = DOC_PINS.get(db_doc_id, ["medintel123"])
            if req.password:
                if str(req.password).strip() not in valid_pins:
                    raise HTTPException(status_code=401, detail="Authentication failed: Invalid doctor password or clinical PIN.")
            elif not req.firebase_uid:
                raise HTTPException(status_code=401, detail="Authentication failed: Doctor password or clinical PIN is required.")

            if req.firebase_uid and db_fb_uid and db_fb_uid != req.firebase_uid:
                raise HTTPException(status_code=401, detail=f"Identity Verification Failed: Firebase UID '{req.firebase_uid}' does not match authorized record.")

            doctor_info = {
                "doctor_id": db_doc_id,
                "doctor_name": db_name,
                "email": db_email,
                "firebase_uid": req.firebase_uid or db_fb_uid,
                "specialty": db_specialty,
                "role": db_role
            }
            return {
                "status": "SUCCESS",
                "message": "Authenticated successfully.",
                "doctor_info": doctor_info
            }
        finally:
            con.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/auth/devices")
def get_doctor_devices_endpoint(doctor_id: str = None):
    """Retrieves active registered devices for doctor within API process."""
    try:
        devs = get_registered_doctor_devices(doctor_id=doctor_id)
        return {
            "status": "SUCCESS",
            "devices": devs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/auth/deactivate_device")
def deactivate_doctor_device_endpoint(req: DeactivateDeviceRequest):
    """Deactivates a doctor device FCM token within API process."""
    try:
        deactivate_doctor_device(req.fcm_token)
        return {
            "status": "SUCCESS",
            "message": "Device deactivated successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/auth/test_push")
def send_test_push_endpoint(doctor_id: str = "DOC001"):
    """Sends diagnostic FCM test push to doctor's active device within API process."""
    try:
        from services.notification_service import send_test_notification_to_doctor
        res = send_test_notification_to_doctor(doctor_id=doctor_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/auth/register_device")
def register_doctor_device_endpoint(req: RegisterDeviceRequest):
    """Registers or updates a doctor's mobile device for FCM notifications."""
    try:
        con = get_connection()
        try:
            # Validate doctor belongs to AuthorizedDoctors
            row = con.execute("""
                SELECT doctor_id, doctor_name, specialty, role, active
                FROM AuthorizedDoctors
                WHERE doctor_id = ? AND active = TRUE;
            """, [req.doctor_id]).fetchone()

            if not row:
                default_docs = {
                    "DOC001": ("DOC001", "Dr. Viraj Patil", "CARDIOLOGY", "DOCTOR", True),
                    "DOC002": ("DOC002", "Dr. Smarath Pawar", "PULMONOLOGY", "DOCTOR", True),
                    "DOC003": ("DOC003", "Dr. Shreya Sutar", "GENERAL MEDICINE", "DOCTOR", True),
                    "REC001": ("REC001", "Reception Desk", "HOSPITAL ADMISSIONS", "RECEPTIONIST", True)
                }
                if req.doctor_id in default_docs:
                    row = default_docs[req.doctor_id]
                else:
                    raise HTTPException(status_code=403, detail=f"Staff ID '{req.doctor_id}' is unauthorized or inactive.")

            doc_id, doc_name, specialty, role, active = row
            # Enforce authoritative doctor name and specialty from authoritative registry
            doctor_name = doc_name
            specialty_val = specialty

            res = register_doctor_device(
                device_id=req.device_id,
                doctor_id=doc_id,
                doctor_name=doctor_name,
                specialty=specialty_val,
                fcm_token=req.fcm_token,
                firebase_uid=req.firebase_uid,
                con=con
            )

            # Idempotently dispatch any active critical alerts assigned to this doctor that missed dispatch
            reconciled_alerts = []
            try:
                from database.monitoring_queries import get_active_alerts
                from services.alert_router import route_alert
                active_alerts = get_active_alerts(doctor_id=doc_id, con=con)
                for a in active_alerts:
                    # a[12] is notification_status
                    notif_status = a[12] if len(a) > 12 else None
                    if notif_status in [None, "NO_ACTIVE_DEVICES", "PENDING", "FAILED"]:
                        p_name = a[17] if len(a) > 17 and a[17] else f"Patient P{a[1]}"
                        alert_item = {
                            "alert_id": a[0],
                            "patient_id": a[1],
                            "patient_name": p_name,
                            "severity": a[2],
                            "reason": a[3],
                            "recommendation": a[4],
                            "priority": a[5],
                            "ward": a[6],
                            "room_no": str(a[7]) if a[7] is not None else "201",
                            "bed_no": str(a[8]) if a[8] is not None else "1",
                            "specialty": a[9],
                            "assigned_doctor": a[10]
                        }
                        route_res = route_alert(alert_item, ward=a[6])
                        new_status = route_res.get("notification_status", "SENT_TO_ON_CALL")
                        con.execute("UPDATE AlertHistory SET notification_status = ? WHERE alert_id = ?", [new_status, a[0]])
                        reconciled_alerts.append(a[0])
            except Exception as recon_err:
                pass

            return {
                "status": "SUCCESS",
                "message": "Device registered successfully.",
                "reconciled_alerts_dispatched": len(reconciled_alerts),
                "device": {
                    "device_id": res["device_id"],
                    "doctor_id": res["doctor_id"],
                    "doctor_name": res["doctor_name"],
                    "specialty": res["specialty"],
                    "registered_at": res["registered_at"],
                    "active": res["active"]
                }
            }
        finally:
            con.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/alerts/voice/{alert_id}.wav")
def get_alert_voice_wav(alert_id: str):
    """Serves the generated Piper TTS / system audio WAV for the specified alert."""
    from pathlib import Path
    alerts_dir = Path(__file__).resolve().parent.parent / "static" / "audio" / "alerts"
    audio_file = alerts_dir / f"{alert_id}.wav"

    if not audio_file.exists():
        # Check destination-prefixed names e.g. cardiology_ALT-P101.wav
        matches = list(alerts_dir.glob(f"*_{alert_id}.wav"))
        if matches:
            audio_file = matches[0]

    if not audio_file.exists():
        try:
            from services.voice.alert_voice import trigger_workstation_voice_alert
            from database.monitoring_queries import get_active_alerts
            active = get_active_alerts()
            clean_id = alert_id
            for prefix in ["cardiology_", "pulmonology_", "general_medicine_", "receptionist_"]:
                if clean_id.lower().startswith(prefix):
                    clean_id = clean_id[len(prefix):]
            match = next((a for a in active if a.get("alert_id") in [alert_id, clean_id]), None)
            if match:
                trigger_workstation_voice_alert(match)
                if (alerts_dir / f"{alert_id}.wav").exists():
                    audio_file = alerts_dir / f"{alert_id}.wav"
                else:
                    matches = list(alerts_dir.glob(f"*_{alert_id}.wav"))
                    if matches:
                        audio_file = matches[0]
        except Exception:
            pass

    if audio_file.exists():
        return FileResponse(path=str(audio_file), media_type="audio/wav")
    raise HTTPException(status_code=404, detail=f"Audio alert not found for {alert_id}")


@app.get("/api/v1/alerts/voice/latest")
def get_latest_voice_alert_endpoint(destination: str | None = None):
    """Returns the most recent workstation voice alert payload for the requested destination."""
    try:
        from services.voice.alert_voice import get_latest_voice_alert
        latest = get_latest_voice_alert(destination=destination)
        return {
            "status": "SUCCESS",
            "voice_alert": latest
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/alerts/voice/queue")
def get_voice_queue_endpoint(destination: str | None = None, specialty: str | None = None, doctor_id: str | None = None):
    """Returns the real-time serialized queue of voice alerts for the requested destination."""
    try:
        from services.voice.alert_voice import get_voice_queue
        dest = destination or specialty or doctor_id
        queue_info = get_voice_queue(destination=dest)
        return queue_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VoiceStatusUpdateRequest(BaseModel):
    destination: str | None = None
    alert_id: str
    status: str  # "SPEAKING" | "COMPLETED"


@app.post("/api/v1/alerts/voice/status")
def update_voice_alert_status_endpoint(req: VoiceStatusUpdateRequest):
    """Updates the real-time playback status ('SPEAKING' or 'COMPLETED') of an alert."""
    try:
        from services.voice.alert_voice import update_voice_alert_status
        updated_queue = update_voice_alert_status(
            destination=req.destination,
            alert_id=req.alert_id,
            status=req.status
        )
        return {
            "status": "SUCCESS",
            "queue": updated_queue
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/api/v1/alerts/voice/test", methods=["GET", "POST"])
def test_voice_alert_endpoint():
    """Generates and serves a harmless test audio phrase without modifying patient data."""
    try:
        from services.voice.piper_tts import synthesize_speech
        test_text = "MedIntel voice alert system is operational. Workstation audio active."
        test_id = "ALT-TEST-VOICE"
        audio_url = synthesize_speech(test_text, test_id)
        return {
            "status": "SUCCESS",
            "voice_alert": {
                "alert_id": test_id,
                "spoken_text": test_text,
                "audio_url": f"/api/v1/alerts/voice/{test_id}.wav",
                "timestamp": time.time()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CriticalAlertTriggerRequest(BaseModel):
    patient_id: int
    severity: str = "CRITICAL"
    reason: str = "Abnormal Vitals"
    recommendation: str = "Immediate clinical review"
    priority: str = "HIGH"
    ward: str = "ICU"
    room_no: str = "201"
    bed_no: str = "1"
    specialty: str = "GENERAL MEDICINE"
    assigned_doctor: str = "Dr. Amit Verma"


@app.post("/api/v1/alerts/trigger")
def trigger_critical_alert_endpoint(req: CriticalAlertTriggerRequest):
    """Triggers and records a critical alert within the single-owner API process."""
    try:
        from datetime import datetime
        from database.connection import get_connection
        from database.monitoring_queries import record_or_update_critical_alert
        con = get_connection()
        if req.severity == "CRITICAL":
            max_vid = con.execute("SELECT COALESCE(MAX(vital_id), 0) FROM VitalSigns").fetchone()[0]
            con.execute("""
                INSERT INTO VitalSigns (vital_id, patient_id, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, [max_vid + 1, req.patient_id, 135, 87, 39.1, 165, 95, 26, datetime.now()])

        aid = record_or_update_critical_alert(
            patient_id=req.patient_id,
            severity=req.severity,
            reason=req.reason,
            recommendation=req.recommendation,
            priority=req.priority,
            ward=req.ward,
            room_no=req.room_no,
            bed_no=req.bed_no,
            specialty=req.specialty,
            assigned_doctor=req.assigned_doctor,
            con=con
        )
        return {
            "status": "SUCCESS",
            "alert_id": aid
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", 8000)))
    uvicorn.run(app, host=host, port=port)

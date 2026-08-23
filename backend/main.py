import os
import time
import threading
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database.connection import get_connection
from database.monitoring_queries import (
    get_live_monitoring_state,
    get_pipeline_status_metrics,
    update_pipeline_status_metrics,
    get_active_alerts,
    get_alert_history,
    set_live_update_interval,
    get_registered_doctor_devices,
    deactivate_doctor_device,
    create_doctor_registration_nonce,
    create_patient,
    delete_patient,
    search_patients
)
from simulator.patient_simulator import generate_and_store_vitals, process_background_alert_pipeline

app = FastAPI(
    title="MedIntel Live Monitoring API",
    version="1.0.0",
    description="Single-Owner REST API for MedIntel Patient Vital Signs & Clinical Alerts"
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
    global _simulator_running, _simulator_status
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
        update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0, con=con)
        con.close()
        print("[SIMULATOR MANAGER] Background simulator thread stopped.", flush=True)


@app.on_event("startup")
def on_startup():
    """Ensure initial simulator state is strictly STOPPED."""
    global _simulator_running, _simulator_status
    _simulator_running = False
    _simulator_status = "STOPPED"
    try:
        update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0)
    except Exception:
        pass


class IntervalUpdateRequest(BaseModel):
    interval_seconds: int


class DoctorAuthRequest(BaseModel):
    email: str
    password: str | None = None
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
    patient_id: int | None = None


@app.get("/")
def read_root():
    return {
        "service": "MedIntel Live Monitoring API",
        "status": "ONLINE",
        "docs": "/docs"
    }


@app.get("/health")
def health_check_endpoint():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": "MedIntel API",
        "version": "2.0.0"
    }


@app.get("/api/v1/patients")
def get_patients_endpoint():
    """Returns all monitored patients."""
    try:
        return get_live_vitals_endpoint()
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
            patient_id=req.patient_id
        )
        return {
            "status": "SUCCESS",
            "message": "Patient added successfully.",
            "patient_id": f"P{res['patient_id']}",
            "pid_raw": res['patient_id'],
            "patient": res
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
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
    global _simulator_thread, _simulator_running, _simulator_status
    with _simulator_lock:
        if _simulator_running or (_simulator_thread is not None and _simulator_thread.is_alive()):
            return {
                "status": "RUNNING",
                "message": "Simulator is already running.",
                "pid": os.getpid()
            }

        _simulator_stop_event.clear()
        _simulator_running = True
        _simulator_status = "RUNNING"
        _simulator_thread = threading.Thread(target=_background_simulator_worker, daemon=True)
        _simulator_thread.start()

        return {
            "status": "RUNNING",
            "message": "Simulator started successfully.",
            "pid": os.getpid()
        }


@app.post("/api/v1/simulator/stop")
def stop_simulator_endpoint():
    """Stops the running simulator cleanly."""
    global _simulator_thread, _simulator_running, _simulator_status
    with _simulator_lock:
        if not _simulator_running and (_simulator_thread is None or not _simulator_thread.is_alive()):
            _simulator_status = "STOPPED"
            update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0)
            return {
                "status": "STOPPED",
                "message": "Simulator is already stopped."
            }

        _simulator_stop_event.set()
        if _simulator_thread is not None:
            _simulator_thread.join(timeout=3.0)

        _simulator_running = False
        _simulator_status = "STOPPED"
        update_pipeline_status_metrics(status="STOPPED", cycle_duration=0.0)

        return {
            "status": "STOPPED",
            "message": "Simulator stopped successfully."
        }


@app.get("/api/v1/live_vitals")
def get_live_vitals_endpoint():
    """Returns the latest vitals, severities, trends, and clinical reasons for all active patients."""
    try:
        state = get_live_monitoring_state()
        return {
            "status": "SUCCESS",
            "total_patients": state["total_patients"],
            "total_vitals_count": state["total_vitals_count"],
            "critical_count": state["critical_count"],
            "moderate_count": state["moderate_count"],
            "low_count": state["low_count"],
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
                    "assigned_doctor": state["patient_routings"].get(p[0], {}).get("assigned_doctor", "Dr. Amit Verma")
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
def get_active_alerts_endpoint():
    """Returns currently active critical alerts."""
    try:
        alerts = get_active_alerts()
        return {
            "status": "SUCCESS",
            "active_alerts_count": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/alerts/history")
def get_alert_history_endpoint():
    """Returns recent alert history log."""
    try:
        history = get_alert_history()
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


@app.post("/api/v1/auth/login")
def doctor_login_endpoint(req: DoctorAuthRequest):
    """Authenticates doctor against AuthorizedDoctors database within the single-owner API process."""
    try:
        con = get_connection()
        try:
            email_clean = req.email.strip().lower()
            row = con.execute("""
                SELECT doctor_id, doctor_name, email, firebase_uid, specialty, role, active
                FROM AuthorizedDoctors
                WHERE LOWER(email) = ? AND active = TRUE AND role = 'DOCTOR';
            """, [email_clean]).fetchone()

            if not row:
                default_docs = {
                    "dr.rahul@medintel.org": ("DOC001", "Dr. Rahul Sharma", "dr.rahul@medintel.org", "FB-DOC001", "CARDIOLOGY", "DOCTOR", True),
                    "dr.priya@medintel.org": ("DOC002", "Dr. Priya Patel", "dr.priya@medintel.org", "FB-DOC002", "NEUROLOGY", "DOCTOR", True),
                    "dr.amit@medintel.org": ("DOC003", "Dr. Amit Verma", "dr.amit@medintel.org", "FB-DOC003", "GENERAL MEDICINE", "DOCTOR", True),
                    "doctor.amit@medintel.io": ("DOC003", "Dr. Amit Verma", "doctor.amit@medintel.io", "FB-DOC003", "GENERAL MEDICINE", "DOCTOR", True)
                }
                if email_clean in default_docs:
                    row = default_docs[email_clean]
                else:
                    raise HTTPException(status_code=404, detail=f"Doctor account '{req.email}' not found or inactive in database.")

            db_doc_id, db_name, db_email, db_fb_uid, db_specialty, db_role, db_active = row

            if not db_active:
                raise HTTPException(status_code=403, detail="Doctor account is inactive.")

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
                "message": "Doctor authenticated successfully.",
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


@app.post("/api/v1/auth/create_nonce")
def create_doctor_nonce_endpoint(req: CreateNonceRequest):
    """Generates single-use registration nonce within API process."""
    try:
        nonce = create_doctor_registration_nonce(req.doctor_id)
        return {
            "status": "SUCCESS",
            "nonce": nonce
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

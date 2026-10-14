import sys
import os
from pathlib import Path

# Ensure project root is on sys.path for robust module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime
from database.connection import get_connection

try:
    from services.llm.llm_gateway import generate_clinical_explanation
except ImportError:
    generate_clinical_explanation = None



def get_critical_patients(con=None, doctor_id=None, specialty=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        from services.alert_router import AUTHORITATIVE_DOCTORS
        target_specialty = None
        if doctor_id:
            doc_clean = str(doctor_id).strip().upper()
            if doc_clean == "REC001":
                target_specialty = None
            elif doc_clean in AUTHORITATIVE_DOCTORS:
                doc = AUTHORITATIVE_DOCTORS[doc_clean]
                if doc.get("role") == "DOCTOR":
                    target_specialty = doc.get("specialty")
            else:
                from services.alert_router import AUTHORITATIVE_USERS_BY_EMAIL
                u = AUTHORITATIVE_USERS_BY_EMAIL.get(str(doctor_id).strip().lower())
                if u and u.get("role") == "DOCTOR":
                    target_specialty = u.get("specialty")
        if not target_specialty and specialty:
            spec_clean = str(specialty).strip().upper()
            if spec_clean not in ["HOSPITAL ADMISSIONS", "RECEPTIONIST", "ALL", "NONE", ""]:
                target_specialty = spec_clean

        if target_specialty:
            query = """
            SELECT
                p.patient_id,
                p.first_name,
                p.last_name,
                v.heart_rate,
                v.spo2,
                v.temperature,
                v.systolic_bp,
                v.diastolic_bp,
                v.respiratory_rate,
                p.ward,
                COALESCE(p.room_no, '201') as room_no,
                COALESCE(p.bed_no, '1') as bed_no,
                p.age,
                p.gender,
                p.blood_group,
                v.recorded_at,
                COALESCE(p.specialty, 'GENERAL MEDICINE') as specialty,
                p.assigned_doctor_id
            FROM Patients p
            INNER JOIN (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
                FROM VitalSigns
            ) v ON p.patient_id = v.patient_id AND v.rn = 1
            WHERE UPPER(COALESCE(p.specialty, 'GENERAL MEDICINE')) = UPPER(?)
            ORDER BY p.patient_id;
            """
            return con.execute(query, [target_specialty]).fetchall()
        else:
            query = """
            SELECT
                p.patient_id,
                p.first_name,
                p.last_name,
                v.heart_rate,
                v.spo2,
                v.temperature,
                v.systolic_bp,
                v.diastolic_bp,
                v.respiratory_rate,
                p.ward,
                COALESCE(p.room_no, '201') as room_no,
                COALESCE(p.bed_no, '1') as bed_no,
                p.age,
                p.gender,
                p.blood_group,
                v.recorded_at,
                COALESCE(p.specialty, 'GENERAL MEDICINE') as specialty,
                p.assigned_doctor_id
            FROM Patients p
            INNER JOIN (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
                FROM VitalSigns
            ) v ON p.patient_id = v.patient_id AND v.rn = 1
            ORDER BY p.patient_id;
            """
            return con.execute(query).fetchall()
    finally:
        if close_con:
            con.close()


def get_all_monitored_patients(con=None, doctor_id=None, specialty=None):
    return get_critical_patients(con=con, doctor_id=doctor_id, specialty=specialty)


def get_patient_vital_history(patient_id, limit=20, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        query = """
        SELECT vital_id, patient_id, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate, recorded_at
        FROM VitalSigns
        WHERE patient_id = ?
        ORDER BY recorded_at DESC, vital_id DESC
        LIMIT ?;
        """
        return con.execute(query, [patient_id, limit]).fetchall()
    finally:
        if close_con:
            con.close()


def get_patient_by_id(patient_id, con=None):
    """Retrieves full details and latest vitals for a single patient with authoritative doctor resolution."""
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        clean_id = int(str(patient_id).upper().replace("P", ""))
        query = """
        SELECT
            p.patient_id,
            p.first_name,
            p.last_name,
            v.heart_rate,
            v.spo2,
            v.temperature,
            v.systolic_bp,
            v.diastolic_bp,
            v.respiratory_rate,
            p.ward,
            COALESCE(p.room_no, '201') as room_no,
            COALESCE(p.bed_no, '1') as bed_no,
            p.age,
            p.gender,
            p.blood_group,
            v.recorded_at,
            COALESCE(p.specialty, 'GENERAL MEDICINE') as specialty,
            p.assigned_doctor_id,
            p.admission_date
        FROM Patients p
        LEFT JOIN (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
            FROM VitalSigns
        ) v ON p.patient_id = v.patient_id AND v.rn = 1
        WHERE p.patient_id = ?;
        """
        row = con.execute(query, [clean_id]).fetchone()
        if not row:
            return None

        specialty_val = (row[16] or "GENERAL MEDICINE").upper()
        doc_id = row[17]

        from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR
        doc_info = AUTHORITATIVE_DOCTORS.get(doc_id) if doc_id else None
        if not doc_info:
            doc_info = SPECIALTY_TO_DOCTOR.get(specialty_val)
        if not doc_info:
            doc_info = AUTHORITATIVE_DOCTORS.get("DOC003", {
                "doctor_id": "DOC003",
                "doctor_name": "Dr. Shreya Sutar",
                "specialty": "GENERAL MEDICINE"
            })

        doc_name = doc_info.get("doctor_name", "Dr. Shreya Sutar")
        resolved_doc_id = doc_info.get("doctor_id", "DOC003")
        resolved_specialty = doc_info.get("specialty", specialty_val)

        return {
            "patient_id": f"P{row[0]}",
            "pid_raw": row[0],
            "first_name": row[1],
            "last_name": row[2],
            "name": f"{row[1]} {row[2]}",
            "patient_name": f"{row[1]} {row[2]}",
            "heart_rate": row[3] if row[3] is not None else 75,
            "spo2": row[4] if row[4] is not None else 98,
            "temperature": row[5] if row[5] is not None else 36.8,
            "systolic_bp": row[6] if row[6] is not None else 120,
            "diastolic_bp": row[7] if row[7] is not None else 80,
            "respiratory_rate": row[8] if row[8] is not None else 16,
            "ward": row[9],
            "room_no": row[10],
            "bed_no": row[11],
            "age": row[12],
            "gender": row[13],
            "blood_group": row[14],
            "recorded_at": str(row[15]) if row[15] else None,
            "specialty": resolved_specialty,
            "assigned_doctor_id": resolved_doc_id,
            "assigned_doctor_name": doc_name,
            "assigned_doctor_specialty": resolved_specialty,
            "assigned_doctor": doc_name,
            "admission_date": str(row[18]) if row[18] else None
        }
    finally:
        if close_con:
            con.close()



def get_active_alerts(con=None, doctor_id=None, specialty=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        from services.alert_router import AUTHORITATIVE_DOCTORS
        target_specialty = None
        if doctor_id:
            doc_clean = str(doctor_id).strip().upper()
            if doc_clean == "REC001":
                target_specialty = None
            elif doc_clean in AUTHORITATIVE_DOCTORS:
                doc = AUTHORITATIVE_DOCTORS[doc_clean]
                if doc.get("role") == "DOCTOR":
                    target_specialty = doc.get("specialty")
            else:
                from services.alert_router import AUTHORITATIVE_USERS_BY_EMAIL
                u = AUTHORITATIVE_USERS_BY_EMAIL.get(str(doctor_id).strip().lower())
                if u and u.get("role") == "DOCTOR":
                    target_specialty = u.get("specialty")
        if not target_specialty and specialty:
            spec_clean = str(specialty).strip().upper()
            if spec_clean not in ["HOSPITAL ADMISSIONS", "RECEPTIONIST", "ALL", "NONE", ""]:
                target_specialty = spec_clean

        if target_specialty:
            query = """
            SELECT ah.alert_id, ah.patient_id, ah.severity, ah.reason, ah.recommendation, ah.priority, ah.ward, ah.room_no, ah.bed_no, ah.specialty, ah.assigned_doctor, ah.created_at, ah.notification_status, ah.acknowledged, ah.acknowledged_at, ah.resolved_at, ah.active,
                   COALESCE(TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')), 'Patient #' || CAST(ah.patient_id AS VARCHAR)) as patient_name
            FROM AlertHistory ah
            LEFT JOIN Patients p ON ah.patient_id = p.patient_id
            WHERE ah.active = TRUE AND UPPER(ah.specialty) = UPPER(?)
            ORDER BY ah.created_at DESC;
            """
            return con.execute(query, [target_specialty]).fetchall()
        else:
            query = """
            SELECT ah.alert_id, ah.patient_id, ah.severity, ah.reason, ah.recommendation, ah.priority, ah.ward, ah.room_no, ah.bed_no, ah.specialty, ah.assigned_doctor, ah.created_at, ah.notification_status, ah.acknowledged, ah.acknowledged_at, ah.resolved_at, ah.active,
                   COALESCE(TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')), 'Patient #' || CAST(ah.patient_id AS VARCHAR)) as patient_name
            FROM AlertHistory ah
            LEFT JOIN Patients p ON ah.patient_id = p.patient_id
            WHERE ah.active = TRUE
            ORDER BY ah.created_at DESC;
            """
            return con.execute(query).fetchall()
    finally:
        if close_con:
            con.close()


def get_alert_history(limit=50, con=None, doctor_id=None, specialty=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        from services.alert_router import AUTHORITATIVE_DOCTORS
        target_specialty = None
        if doctor_id:
            doc_clean = str(doctor_id).strip().upper()
            if doc_clean == "REC001":
                target_specialty = None
            elif doc_clean in AUTHORITATIVE_DOCTORS:
                doc = AUTHORITATIVE_DOCTORS[doc_clean]
                if doc.get("role") == "DOCTOR":
                    target_specialty = doc.get("specialty")
            else:
                from services.alert_router import AUTHORITATIVE_USERS_BY_EMAIL
                u = AUTHORITATIVE_USERS_BY_EMAIL.get(str(doctor_id).strip().lower())
                if u and u.get("role") == "DOCTOR":
                    target_specialty = u.get("specialty")
        if not target_specialty and specialty:
            spec_clean = str(specialty).strip().upper()
            if spec_clean not in ["HOSPITAL ADMISSIONS", "RECEPTIONIST", "ALL", "NONE", ""]:
                target_specialty = spec_clean

        if target_specialty:
            query = """
            SELECT ah.alert_id, ah.patient_id, ah.severity, ah.reason, ah.recommendation, ah.priority, ah.ward, ah.room_no, ah.bed_no, ah.specialty, ah.assigned_doctor, ah.created_at, ah.notification_status, ah.acknowledged, ah.acknowledged_at, ah.resolved_at, ah.active,
                   COALESCE(TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')), 'Patient #' || CAST(ah.patient_id AS VARCHAR)) as patient_name
            FROM AlertHistory ah
            LEFT JOIN Patients p ON ah.patient_id = p.patient_id
            WHERE UPPER(ah.specialty) = UPPER(?)
            ORDER BY ah.created_at DESC
            LIMIT ?;
            """
            return con.execute(query, [target_specialty, limit]).fetchall()
        else:
            query = """
            SELECT ah.alert_id, ah.patient_id, ah.severity, ah.reason, ah.recommendation, ah.priority, ah.ward, ah.room_no, ah.bed_no, ah.specialty, ah.assigned_doctor, ah.created_at, ah.notification_status, ah.acknowledged, ah.acknowledged_at, ah.resolved_at, ah.active,
                   COALESCE(TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')), 'Patient #' || CAST(ah.patient_id AS VARCHAR)) as patient_name
            FROM AlertHistory ah
            LEFT JOIN Patients p ON ah.patient_id = p.patient_id
            ORDER BY ah.created_at DESC
            LIMIT ?;
            """
            return con.execute(query, [limit]).fetchall()
    finally:
        if close_con:
            con.close()


def acknowledge_alert(alert_id, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        con.execute("""
            UPDATE AlertHistory
            SET acknowledged = TRUE, acknowledged_at = ?
            WHERE alert_id = ?;
        """, [datetime.now(), alert_id])
    finally:
        if close_con:
            con.close()


def resolve_alert(alert_id, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        con.execute("""
            UPDATE AlertHistory
            SET active = FALSE, resolved_at = ?
            WHERE alert_id = ?;
        """, [datetime.now(), alert_id])
    finally:
        if close_con:
            con.close()


def get_registered_doctor_devices(doctor_id=None, specialty=None, doctor_name=None, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        if doctor_id:
            return con.execute("SELECT device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, active FROM DoctorDevices WHERE doctor_id = ? AND active = TRUE;", [doctor_id]).fetchall()
        elif specialty:
            return con.execute("SELECT device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, active FROM DoctorDevices WHERE UPPER(specialty) = UPPER(?) AND active = TRUE;", [specialty]).fetchall()
        elif doctor_name:
            return con.execute("SELECT device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, active FROM DoctorDevices WHERE UPPER(doctor_name) = UPPER(?) AND active = TRUE;", [doctor_name]).fetchall()
        return con.execute("SELECT device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, active FROM DoctorDevices WHERE active = TRUE;").fetchall()
    finally:
        if close_con:
            con.close()


def register_doctor_device(device_id, doctor_id, doctor_name, specialty, fcm_token, firebase_uid=None, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        now_ts = datetime.now()
        con.execute("DELETE FROM DoctorDevices WHERE device_id = ? OR fcm_token = ?;", [device_id, fcm_token])
        con.execute("""
            INSERT INTO DoctorDevices (device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, last_seen_at, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE);
        """, [device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, now_ts, now_ts])
        return {
            "device_id": device_id,
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "specialty": specialty,
            "fcm_token": fcm_token,
            "registered_at": str(now_ts),
            "active": True
        }
    finally:
        if close_con:
            con.close()



def deactivate_doctor_device(fcm_token, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        con.execute("UPDATE DoctorDevices SET active = FALSE WHERE fcm_token = ?;", [fcm_token])
    finally:
        if close_con:
            con.close()


def create_doctor_registration_nonce(doctor_id, ttl_minutes=30, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        import uuid
        from datetime import timedelta
        nonce = f"NONCE-{uuid.uuid4().hex[:12].upper()}"
        now_dt = datetime.now()
        exp_dt = now_dt + timedelta(minutes=ttl_minutes)
        con.execute("""
            INSERT INTO PendingRegistrationNonces (nonce, doctor_id, created_at, expires_at, used)
            VALUES (?, ?, ?, ?, FALSE);
        """, [nonce, doctor_id, now_dt, exp_dt])
        return nonce
    finally:
        if close_con:
            con.close()


def get_live_update_interval(con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        val = con.execute("SELECT setting_value FROM SystemSettings WHERE setting_key = 'live_update_interval';").fetchone()
        return int(val[0]) if val else 3
    except Exception:
        return 3
    finally:
        if close_con:
            con.close()


def set_live_update_interval(interval_seconds, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        con.execute("""
            INSERT INTO SystemSettings (setting_key, setting_value, updated_at)
            VALUES ('live_update_interval', ?, ?)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;
        """, [str(interval_seconds), datetime.now()])
    finally:
        if close_con:
            con.close()


def update_pipeline_status_metrics(status="RUNNING", cycle_duration=0.0, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        now_dt = datetime.now()
        dur_str = f"{cycle_duration:.3f}"
        con.execute("""
            INSERT INTO SystemSettings (setting_key, setting_value, updated_at)
            VALUES ('simulator_status', ?, ?)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;
        """, [status, now_dt])
        con.execute("""
            INSERT INTO SystemSettings (setting_key, setting_value, updated_at)
            VALUES ('last_cycle_duration', ?, ?)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;
        """, [dur_str, now_dt])
        con.execute("""
            INSERT INTO SystemSettings (setting_key, setting_value, updated_at)
            VALUES ('last_pipeline_heartbeat', ?, ?)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;
        """, [now_dt.isoformat(), now_dt])
    finally:
        if close_con:
            con.close()


def get_pipeline_status_metrics(con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True

    try:
        rows = con.execute("SELECT setting_key, setting_value FROM SystemSettings").fetchall()
        settings = dict(rows) if rows else {}

        interval = int(settings.get("live_update_interval", 3))
        status = settings.get("simulator_status", "IDLE")
        cycle_dur = float(settings.get("last_cycle_duration", 0.0))
        heartbeat = settings.get("last_pipeline_heartbeat")

        if status == "RUNNING":
            if cycle_dur > interval:
                pipeline_health = "⚠️ PIPELINE SLOW"
            else:
                pipeline_health = "HEALTHY"
        else:
            pipeline_health = "IDLE"

        total_patients = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
        total_vitals = con.execute("SELECT COUNT(*) FROM VitalSigns").fetchone()[0]
        latest_vital = con.execute("SELECT MAX(recorded_at) FROM VitalSigns").fetchone()[0]

        latest_ts_str = latest_vital.strftime("%H:%M:%S") if latest_vital and hasattr(latest_vital, "strftime") else (str(latest_vital) if latest_vital else datetime.now().strftime("%H:%M:%S"))

        return {
            "simulator_status": status,
            "total_patients": total_patients,
            "total_vitals_count": total_vitals,
            "latest_db_update": latest_ts_str,
            "update_interval": interval,
            "last_cycle_duration": cycle_dur,
            "pipeline_health": pipeline_health,
            "heartbeat": heartbeat
        }
    finally:
        if close_con:
            con.close()


def get_hospital_monitoring_summary(con=None):
    """
    Computes authoritative hospital-wide summary statistics across all wards and specialties:
    - total_patients
    - critical_count
    - moderate_count
    - low_count
    - total_vitals_count
    - active_alerts_count
    - doctors_online (3)
    - latest_db_update
    """
    from services.severity_engine import classify_severity
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        query = """
        SELECT
            p.patient_id,
            p.first_name,
            p.last_name,
            COALESCE(v.heart_rate, 75) as heart_rate,
            COALESCE(v.spo2, 98) as spo2,
            COALESCE(v.temperature, 36.8) as temperature,
            COALESCE(v.systolic_bp, 120) as systolic_bp,
            COALESCE(v.diastolic_bp, 80) as diastolic_bp,
            COALESCE(v.respiratory_rate, 16) as respiratory_rate,
            p.ward,
            COALESCE(p.room_no, '201') as room_no,
            COALESCE(p.bed_no, '1') as bed_no,
            p.age,
            p.gender,
            p.blood_group,
            v.recorded_at,
            COALESCE(p.specialty, 'GENERAL MEDICINE') as specialty
        FROM Patients p
        LEFT JOIN (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
            FROM VitalSigns
        ) v ON p.patient_id = v.patient_id AND v.rn = 1
        ORDER BY p.patient_id;
        """
        rows = con.execute(query).fetchall()
        total_patients = len(rows)

        crit_count = 0
        mod_count = 0
        low_count = 0
        latest_ts = None

        for r in rows:
            sev = classify_severity(r)
            if sev == "CRITICAL":
                crit_count += 1
            elif sev == "MODERATE":
                mod_count += 1
            else:
                low_count += 1
            rec_at = r[15]
            if rec_at and (latest_ts is None or rec_at > latest_ts):
                latest_ts = rec_at

        total_vitals = con.execute("SELECT COUNT(*) FROM VitalSigns").fetchone()[0]
        try:
            active_alerts_cnt = con.execute("SELECT COUNT(*) FROM AlertHistory WHERE active = TRUE").fetchone()[0]
        except Exception:
            active_alerts_cnt = 0

        latest_str = latest_ts.strftime("%H:%M:%S") if latest_ts and hasattr(latest_ts, "strftime") else (str(latest_ts) if latest_ts else datetime.now().strftime("%H:%M:%S"))

        return {
            "total_patients": total_patients,
            "critical_count": crit_count,
            "moderate_count": mod_count,
            "low_count": low_count,
            "total_vitals_count": total_vitals,
            "active_alerts_count": active_alerts_cnt,
            "doctors_online": 3,
            "latest_db_update": latest_str
        }
    finally:
        if close_con:
            con.close()


def get_live_monitoring_state(con=None, doctor_id=None, specialty=None):
    """
    Fast single-pass SQL query to retrieve all active patients, latest vitals,
    previous vitals (for trends), calculated severities, reasons, recommendations,
    and alert metrics. Supports doctor-specific specialty isolation alongside
    authoritative hospital-wide summary metrics.
    """
    from services.severity_engine import classify_severity
    from services.reason_detection import get_patient_reasons
    from services.recommendation_engine import get_recommendations
    try:
        from services.alert_router import SPECIALTY_TO_DOCTOR, SPECIALTY_MAP, WARD_TO_PATIENT_TYPE, AUTHORITATIVE_DOCTORS
    except ImportError:
        SPECIALTY_TO_DOCTOR = {}
        SPECIALTY_MAP = {"GENERAL": {"specialty": "GENERAL MEDICINE", "assigned_doctor": "Dr. Shreya Sutar"}}
        WARD_TO_PATIENT_TYPE = {}
        AUTHORITATIVE_DOCTORS = {}

    target_specialty = None
    if doctor_id:
        doc_clean = str(doctor_id).strip().upper()
        if doc_clean == "REC001":
            target_specialty = None  # Receptionist sees hospital-wide
        elif doc_clean in AUTHORITATIVE_DOCTORS:
            d_info = AUTHORITATIVE_DOCTORS[doc_clean]
            if d_info.get("role") == "DOCTOR":
                target_specialty = d_info.get("specialty")
        else:
            from services.alert_router import AUTHORITATIVE_USERS_BY_EMAIL
            u_info = AUTHORITATIVE_USERS_BY_EMAIL.get(str(doctor_id).strip().lower())
            if u_info and u_info.get("role") == "DOCTOR":
                target_specialty = u_info.get("specialty")

    if not target_specialty and specialty:
        spec_clean = str(specialty).strip().upper()
        if spec_clean not in ["HOSPITAL ADMISSIONS", "RECEPTIONIST", "ALL", "NONE", ""]:
            target_specialty = spec_clean

    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        if target_specialty:
            query = """
            SELECT
                p.patient_id,
                p.first_name,
                p.last_name,
                COALESCE(v.heart_rate, 75) as heart_rate,
                COALESCE(v.spo2, 98) as spo2,
                COALESCE(v.temperature, 36.8) as temperature,
                COALESCE(v.systolic_bp, 120) as systolic_bp,
                COALESCE(v.diastolic_bp, 80) as diastolic_bp,
                COALESCE(v.respiratory_rate, 16) as respiratory_rate,
                p.ward,
                COALESCE(p.room_no, '201') as room_no,
                COALESCE(p.bed_no, '1') as bed_no,
                p.age,
                p.gender,
                p.blood_group,
                v.recorded_at,
                COALESCE(v.rn, 1) as rn,
                COALESCE(p.specialty, 'GENERAL MEDICINE') as specialty,
                p.assigned_doctor_id
            FROM Patients p
            LEFT JOIN (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
                FROM VitalSigns
            ) v ON p.patient_id = v.patient_id AND (v.rn IS NULL OR v.rn <= 2)
            WHERE UPPER(COALESCE(p.specialty, 'GENERAL MEDICINE')) = UPPER(?)
            ORDER BY p.patient_id, v.rn;
            """
            rows = con.execute(query, [target_specialty]).fetchall()
            total_vitals_count = con.execute("""
                SELECT COUNT(*)
                FROM VitalSigns v
                JOIN Patients p ON v.patient_id = p.patient_id
                WHERE UPPER(COALESCE(p.specialty, 'GENERAL MEDICINE')) = UPPER(?);
            """, [target_specialty]).fetchone()[0]
        else:
            query = """
            SELECT
                p.patient_id,
                p.first_name,
                p.last_name,
                COALESCE(v.heart_rate, 75) as heart_rate,
                COALESCE(v.spo2, 98) as spo2,
                COALESCE(v.temperature, 36.8) as temperature,
                COALESCE(v.systolic_bp, 120) as systolic_bp,
                COALESCE(v.diastolic_bp, 80) as diastolic_bp,
                COALESCE(v.respiratory_rate, 16) as respiratory_rate,
                p.ward,
                COALESCE(p.room_no, '201') as room_no,
                COALESCE(p.bed_no, '1') as bed_no,
                p.age,
                p.gender,
                p.blood_group,
                v.recorded_at,
                COALESCE(v.rn, 1) as rn,
                COALESCE(p.specialty, 'GENERAL MEDICINE') as specialty,
                p.assigned_doctor_id
            FROM Patients p
            LEFT JOIN (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
                FROM VitalSigns
            ) v ON p.patient_id = v.patient_id AND (v.rn IS NULL OR v.rn <= 2)
            ORDER BY p.patient_id, v.rn;
            """
            rows = con.execute(query).fetchall()
            total_vitals_count = con.execute("SELECT COUNT(*) FROM VitalSigns").fetchone()[0]

        patient_readings = {}
        for r in rows:
            pid = r[0]
            if pid not in patient_readings:
                patient_readings[pid] = []
            patient_readings[pid].append(r)

        monitored_patients = []
        patient_trends = {}
        patient_severities = {}
        patient_reasons = {}
        patient_recommendations = {}
        patient_routings = {}

        critical_count = 0
        moderate_count = 0
        low_count = 0
        latest_ts = None

        for pid, p_rows in patient_readings.items():
            p_rows.sort(key=lambda x: (x[16] if x[16] is not None else 999))
            curr = p_rows[0]
            p_specialty = curr[17] if len(curr) > 17 and curr[17] else "GENERAL MEDICINE"

            # Specialty Isolation Filter
            if target_specialty and p_specialty.upper() != target_specialty.upper():
                continue

            monitored_patients.append(curr)

            rec_at = curr[15]
            if rec_at and (latest_ts is None or rec_at > latest_ts):
                latest_ts = rec_at

            sev = classify_severity(curr)
            patient_severities[pid] = sev
            if sev == "CRITICAL":
                critical_count += 1
            elif sev == "MODERATE":
                moderate_count += 1
            else:
                low_count += 1

            if len(p_rows) >= 2 and p_rows[1][3] is not None:
                prev = p_rows[1]
                curr_spo2, curr_hr, curr_temp = curr[4], curr[3], curr[5]
                prev_spo2, prev_hr, prev_temp = prev[4], prev[3], prev[5]

                if (curr_spo2 < prev_spo2) or (curr_hr > prev_hr + 4) or (curr_temp > prev_temp + 0.2):
                    trend = "WORSENING"
                elif (curr_spo2 > prev_spo2) or (curr_hr < prev_hr - 4) or (curr_temp < prev_temp - 0.2):
                    trend = "IMPROVING"
                else:
                    trend = "STABLE"
            else:
                trend = "STABLE"

            patient_trends[pid] = trend

            reasons = get_patient_reasons(curr)
            patient_reasons[pid] = reasons

            recs = get_recommendations(curr)
            patient_recommendations[pid] = recs

            # Resolve authoritative doctor assignment
            doc_id = curr[18] if len(curr) > 18 and curr[18] else None
            routing_info = None
            if doc_id and doc_id in AUTHORITATIVE_DOCTORS:
                routing_info = dict(AUTHORITATIVE_DOCTORS[doc_id])
            if not routing_info:
                routing_info = SPECIALTY_TO_DOCTOR.get(p_specialty.upper())
            if not routing_info:
                ward_val = curr[9]
                patient_type = WARD_TO_PATIENT_TYPE.get(ward_val, "GENERAL")
                routing_info = SPECIALTY_MAP.get(
                    patient_type.upper(),
                    SPECIALTY_MAP.get("GENERAL", {"specialty": "GENERAL MEDICINE", "assigned_doctor": "Dr. Shreya Sutar", "doctor_name": "Dr. Shreya Sutar", "doctor_id": "DOC003"})
                )
            routing_info = dict(routing_info)
            resolved_doc_id = routing_info.get("doctor_id") or ("DOC001" if p_specialty == "CARDIOLOGY" else ("DOC002" if p_specialty == "PULMONOLOGY" else "DOC003"))
            resolved_doc_name = routing_info.get("doctor_name") or routing_info.get("assigned_doctor") or ("Dr. Viraj Patil" if resolved_doc_id == "DOC001" else ("Dr. Smarath Pawar" if resolved_doc_id == "DOC002" else "Dr. Shreya Sutar"))
            resolved_spec = routing_info.get("specialty") or p_specialty

            routing_info["doctor_id"] = resolved_doc_id
            routing_info["doctor_name"] = resolved_doc_name
            routing_info["assigned_doctor"] = resolved_doc_name
            routing_info["assigned_doctor_id"] = resolved_doc_id
            routing_info["assigned_doctor_name"] = resolved_doc_name
            routing_info["assigned_doctor_specialty"] = resolved_spec
            routing_info["specialty"] = resolved_spec

            patient_routings[pid] = routing_info

        latest_ts_str = latest_ts.strftime("%H:%M:%S") if latest_ts and hasattr(latest_ts, "strftime") else (str(latest_ts) if latest_ts else datetime.now().strftime("%H:%M:%S"))

        # Compute or attach authoritative hospital-wide summary
        if target_specialty:
            hospital_summary = get_hospital_monitoring_summary(con=con)
        else:
            try:
                active_alerts_cnt = con.execute("SELECT COUNT(*) FROM AlertHistory WHERE active = TRUE").fetchone()[0]
            except Exception:
                active_alerts_cnt = 0

            hospital_summary = {
                "total_patients": len(monitored_patients),
                "critical_count": critical_count,
                "moderate_count": moderate_count,
                "low_count": low_count,
                "total_vitals_count": total_vitals_count,
                "active_alerts_count": active_alerts_cnt,
                "doctors_online": 3,
                "latest_db_update": latest_ts_str
            }

        return {
            "patients": monitored_patients,
            "patient_trends": patient_trends,
            "patient_severities": patient_severities,
            "patient_reasons": patient_reasons,
            "patient_recommendations": patient_recommendations,
            "patient_routings": patient_routings,
            "total_patients": len(monitored_patients),
            "total_vitals_count": total_vitals_count,
            "critical_count": critical_count,
            "moderate_count": moderate_count,
            "low_count": low_count,
            "hospital_summary": hospital_summary,
            "latest_db_update": latest_ts_str,
            "latest_ts": latest_ts
        }
    finally:
        if close_con:
            con.close()


def create_patient(first_name, last_name=None, age=None, gender=None, ward=None, room_no="201", bed_no="1", blood_group="O+", specialty="GENERAL MEDICINE", assigned_doctor_id=None, patient_id=None, con=None):
    if isinstance(first_name, dict):
        d = first_name
        p_name = d.get("patient_name") or f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
        parts = p_name.split(" ", 1)
        fn = d.get("first_name") or (parts[0] if parts and parts[0] else "Patient")
        ln = d.get("last_name") or (parts[1] if len(parts) > 1 else "Doe")
        return create_patient(
            first_name=fn,
            last_name=ln,
            age=d.get("age", 45),
            gender=d.get("gender", "Male"),
            ward=d.get("ward", "General Ward"),
            room_no=d.get("room_no", "201"),
            bed_no=d.get("bed_no", "1"),
            blood_group=d.get("blood_group", "O+"),
            specialty=d.get("specialty", "GENERAL MEDICINE"),
            assigned_doctor_id=d.get("assigned_doctor_id"),
            patient_id=d.get("patient_id"),
            con=con
        )
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR
        doc_info = None
        if assigned_doctor_id:
            clean_doc = str(assigned_doctor_id).strip().upper()
            doc_info = AUTHORITATIVE_DOCTORS.get(clean_doc)
        if not doc_info and specialty:
            clean_spec = str(specialty).strip().upper()
            doc_info = SPECIALTY_TO_DOCTOR.get(clean_spec)
        if not doc_info:
            doc_info = AUTHORITATIVE_DOCTORS.get("DOC003", {
                "doctor_id": "DOC003",
                "doctor_name": "Dr. Shreya Sutar",
                "specialty": "GENERAL MEDICINE"
            })

        assigned_doctor_id = doc_info["doctor_id"]
        assigned_doctor_name = doc_info["doctor_name"]
        specialty = doc_info["specialty"]

        if patient_id is not None:
            pid = int(str(patient_id).replace("P", "").replace("p", ""))
            existing = con.execute("SELECT patient_id FROM Patients WHERE patient_id = ?", [pid]).fetchone()
            if existing:
                raise ValueError(f"Patient ID P{pid} already exists.")
        else:
            max_pid = con.execute("SELECT COALESCE(MAX(patient_id), 100) FROM Patients").fetchone()[0]
            pid = max_pid + 1

        adm_date = datetime.now().date()
        con.execute("""
            INSERT INTO Patients (patient_id, first_name, last_name, age, gender, blood_group, ward, room_no, bed_no, admission_date, specialty, assigned_doctor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [pid, first_name, last_name, age, gender, blood_group, ward, str(room_no), str(bed_no), adm_date, specialty, assigned_doctor_id])

        max_v_id = con.execute("SELECT COALESCE(MAX(vital_id), 0) FROM VitalSigns").fetchone()[0]
        v_id = max_v_id + 1
        now_ts = datetime.now()
        con.execute("""
            INSERT INTO VitalSigns (vital_id, patient_id, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [v_id, pid, 72, 98, 36.8, 120, 80, 16, now_ts])

        return {
            "success": True,
            "patient_id": f"P{pid}",
            "pid_raw": pid,
            "first_name": first_name,
            "last_name": last_name,
            "name": f"{first_name} {last_name}",
            "patient_name": f"{first_name} {last_name}",
            "age": age,
            "gender": gender,
            "blood_group": blood_group,
            "ward": ward,
            "room_no": str(room_no),
            "bed_no": str(bed_no),
            "specialty": specialty,
            "assigned_doctor_id": assigned_doctor_id,
            "assigned_doctor_name": assigned_doctor_name,
            "assigned_doctor_specialty": specialty,
            "assigned_doctor": assigned_doctor_name,
            "admission_date": str(adm_date)
        }
    finally:
        if close_con:
            con.close()


def update_patient(patient_id, first_name=None, last_name=None, age=None, gender=None, blood_group=None, ward=None, room_no=None, bed_no=None, specialty=None, assigned_doctor_id=None, con=None):
    if isinstance(first_name, dict):
        d = first_name
        return update_patient(
            patient_id=patient_id,
            first_name=d.get("first_name"),
            last_name=d.get("last_name"),
            age=d.get("age"),
            gender=d.get("gender"),
            blood_group=d.get("blood_group"),
            ward=d.get("ward"),
            room_no=d.get("room_no"),
            bed_no=d.get("bed_no"),
            specialty=d.get("specialty"),
            assigned_doctor_id=d.get("assigned_doctor_id"),
            con=con
        )
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        clean_id = int(str(patient_id).replace("P", "").replace("p", ""))
        existing = con.execute("SELECT patient_id, first_name, last_name, age, gender, blood_group, ward, room_no, bed_no, admission_date, specialty, assigned_doctor_id FROM Patients WHERE patient_id = ?", [clean_id]).fetchone()
        if not existing:
            raise ValueError(f"Patient P{clean_id} not found.")

        from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR
        cur_first_name = existing[1]
        cur_last_name = existing[2]
        cur_age = existing[3]
        cur_gender = existing[4]
        cur_blood_group = existing[5]
        cur_ward = existing[6]
        cur_room_no = existing[7]
        cur_bed_no = existing[8]
        cur_specialty = existing[10] or "GENERAL MEDICINE"
        cur_doc_id = existing[11]

        new_first_name = first_name if first_name is not None else cur_first_name
        new_last_name = last_name if last_name is not None else cur_last_name
        new_age = age if age is not None else cur_age
        new_gender = gender if gender is not None else cur_gender
        new_blood_group = blood_group if blood_group is not None else cur_blood_group
        new_ward = ward if ward is not None else cur_ward
        new_room_no = str(room_no) if room_no is not None else str(cur_room_no)
        new_bed_no = str(bed_no) if bed_no is not None else str(cur_bed_no)

        doc_info = None
        if assigned_doctor_id:
            clean_doc = str(assigned_doctor_id).strip().upper()
            doc_info = AUTHORITATIVE_DOCTORS.get(clean_doc)
        elif specialty:
            clean_spec = str(specialty).strip().upper()
            doc_info = SPECIALTY_TO_DOCTOR.get(clean_spec)
        elif cur_doc_id:
            doc_info = AUTHORITATIVE_DOCTORS.get(cur_doc_id)

        if not doc_info:
            doc_info = AUTHORITATIVE_DOCTORS.get("DOC003")

        final_doc_id = doc_info["doctor_id"]
        final_doc_name = doc_info["doctor_name"]
        final_specialty = doc_info["specialty"]

        con.execute("""
            UPDATE Patients
            SET first_name = ?, last_name = ?, age = ?, gender = ?, blood_group = ?, ward = ?, room_no = ?, bed_no = ?, specialty = ?, assigned_doctor_id = ?
            WHERE patient_id = ?;
        """, [new_first_name, new_last_name, new_age, new_gender, new_blood_group, new_ward, new_room_no, new_bed_no, final_specialty, final_doc_id, clean_id])

        con.execute("""
            UPDATE AlertHistory
            SET specialty = ?, assigned_doctor = ?, ward = ?, room_no = ?, bed_no = ?
            WHERE patient_id = ? AND active = TRUE;
        """, [final_specialty, final_doc_name, new_ward, new_room_no, new_bed_no, clean_id])

        return {
            "patient_id": f"P{clean_id}",
            "pid_raw": clean_id,
            "first_name": new_first_name,
            "last_name": new_last_name,
            "name": f"{new_first_name} {new_last_name}",
            "patient_name": f"{new_first_name} {new_last_name}",
            "age": new_age,
            "gender": new_gender,
            "blood_group": new_blood_group,
            "ward": new_ward,
            "room_no": new_room_no,
            "bed_no": new_bed_no,
            "specialty": final_specialty,
            "assigned_doctor_id": final_doc_id,
            "assigned_doctor_name": final_doc_name,
            "assigned_doctor_specialty": final_specialty,
            "assigned_doctor": final_doc_name
        }
    finally:
        if close_con:
            con.close()


def delete_patient(patient_id, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        pid = int(str(patient_id).replace("P", "").replace("p", ""))
        existing = con.execute("SELECT patient_id FROM Patients WHERE patient_id = ?", [pid]).fetchone()
        if not existing:
            raise ValueError(f"Patient P{pid} not found.")

        con.execute("DELETE FROM VitalSigns WHERE patient_id = ?", [pid])
        con.execute("DELETE FROM AlertHistory WHERE patient_id = ?", [pid])
        con.execute("DELETE FROM Patients WHERE patient_id = ?", [pid])

        try:
            from services.simulator import PATIENT_VITAL_STATE, PATIENT_CLINICAL_PROFILES, TARGET_CRITICAL_PIDS
            PATIENT_VITAL_STATE.pop(f"P{pid}", None)
            PATIENT_CLINICAL_PROFILES.pop(f"P{pid}", None)
            if f"P{pid}" in TARGET_CRITICAL_PIDS:
                TARGET_CRITICAL_PIDS.remove(f"P{pid}")
        except Exception:
            pass

        return True
    finally:
        if close_con:
            con.close()


def record_or_update_critical_alert(patient_id, severity, reason, recommendation, priority="HIGH", ward="ICU", room_no="201", bed_no="1", specialty="GENERAL MEDICINE", assigned_doctor="Dr. Amit Verma", con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        pid = int(patient_id)
        now_ts = datetime.now()

        existing_alert = con.execute("SELECT alert_id FROM AlertHistory WHERE patient_id = ? AND active = TRUE", [pid]).fetchone()

        if existing_alert:
            alert_id = existing_alert[0]
            con.execute("""
                UPDATE AlertHistory
                SET severity = ?, reason = ?, recommendation = ?, priority = ?, ward = ?, room_no = ?, bed_no = ?, specialty = ?, assigned_doctor = ?, created_at = ?
                WHERE alert_id = ? AND active = TRUE;
            """, [severity, reason, recommendation, priority, ward, str(room_no), str(bed_no), specialty, assigned_doctor, now_ts, alert_id])

            # Check if this active alert had missed delivery (e.g. device was offline or not registered)
            curr_status_row = con.execute("SELECT notification_status FROM AlertHistory WHERE alert_id = ?", [alert_id]).fetchone()
            if curr_status_row and curr_status_row[0] in [None, "NO_ACTIVE_DEVICES", "PENDING", "FAILED"]:
                try:
                    from database.monitoring_queries import get_registered_doctor_devices
                    from services.alert_router import route_alert
                    active_devs = get_registered_doctor_devices(specialty=specialty, con=con)
                    if active_devs:
                        p_row = con.execute("SELECT first_name, last_name, specialty FROM Patients WHERE patient_id = ?", [pid]).fetchone()
                        p_name = f"{p_row[0]} {p_row[1]}" if p_row else f"Patient #{pid}"
                        alert_item = {
                            "alert_id": alert_id,
                            "patient_id": pid,
                            "patient_name": p_name,
                            "severity": severity,
                            "reason": reason,
                            "recommendation": recommendation,
                            "priority": priority,
                            "ward": ward,
                            "room_no": str(room_no),
                            "bed_no": str(bed_no),
                            "specialty": specialty,
                            "assigned_doctor": assigned_doctor,
                        }
                        route_res = route_alert(alert_item, ward=ward)
                        new_st = route_res.get("notification_status", "SENT_TO_ON_CALL") if isinstance(route_res, dict) else "SENT_TO_ON_CALL"
                        con.execute("UPDATE AlertHistory SET notification_status = ? WHERE alert_id = ?", [new_st, alert_id])
                except Exception:
                    pass

            return alert_id
        else:
            alert_id = f"ALT-P{pid}"
            exists = con.execute("SELECT alert_id FROM AlertHistory WHERE alert_id = ?", [alert_id]).fetchone()
            if exists:
                import time
                alert_id = f"ALT-P{pid}-{int(time.time() * 1000)}"
                while con.execute("SELECT alert_id FROM AlertHistory WHERE alert_id = ?", [alert_id]).fetchone():
                    import uuid
                    alert_id = f"ALT-P{pid}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}"

            con.execute("""
                INSERT INTO AlertHistory (alert_id, patient_id, severity, reason, recommendation, priority, ward, room_no, bed_no, specialty, assigned_doctor, created_at, notification_status, acknowledged, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', FALSE, TRUE);
            """, [alert_id, pid, severity, reason, recommendation, priority, ward, str(room_no), str(bed_no), specialty, assigned_doctor, now_ts])

            # Trigger downstream Agent 3 alert routing (Voice + FCM) IMMEDIATELY with ZERO delay
            notif_status_result = "SENT"
            try:
                p_row = con.execute("SELECT first_name, last_name, specialty FROM Patients WHERE patient_id = ?", [pid]).fetchone()
                p_name = f"{p_row[0]} {p_row[1]}" if p_row else f"Patient #{pid}"
                if p_row and len(p_row) > 2 and p_row[2]:
                    specialty = p_row[2]

                crit_vital = None
                crit_val = None
                v_recent = con.execute("""
                    SELECT heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate
                    FROM VitalSigns WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 1
                """, [pid]).fetchone()
                if v_recent:
                    hr, spo2, temp, sbp, dbp, rr = v_recent
                    if spo2 and spo2 < 90:
                        crit_vital = "oxygen_saturation"
                        crit_val = f"{spo2}"
                    elif temp and temp > 38.5:
                        crit_vital = "body_temperature"
                        crit_val = f"{temp}"
                    elif hr and (hr > 120 or hr < 50):
                        crit_vital = "heart_rate"
                        crit_val = f"{hr}"
                    elif sbp and (sbp > 160 or sbp < 90):
                        crit_vital = "systolic_blood_pressure"
                        crit_val = f"{sbp}"

                alert_item = {
                    "alert_id": alert_id,
                    "patient_id": pid,
                    "patient_name": p_name,
                    "severity": severity,
                    "reason": reason,
                    "recommendation": recommendation,
                    "priority": priority,
                    "ward": ward,
                    "room_no": str(room_no),
                    "bed_no": str(bed_no),
                    "specialty": specialty,
                    "assigned_doctor": assigned_doctor,
                    "critical_vital": crit_vital,
                    "vital_value": crit_val
                }

                from services.alert_router import route_alert
                route_res = route_alert(alert_item, ward=ward)
                if isinstance(route_res, dict):
                    notif_status_result = route_res.get("notification_status", "SENT_TO_ON_CALL")
                con.execute("UPDATE AlertHistory SET notification_status = ? WHERE alert_id = ?", [notif_status_result, alert_id])
            except Exception as route_err:
                import logging
                logging.getLogger("MedIntelAlertEngine").error(f"Downstream alert routing failed for {alert_id}: {route_err}")
                con.execute("UPDATE AlertHistory SET notification_status = 'FAILED' WHERE alert_id = ?", [alert_id])

            # Non-blocking / secondary LLM & RAG Explanation enrichment if available (never delays voice alert)
            if generate_clinical_explanation:
                try:
                    v_row = con.execute("""
                        SELECT heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate
                        FROM VitalSigns WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 1
                    """, [pid]).fetchone()
                    if v_row:
                        p_dict = {
                            "patient_id": f"P{pid}",
                            "heart_rate": v_row[0],
                            "spo2": v_row[1],
                            "temperature": v_row[2],
                            "systolic_bp": v_row[3],
                            "diastolic_bp": v_row[4],
                            "respiratory_rate": v_row[5],
                            "specialty": specialty,
                            "ward": ward,
                            "room_no": str(room_no),
                            "bed_no": str(bed_no)
                        }
                        abnormalities = [r.strip() for r in reason.split(";") if r.strip()]
                        exp = generate_clinical_explanation(p_dict, severity, abnormalities)
                        if exp:
                            enr_reason = "; ".join(exp["reasons"]) if exp.get("reasons") else exp.get("clinical_summary", reason)
                            enr_rec = exp.get("recommendation", recommendation)
                            enr_prio = exp.get("priority", priority)
                            con.execute("""
                                UPDATE AlertHistory
                                SET reason = ?, recommendation = ?, priority = ?
                                WHERE alert_id = ?;
                            """, [enr_reason, enr_rec, enr_prio, alert_id])
                except Exception as llm_err:
                    pass

            return alert_id
    finally:
        if close_con:
            con.close()


def sync_active_alerts_with_critical_patients(critical_pids, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        crit_set = set(int(pid) for pid in critical_pids)
        active_alerts = con.execute("SELECT alert_id, patient_id FROM AlertHistory WHERE active = TRUE").fetchall()
        for a_id, pid in active_alerts:
            if pid not in crit_set:
                con.execute("UPDATE AlertHistory SET active = FALSE, resolved_at = ? WHERE alert_id = ?", [datetime.now(), a_id])
                try:
                    from services.voice.alert_voice import clear_spoken_alert_cache
                    clear_spoken_alert_cache(a_id)
                except Exception:
                    pass
    finally:
        if close_con:
            con.close()


def search_patients(query, con=None):
    """
    Searches patients by Patient ID (exact/numeric/P-prefixed) or Name (case-insensitive partial match).
    """
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        if not query or not str(query).strip():
            return []

        q_str = str(query).strip()

        clean_id = None
        if q_str.upper().startswith("P") and q_str[1:].isdigit():
            clean_id = int(q_str[1:])
        elif q_str.isdigit():
            clean_id = int(q_str)

        from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR

        def _format_patient_row(p):
            spec = p[10] or "GENERAL MEDICINE"
            doc_id = p[11] if len(p) > 11 else None
            doc_info = AUTHORITATIVE_DOCTORS.get(doc_id) if doc_id else None
            if not doc_info:
                doc_info = SPECIALTY_TO_DOCTOR.get(spec.upper(), AUTHORITATIVE_DOCTORS.get("DOC003"))
            return {
                "patient_id": f"P{p[0]}",
                "pid_raw": p[0],
                "name": f"{p[1]} {p[2]}",
                "first_name": p[1],
                "last_name": p[2],
                "age": p[3],
                "gender": p[4],
                "blood_group": p[5],
                "ward": p[6],
                "room_no": p[7],
                "bed_no": p[8],
                "admission_date": str(p[9]) if p[9] else "",
                "specialty": doc_info["specialty"],
                "assigned_doctor_id": doc_info["doctor_id"],
                "assigned_doctor_name": doc_info["doctor_name"],
                "assigned_doctor_specialty": doc_info["specialty"],
                "assigned_doctor": doc_info["doctor_name"]
            }

        if clean_id is not None:
            res = con.execute("""
                SELECT patient_id, first_name, last_name, age, gender, blood_group, ward, room_no, bed_no, admission_date, COALESCE(specialty, 'GENERAL MEDICINE'), assigned_doctor_id
                FROM Patients
                WHERE patient_id = ?
            """, [clean_id]).fetchall()
            if res:
                return [_format_patient_row(res[0])]

        search_pattern = f"%{q_str.lower()}%"
        res = con.execute("""
            SELECT patient_id, first_name, last_name, age, gender, blood_group, ward, room_no, bed_no, admission_date, COALESCE(specialty, 'GENERAL MEDICINE'), assigned_doctor_id
            FROM Patients
            WHERE LOWER(first_name) LIKE ? OR LOWER(last_name) LIKE ? OR LOWER(first_name || ' ' || last_name) LIKE ?
            ORDER BY patient_id;
        """, [search_pattern, search_pattern, search_pattern]).fetchall()

        return [_format_patient_row(p) for p in res]
    finally:
        if close_con:
            con.close()





import sys
import os
from pathlib import Path

# Ensure project root is on sys.path for robust module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime
from database.connection import get_connection

def get_critical_patients(con=None):
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
            v.recorded_at
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


def get_all_monitored_patients(con=None):
    return get_critical_patients(con=con)


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


def get_active_alerts(con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        query = """
        SELECT alert_id, patient_id, severity, reason, recommendation, priority, ward, room_no, bed_no, specialty, assigned_doctor, created_at, notification_status, acknowledged, acknowledged_at, resolved_at, active
        FROM AlertHistory
        WHERE active = TRUE
        ORDER BY created_at DESC;
        """
        return con.execute(query).fetchall()
    finally:
        if close_con:
            con.close()


def get_alert_history(limit=50, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        query = """
        SELECT alert_id, patient_id, severity, reason, recommendation, priority, ward, room_no, bed_no, specialty, assigned_doctor, created_at, notification_status, acknowledged, acknowledged_at, resolved_at, active
        FROM AlertHistory
        ORDER BY created_at DESC
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


def get_registered_doctor_devices(doctor_id=None, con=None):
    close_con = False
    if con is None:
        con = get_connection()
        close_con = True
    try:
        if doctor_id:
            return con.execute("SELECT device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, active FROM DoctorDevices WHERE doctor_id = ? AND active = TRUE;", [doctor_id]).fetchall()
        return con.execute("SELECT device_id, doctor_id, firebase_uid, doctor_name, specialty, fcm_token, registered_at, active FROM DoctorDevices WHERE active = TRUE;").fetchall()
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


def get_live_monitoring_state(con=None):
    """
    Fast single-pass SQL query to retrieve all active patients, latest vitals,
    previous vitals (for trends), calculated severities, reasons, recommendations,
    and alert metrics.
    """
    from services.severity_engine import classify_severity
    from services.reason_detection import get_patient_reasons
    from services.recommendation_engine import get_recommendations
    try:
        from services.alert_router import SPECIALTY_MAP, WARD_TO_PATIENT_TYPE
    except ImportError:
        SPECIALTY_MAP = {"GENERAL": {"specialty": "GENERAL MEDICINE", "assigned_doctor": "Dr. Amit Verma"}}
        WARD_TO_PATIENT_TYPE = {}

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
            v.rn
        FROM Patients p
        INNER JOIN (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) as rn
            FROM VitalSigns
            WHERE vital_id > (SELECT COALESCE(MAX(vital_id), 0) - 500 FROM VitalSigns)
        ) v ON p.patient_id = v.patient_id AND v.rn <= 2
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
            p_rows.sort(key=lambda x: x[16])
            curr = p_rows[0]
            monitored_patients.append(curr[:16])

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

            if len(p_rows) >= 2:
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

            ward_val = curr[9]
            patient_type = WARD_TO_PATIENT_TYPE.get(ward_val, "GENERAL")
            routing_info = SPECIALTY_MAP.get(patient_type.upper(), SPECIALTY_MAP.get("GENERAL", {"specialty": "GENERAL MEDICINE", "assigned_doctor": "Dr. Amit Verma"}))
            patient_routings[pid] = routing_info

        latest_ts_str = latest_ts.strftime("%H:%M:%S") if latest_ts and hasattr(latest_ts, "strftime") else (str(latest_ts) if latest_ts else datetime.now().strftime("%H:%M:%S"))

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
            "latest_db_update": latest_ts_str,
            "latest_ts": latest_ts
        }
    finally:
        if close_con:
            con.close()

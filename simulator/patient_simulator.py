import os
import sys
import random
import importlib.util
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path for robust module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection

# Dynamic import for local kafka/producer.py to avoid shadowing by site-packages kafka module
try:
    kafka_prod_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kafka", "producer.py"))
    spec = importlib.util.spec_from_file_location("medintel_kafka_producer", kafka_prod_path)
    medintel_kafka_producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(medintel_kafka_producer)
    publish_vitals_batch_to_kafka = medintel_kafka_producer.publish_vitals_batch_to_kafka
except Exception:
    def publish_vitals_batch_to_kafka(batch, topic_name='medintel-vitals', bootstrap_servers=['localhost:9094']):
        return 0

MAX_READINGS_PER_PATIENT = 50


DESIGNATED_CRITICAL_IDS = {101, 102, 103, 104, 105, 106, 107, 108}
PATIENT_VITAL_STATE = {}


def _is_designated_critical(patient_id):
    try:
        clean_id = int(str(patient_id).upper().replace("P", ""))
        return clean_id in DESIGNATED_CRITICAL_IDS
    except (ValueError, TypeError):
        return False


def generate_vitals_for_patient(patient_id):
    """Generates realistic vital sign values with gradual bounded changes and 8 designated critical patients."""
    global PATIENT_VITAL_STATE

    try:
        clean_id = int(str(patient_id).upper().replace("P", ""))
    except (ValueError, TypeError):
        clean_id = patient_id

    is_critical = _is_designated_critical(patient_id)

    if patient_id not in PATIENT_VITAL_STATE:
        if is_critical:
            # Initial critical state for designated patients
            spo2 = random.randint(82, 88)
            temp = round(random.uniform(38.7, 39.4), 1)
            hr = random.randint(115, 145)
            sys_bp = random.randint(155, 185)
            dia_bp = random.randint(95, 110)
            resp = random.randint(25, 34)
        else:
            # Initial normal/moderate state for other patients
            if isinstance(clean_id, int) and clean_id % 5 == 0:
                # Moderate baseline for subset of normal patients
                spo2 = random.randint(92, 95)
                temp = round(random.uniform(37.4, 38.0), 1)
                hr = random.randint(95, 115)
                sys_bp = random.randint(130, 150)
                dia_bp = random.randint(82, 92)
                resp = random.randint(19, 23)
            else:
                # Normal baseline
                spo2 = random.randint(96, 99)
                temp = round(random.uniform(36.6, 37.3), 1)
                hr = random.randint(68, 88)
                sys_bp = random.randint(114, 128)
                dia_bp = random.randint(72, 84)
                resp = random.randint(12, 17)
    else:
        prev_hr, prev_spo2, prev_temp, prev_sys_bp, prev_dia_bp, prev_resp = PATIENT_VITAL_STATE[patient_id]

        if is_critical:
            # Gradual bounded changes for Critical patients (staying strictly Critical)
            spo2 = max(78, min(88, prev_spo2 + random.choice([-1, 0, 1])))
            temp = round(max(38.7, min(40.0, prev_temp + random.choice([-0.1, 0.0, 0.1]))), 1)
            hr = max(110, min(160, prev_hr + random.choice([-2, -1, 0, 1, 2])))
            sys_bp = max(150, min(190, prev_sys_bp + random.choice([-2, -1, 0, 1, 2])))
            dia_bp = max(90, min(115, prev_dia_bp + random.choice([-1, 0, 1])))
            resp = max(24, min(36, prev_resp + random.choice([-1, 0, 1])))
        else:
            # Gradual bounded changes for Non-Critical patients (strictly avoiding Critical thresholds)
            spo2 = max(92, min(100, prev_spo2 + random.choice([-1, 0, 1])))
            temp = round(max(36.3, min(38.2, prev_temp + random.choice([-0.1, 0.0, 0.1]))), 1)
            hr = max(60, min(118, prev_hr + random.choice([-2, -1, 0, 1, 2])))
            sys_bp = max(105, min(155, prev_sys_bp + random.choice([-2, -1, 0, 1, 2])))
            dia_bp = max(65, min(92, prev_dia_bp + random.choice([-1, 0, 1])))
            resp = max(12, min(23, prev_resp + random.choice([-1, 0, 1])))

    PATIENT_VITAL_STATE[patient_id] = (hr, spo2, temp, sys_bp, dia_bp, resp)
    return hr, spo2, temp, sys_bp, dia_bp, resp


def generate_and_store_vitals():
    """Generates 100 vital readings (P101-P200), inserts into DuckDB, and publishes to Kafka."""
    con = get_connection()
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        if "Patients" not in tables or "VitalSigns" not in tables:
            print("[SIMULATOR WARNING] Patients or VitalSigns table missing.")
            return []

        patients = con.execute("SELECT patient_id FROM Patients ORDER BY patient_id;").fetchall()
        if not patients:
            print("[SIMULATOR WARNING] No patients found in database.")
            return []

        current_max_id = con.execute("SELECT COALESCE(MAX(vital_id), 0) FROM VitalSigns").fetchone()[0]
        now = datetime.now()

        batch = []
        new_vital_ids = []

        for idx, (patient_id,) in enumerate(patients):
            vital_id = current_max_id + idx + 1
            hr, spo2, temp, sys_bp, dia_bp, resp = generate_vitals_for_patient(patient_id)
            batch.append((vital_id, patient_id, hr, spo2, temp, sys_bp, dia_bp, resp, now))
            new_vital_ids.append(vital_id)

        con.execute("BEGIN TRANSACTION")
        try:
            con.executemany("""
                INSERT INTO VitalSigns (
                    vital_id, patient_id, heart_rate, spo2, temperature,
                    systolic_bp, diastolic_bp, respiratory_rate, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)

            total_count = con.execute("SELECT COUNT(*) FROM VitalSigns").fetchone()[0]
            if total_count > (MAX_READINGS_PER_PATIENT * len(patients)):
                con.execute(f"""
                    DELETE FROM VitalSigns
                    WHERE vital_id IN (
                        SELECT vital_id
                        FROM (
                            SELECT vital_id,
                                   ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY recorded_at DESC, vital_id DESC) AS row_number
                            FROM VitalSigns
                        )
                        WHERE row_number > {MAX_READINGS_PER_PATIENT}
                    )
                """)

            con.execute("COMMIT")

            publish_vitals_batch_to_kafka(batch, topic_name='medintel-vitals')

        except Exception:
            con.execute("ROLLBACK")
            raise

        print(f"[SIMULATOR] Generated {len(new_vital_ids)} vital readings for {len(patients)} patients.")
        return new_vital_ids

    except Exception as e:
        print(f"[SIMULATOR ERROR] Vital generation failed: {e}")
        raise
    finally:
        con.close()


def process_background_alert_pipeline(con=None):
    """
    Runs Layer 1 Background Pipeline processing:
    Evaluates severity, trend, reason, recommendation, alert lifecycle, and FCM routing
    for all active patients without blocking the Streamlit rendering thread.
    """
    try:
        from database.connection import get_connection
        from database.monitoring_queries import get_all_monitored_patients, get_active_alerts
        from services.severity_engine import classify_severity
        from services.reason_detection import get_patient_reasons
        from services.recommendation_engine import get_recommendations
        try:
            from services.alert_manager import process_patient_alert_lifecycle
        except ImportError:
            def process_patient_alert_lifecycle(*args, **kwargs):
                return {}

        if con is None:
            con = get_connection()

        patients = get_all_monitored_patients(con=con)
        active_alerts = get_active_alerts(con=con)

        active_alert_pids = set(a[1] for a in active_alerts) if active_alerts else set()

        for patient in patients:
            pid = patient[0]
            sev = classify_severity(patient)

            if sev == "CRITICAL" or pid in active_alert_pids:
                fname = patient[1]
                lname = patient[2]
                ward = patient[9]
                room_no = patient[10]
                bed_no = patient[11]

                reasons = get_patient_reasons(patient)
                recommendations = get_recommendations(patient)

                agent_2_item = {
                    "patient_id": pid,
                    "patient_name": f"{fname} {lname}",
                    "severity": sev,
                    "ward": ward,
                    "room_no": room_no,
                    "bed_no": bed_no,
                    "reason": f"Abnormal vitals ({', '.join(reasons)})" if reasons else "Routine monitoring",
                    "recommendation": recommendations[0] if recommendations else "Routine patient monitoring",
                    "grounded_recommendations": recommendations
                }
                location = {"ward": ward, "room_no": room_no, "bed_no": bed_no}
                process_patient_alert_lifecycle(agent_2_item, patient_location=location)

    except Exception as err:
        print(f"[BACKGROUND PIPELINE ERROR] Alert processing exception: {err}")
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


def generate_vitals_for_patient(patient_id):
    """Generates realistic vital sign values based on clinical distributions."""
    r = random.random()

    if r < 0.12:
        # Critical state
        spo2 = random.randint(75, 89)
        temp = round(random.uniform(38.6, 40.5), 1)
        hr = random.randint(110, 160)
        sys_bp = random.randint(155, 195)
        dia_bp = random.randint(95, 115)
        resp = random.randint(25, 38)
    elif r < 0.35:
        # Moderate state
        spo2 = random.randint(90, 94)
        temp = round(random.uniform(37.6, 38.5), 1)
        hr = random.randint(100, 125)
        sys_bp = random.randint(135, 160)
        dia_bp = random.randint(85, 95)
        resp = random.randint(20, 25)
    else:
        # Normal state
        spo2 = random.randint(95, 100)
        temp = round(random.uniform(36.5, 37.5), 1)
        hr = random.randint(60, 95)
        sys_bp = random.randint(110, 130)
        dia_bp = random.randint(70, 85)
        resp = random.randint(12, 18)

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
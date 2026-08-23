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


MAX_READINGS_PER_PATIENT = 50

# Dynamic Simulator Realism State
SIMULATOR_CYCLE_COUNT = 0
TARGET_CRITICAL_PIDS = set()
PATIENT_CLINICAL_PROFILES = {}
PATIENT_STAGE = {}
PATIENT_VITAL_STATE = {}

PROFILES = ['HYPOXIA_FEVER', 'TACHYCARDIIC_HYPOXIA', 'HYPERTENSIVE_FEVER', 'TACHYPNEIC_HYPOXIA', 'COMBINATION']


def _clean_patient_id(pid):
    try:
        return int(str(pid).upper().replace("P", ""))
    except (ValueError, TypeError):
        return pid


def update_simulator_patient_rotation(active_patient_ids):
    """
    Manages dynamic rotation of ~8 critical patients.
    Cycles 1-5: All patients normal/moderate (0 critical).
    Cycle 6+: Pick 8 random active patients to deteriorate.
    Every 6 cycles after cycle 6: Recover 2-4 critical patients, deteriorate 2-4 non-critical patients.
    Purges deleted patient IDs.
    """
    global SIMULATOR_CYCLE_COUNT, TARGET_CRITICAL_PIDS, PATIENT_CLINICAL_PROFILES, PATIENT_STAGE, PATIENT_VITAL_STATE

    SIMULATOR_CYCLE_COUNT += 1
    active_set = set(_clean_patient_id(p) for p in active_patient_ids)

    # Purge deleted patients from state
    for pid in list(PATIENT_VITAL_STATE.keys()):
        if _clean_patient_id(pid) not in active_set:
            PATIENT_VITAL_STATE.pop(pid, None)
            PATIENT_CLINICAL_PROFILES.pop(pid, None)
            PATIENT_STAGE.pop(pid, None)
            TARGET_CRITICAL_PIDS.discard(_clean_patient_id(pid))

    for pid in list(TARGET_CRITICAL_PIDS):
        if pid not in active_set:
            TARGET_CRITICAL_PIDS.remove(pid)

    active_list = sorted(list(active_set))
    if not active_list:
        return

    if SIMULATOR_CYCLE_COUNT <= 5:
        TARGET_CRITICAL_PIDS.clear()
        return

    # Cycle 6 initial population of 8 critical patients
    if not TARGET_CRITICAL_PIDS:
        target_count = min(8, len(active_list))
        selected = set(random.sample(active_list, target_count))
        TARGET_CRITICAL_PIDS = selected
        for pid in selected:
            PATIENT_CLINICAL_PROFILES[pid] = random.choice(PROFILES)
            PATIENT_STAGE[pid] = 1.0
        return

    # Periodic rotation every 6 cycles after cycle 6
    if (SIMULATOR_CYCLE_COUNT - 6) % 6 == 0 and SIMULATOR_CYCLE_COUNT > 6:
        curr_crit = list(TARGET_CRITICAL_PIDS)
        non_crit = [p for p in active_list if p not in TARGET_CRITICAL_PIDS]

        if curr_crit and non_crit:
            rotate_count = min(random.randint(2, 4), len(curr_crit), len(non_crit))
            recover_pids = random.sample(curr_crit, rotate_count)
            deteriorate_pids = random.sample(non_crit, rotate_count)

            for p_rec in recover_pids:
                TARGET_CRITICAL_PIDS.remove(p_rec)
                PATIENT_STAGE[p_rec] = 0.0

            for p_det in deteriorate_pids:
                TARGET_CRITICAL_PIDS.add(p_det)
                PATIENT_CLINICAL_PROFILES[p_det] = random.choice(PROFILES)
                PATIENT_STAGE[p_det] = 1.0


def generate_vitals_for_patient(patient_id):
    """Generates realistic vital sign values with gradual stage transitions and dynamic critical rotation."""
    global PATIENT_VITAL_STATE, PATIENT_STAGE, PATIENT_CLINICAL_PROFILES

    clean_id = _clean_patient_id(patient_id)
    is_target_critical = clean_id in TARGET_CRITICAL_PIDS
    profile = PATIENT_CLINICAL_PROFILES.get(clean_id, 'HYPOXIA_FEVER')

    base_spo2 = random.randint(96, 99)
    base_temp = round(random.uniform(36.6, 37.3), 1)
    base_hr = random.randint(68, 84)
    base_sys_bp = random.randint(114, 126)
    base_dia_bp = random.randint(72, 82)
    base_resp = random.randint(12, 16)

    if profile == 'HYPOXIA_FEVER':
        crit_spo2 = random.randint(82, 86)
        crit_temp = round(random.uniform(38.8, 39.5), 1)
        crit_hr = random.randint(110, 130)
        crit_sys_bp = random.randint(145, 175)
        crit_dia_bp = random.randint(90, 105)
        crit_resp = random.randint(24, 32)
    elif profile == 'TACHYCARDIIC_HYPOXIA':
        crit_spo2 = random.randint(84, 88)
        crit_temp = round(random.uniform(37.4, 38.0), 1)
        crit_hr = random.randint(128, 148)
        crit_sys_bp = random.randint(138, 158)
        crit_dia_bp = random.randint(86, 96)
        crit_resp = random.randint(20, 26)
    elif profile == 'HYPERTENSIVE_FEVER':
        crit_spo2 = random.randint(93, 96)
        crit_temp = round(random.uniform(38.7, 39.4), 1)
        crit_hr = random.randint(98, 118)
        crit_sys_bp = random.randint(168, 188)
        crit_dia_bp = random.randint(102, 114)
        crit_resp = random.randint(18, 24)
    elif profile == 'TACHYPNEIC_HYPOXIA':
        crit_spo2 = random.randint(83, 87)
        crit_temp = round(random.uniform(37.0, 37.7), 1)
        crit_hr = random.randint(106, 122)
        crit_sys_bp = random.randint(135, 155)
        crit_dia_bp = random.randint(84, 94)
        crit_resp = random.randint(29, 36)
    else:  # COMBINATION
        crit_spo2 = random.randint(81, 86)
        crit_temp = round(random.uniform(38.9, 39.6), 1)
        crit_hr = random.randint(130, 152)
        crit_sys_bp = random.randint(160, 185)
        crit_dia_bp = random.randint(98, 112)
        crit_resp = random.randint(26, 35)

    if is_target_critical:
        target_spo2, target_temp, target_hr, target_sys_bp, target_dia_bp, target_resp = (
            crit_spo2, crit_temp, crit_hr, crit_sys_bp, crit_dia_bp, crit_resp
        )
    else:
        target_spo2, target_temp, target_hr, target_sys_bp, target_dia_bp, target_resp = (
            base_spo2, base_temp, base_hr, base_sys_bp, base_dia_bp, base_resp
        )

    if patient_id not in PATIENT_VITAL_STATE:
        hr, spo2, temp, sys_bp, dia_bp, resp = base_hr, base_spo2, base_temp, base_sys_bp, base_dia_bp, base_resp
    else:
        prev_hr, prev_spo2, prev_temp, prev_sys_bp, prev_dia_bp, prev_resp = PATIENT_VITAL_STATE[patient_id]

        # Gradual step changes towards target (2-3 cycles from Normal to Critical or Critical to Normal)
        spo2_diff = target_spo2 - prev_spo2
        spo2_step = 0 if spo2_diff == 0 else (min(4, max(2, abs(spo2_diff))) if spo2_diff > 0 else -min(4, max(2, abs(spo2_diff))))

        temp_diff = round(target_temp - prev_temp, 1)
        temp_step = 0.0 if temp_diff == 0.0 else (min(0.6, max(0.3, abs(temp_diff))) if temp_diff > 0 else -min(0.6, max(0.3, abs(temp_diff))))

        hr_diff = target_hr - prev_hr
        hr_step = 0 if hr_diff == 0 else (min(12, max(4, abs(hr_diff))) if hr_diff > 0 else -min(12, max(4, abs(hr_diff))))

        sys_diff = target_sys_bp - prev_sys_bp
        sys_step = 0 if sys_diff == 0 else (min(12, max(4, abs(sys_diff))) if sys_diff > 0 else -min(12, max(4, abs(sys_diff))))

        dia_diff = target_dia_bp - prev_dia_bp
        dia_step = 0 if dia_diff == 0 else (min(6, max(2, abs(dia_diff))) if dia_diff > 0 else -min(6, max(2, abs(dia_diff))))

        resp_diff = target_resp - prev_resp
        resp_step = 0 if resp_diff == 0 else (min(4, max(2, abs(resp_diff))) if resp_diff > 0 else -min(4, max(2, abs(resp_diff))))

        # Small random variation when at target
        if spo2_step == 0:
            spo2_step = random.choice([-1, 0, 1])
        if temp_step == 0.0:
            temp_step = random.choice([-0.1, 0.0, 0.1])
        if hr_step == 0:
            hr_step = random.choice([-1, 0, 1])

        spo2 = max(75, min(100, prev_spo2 + spo2_step))
        temp = round(max(36.0, min(40.5, prev_temp + temp_step)), 1)
        hr = max(55, min(170, prev_hr + hr_step))
        sys_bp = max(95, min(200, prev_sys_bp + sys_step))
        dia_bp = max(60, min(120, prev_dia_bp + dia_step))
        resp = max(10, min(40, prev_resp + resp_step))

    PATIENT_VITAL_STATE[patient_id] = (hr, spo2, temp, sys_bp, dia_bp, resp)
    return hr, spo2, temp, sys_bp, dia_bp, resp


def generate_and_store_vitals():
    """Generates 100 vital readings, inserts into DuckDB, and publishes to Kafka."""
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

        patient_ids = [p[0] for p in patients]
        update_simulator_patient_rotation(patient_ids)

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
    Evaluates severity, reason, recommendation, deduplicates active alerts, and assigns routing.
    """
    try:
        from database.connection import get_connection
        from database.monitoring_queries import (
            get_all_monitored_patients,
            record_or_update_critical_alert,
            sync_active_alerts_with_critical_patients
        )
        from services.severity_engine import classify_severity
        from services.reason_detection import get_patient_reasons
        from services.recommendation_engine import get_recommendations
        try:
            from services.alert_router import SPECIALTY_MAP, WARD_TO_PATIENT_TYPE
        except ImportError:
            SPECIALTY_MAP = {"GENERAL": {"specialty": "GENERAL MEDICINE", "assigned_doctor": "Dr. Amit Verma"}}
            WARD_TO_PATIENT_TYPE = {}

        if con is None:
            con = get_connection()

        patients = get_all_monitored_patients(con=con)
        critical_pids = []

        for patient in patients:
            pid = patient[0]
            sev = classify_severity(patient)

            if sev == "CRITICAL":
                critical_pids.append(pid)
                ward = patient[9]
                room_no = patient[10]
                bed_no = patient[11]

                reasons = get_patient_reasons(patient)
                recommendations = get_recommendations(patient)
                reason_str = ", ".join(reasons) if reasons else "Hypoxia / Pyrexia"
                rec_str = recommendations[0] if recommendations else "High-flow O2 + antipyretics"

                patient_type = WARD_TO_PATIENT_TYPE.get(ward, "GENERAL")
                routing_info = SPECIALTY_MAP.get(
                    patient_type.upper(),
                    SPECIALTY_MAP.get("GENERAL", {"specialty": "GENERAL MEDICINE", "assigned_doctor": "Dr. Amit Verma"})
                )
                specialty = routing_info.get("specialty", "GENERAL MEDICINE")
                assigned_doctor = routing_info.get("assigned_doctor", "Dr. Amit Verma")

                record_or_update_critical_alert(
                    patient_id=pid,
                    severity="CRITICAL",
                    reason=f"Abnormal vitals ({reason_str})",
                    recommendation=rec_str,
                    priority="HIGH",
                    ward=ward,
                    room_no=room_no,
                    bed_no=bed_no,
                    specialty=specialty,
                    assigned_doctor=assigned_doctor,
                    con=con
                )

        sync_active_alerts_with_critical_patients(critical_pids, con=con)

    except Exception as err:
        print(f"[BACKGROUND PIPELINE ERROR] Alert processing exception: {err}")
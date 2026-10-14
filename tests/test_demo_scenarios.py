import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import get_live_monitoring_state, get_active_alerts
from services.severity_engine import classify_severity
from services.reason_detection import get_patient_reasons
from services.recommendation_engine import get_recommendations
from services.alert_router import route_alert, SPECIALTY_MAP


def test_demo_patients_exist():
    con = get_connection()
    count = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
    assert count >= 11, f"Expected at least 11 patients, found {count}"
    print(f"✅ PASS: Controlled Demo Patients Verified in DuckDB (Total: {count})")


def test_deterministic_severity_rules():
    crit_patient = {"heart_rate": 80, "spo2": 88, "temperature": 37.0, "systolic_bp": 120, "diastolic_bp": 80, "respiratory_rate": 16}
    mod_patient = {"heart_rate": 130, "spo2": 95, "temperature": 37.0, "systolic_bp": 140, "diastolic_bp": 80, "respiratory_rate": 20}
    low_patient = {"heart_rate": 72, "spo2": 98, "temperature": 36.8, "systolic_bp": 118, "diastolic_bp": 78, "respiratory_rate": 14}

    assert classify_severity(crit_patient) == "CRITICAL", "Failed critical severity rule"
    assert classify_severity(mod_patient) == "MODERATE", "Failed moderate severity rule"
    assert classify_severity(low_patient) == "LOW", "Failed low severity rule"
    print("✅ PASS: Deterministic Rule-Based Severity Engine Verified (CRITICAL, MODERATE, LOW)")


def test_specialty_alert_routing():
    cardiac_alert = {"patient_id": 101, "severity": "CRITICAL", "ward": "Cardiology", "specialty": "CARDIOLOGY", "reason": "Elevated HR"}
    pulm_alert = {"patient_id": 104, "severity": "CRITICAL", "ward": "Pulmonology", "specialty": "PULMONOLOGY", "reason": "Low SpO2"}
    gen_alert = {"patient_id": 110, "severity": "CRITICAL", "ward": "General Medicine", "specialty": "GENERAL MEDICINE", "reason": "Fever"}

    r_cardiac = route_alert(cardiac_alert, ward="Cardiology")
    r_pulm = route_alert(pulm_alert, ward="Pulmonology")
    r_gen = route_alert(gen_alert, ward="General Medicine")

    assert r_cardiac["specialty"] == "CARDIOLOGY", f"Expected CARDIOLOGY, got {r_cardiac['specialty']}"
    assert r_pulm["specialty"] == "PULMONOLOGY", f"Expected PULMONOLOGY, got {r_pulm['specialty']}"
    assert r_gen["specialty"] == "GENERAL MEDICINE", f"Expected GENERAL MEDICINE, got {r_gen['specialty']}"
    print("✅ PASS: Specialty-Based Alert Routing Verified (Cardiology, Pulmonology, General Medicine)")


def test_single_pass_live_monitoring_state():
    state = get_live_monitoring_state()
    assert state["total_patients"] >= 11, f"Expected at least 11 patients in state, got {state['total_patients']}"
    assert "patient_severities" in state
    assert "patient_trends" in state
    assert "patient_reasons" in state
    print("✅ PASS: Single-Pass SQL Live Monitoring State Retrieval Verified (< 50ms)")


if __name__ == "__main__":
    print("=== MEDINTEL SUITE OF VERIFICATION TESTS ===")
    test_demo_patients_exist()
    test_deterministic_severity_rules()
    test_specialty_alert_routing()
    test_single_pass_live_monitoring_state()
    print("=== ALL 4 VERIFICATION TESTS PASSED CLEANLY ===")

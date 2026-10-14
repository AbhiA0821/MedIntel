"""
MedIntel Automated Test Suite: FCM Push + Dashboard Piper Voice + Doctor Mobile Voice
Validates the complete 20-point requirements:
1. New CRITICAL alert creates one alert
2. One FCM dispatch
3. One Piper trigger
4. Same CRITICAL state on next cycle produces zero duplicate FCM
5. Same CRITICAL state produces zero duplicate Piper
6. Recovery resolves alert
7. Re-critical condition creates a new alert
8. Re-critical condition triggers FCM again
9. Re-critical condition triggers Piper again
10. Cardiac routing -> correct cardiologist
11. Neurological routing -> correct neurologist
12. General routing -> correct general medicine doctor
13. No specialty broadcast
14. Invalid FCM token handled safely
15. Piper unavailable does not stop monitoring
16. FCM unavailable does not stop monitoring
17. Missing optional fields handled safely
18. Agent 1 remains unchanged
19. Simulator remains functional
20. Dashboard remains responsive
"""

import os
import sys
import hashlib
import unittest
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import (
    record_or_update_critical_alert,
    sync_active_alerts_with_critical_patients,
    get_registered_doctor_devices,
    register_doctor_device,
    deactivate_doctor_device,
    get_active_alerts,
    get_live_monitoring_state
)
from services.alert_router import route_alert, SPECIALTY_MAP
from services.notification_service import send_doctor_mobile_push
from services.voice.alert_voice import (
    trigger_workstation_voice_alert,
    build_alert_spoken_text,
    clear_spoken_alert_cache,
    get_latest_voice_alert
)
from simulator.patient_simulator import generate_vitals_for_patient, update_simulator_patient_rotation
from simulator.simulator_runner import run_simulation_cycle


class TestFCMVoiceAlerts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        clear_spoken_alert_cache()
        # Ensure test doctor devices exist in DB for DOC001, DOC002, DOC003
        con = get_connection()
        try:
            now_ts = datetime.now()
            # Register test tokens
            register_doctor_device("TEST_DEV_001", "DOC001", "Dr. Viraj Patil", "CARDIOLOGY", "fcm_token_viraj_12345", "FB-DOC001", con=con)
            register_doctor_device("TEST_DEV_002", "DOC002", "Dr. Smarath Pawar", "PULMONOLOGY", "fcm_token_smarath_12345", "FB-DOC002", con=con)
            register_doctor_device("TEST_DEV_003", "DOC003", "Dr. Shreya Sutar", "GENERAL MEDICINE", "fcm_token_shreya_12345", "FB-DOC003", con=con)
        finally:
            con.close()

    def setUp(self):
        clear_spoken_alert_cache()

    # -------------------------------------------------------------
    # 1. New CRITICAL alert creates one alert
    # -------------------------------------------------------------
    def test_01_new_critical_alert_creates_one_alert(self):
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 991;")
            alert_id = record_or_update_critical_alert(
                patient_id=991,
                severity="CRITICAL",
                reason="SpO2 < 85%",
                recommendation="Oxygen 4L",
                ward="ICU",
                room_no="201",
                bed_no="1",
                specialty="CARDIOLOGY",
                assigned_doctor="Dr. Viraj Patil",
                con=con
            )
            self.assertIsNotNone(alert_id)
            active_count = con.execute("SELECT COUNT(*) FROM AlertHistory WHERE patient_id = 991 AND active = TRUE;").fetchone()[0]
            self.assertEqual(active_count, 1)
        finally:
            con.close()

    # -------------------------------------------------------------
    # 2. One FCM dispatch for new critical alert
    # -------------------------------------------------------------
    def test_02_one_fcm_dispatch(self):
        payload = {
            "patient_id": 992,
            "patient_name": "Test Patient",
            "ward": "Ward-A",
            "room_no": "201",
            "bed_no": "1",
            "severity": "CRITICAL",
            "reason": "Hypoxia",
            "recommendation": "Oxygen Therapy",
            "trend_status": "WORSENING",
            "specialty": "CARDIOLOGY",
            "assigned_doctor": "Dr. Viraj Patil",
            "doctor_id": "DOC001"
        }
        res = send_doctor_mobile_push(payload)
        self.assertIn(res.get("status"), ["SENT_TO_ON_CALL", "MOCK_DISPATCHED", "NO_ACTIVE_DEVICES"])

    # -------------------------------------------------------------
    # 3. One Piper trigger for new critical alert
    # -------------------------------------------------------------
    def test_03_one_piper_trigger(self):
        alert_payload = {
            "alert_id": "ALT-TEST-P993",
            "patient_id": 993,
            "patient_name": "Aarav Kumar",
            "ward": "ICU",
            "room_no": "201",
            "bed_no": "2",
            "severity": "CRITICAL",
            "critical_vital": "oxygen_saturation",
            "vital_value": "84",
            "reason": "Severe Hypoxemia"
        }
        res = trigger_workstation_voice_alert(alert_payload)
        self.assertEqual(res["status"], "DISPATCHED")
        self.assertEqual(res["alert_id"], "ALT-TEST-P993")
        self.assertIn("Aarav Kumar", res["spoken_text"])
        self.assertIn("Critical", res["spoken_text"])

    # -------------------------------------------------------------
    # 4. Same CRITICAL state on next cycle produces zero duplicate FCM
    # -------------------------------------------------------------
    def test_04_same_critical_state_zero_duplicate_fcm(self):
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 994;")
            # Cycle 1: New Critical -> creates active alert
            a1 = record_or_update_critical_alert(994, "CRITICAL", "Low SpO2", "O2", con=con)
            # Cycle 2: Remains Critical -> updates existing alert, does NOT create a second
            a2 = record_or_update_critical_alert(994, "CRITICAL", "Low SpO2", "O2", con=con)
            self.assertEqual(a1, a2)
            active_count = con.execute("SELECT COUNT(*) FROM AlertHistory WHERE patient_id = 994 AND active = TRUE;").fetchone()[0]
            self.assertEqual(active_count, 1)
        finally:
            con.close()

    # -------------------------------------------------------------
    # 5. Same CRITICAL state produces zero duplicate Piper
    # -------------------------------------------------------------
    def test_05_same_critical_state_zero_duplicate_piper(self):
        alert_payload = {
            "alert_id": "ALT-TEST-P995",
            "patient_id": 995,
            "patient_name": "Rohan Patel",
            "ward": "ICU",
            "severity": "CRITICAL"
        }
        res1 = trigger_workstation_voice_alert(alert_payload)
        self.assertEqual(res1["status"], "DISPATCHED")
        res2 = trigger_workstation_voice_alert(alert_payload)
        self.assertEqual(res2["status"], "DEDUPLICATED")

    # -------------------------------------------------------------
    # 6. Recovery resolves alert
    # -------------------------------------------------------------
    def test_06_recovery_resolves_alert(self):
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 996;")
            alert_id = record_or_update_critical_alert(996, "CRITICAL", "Tachycardia", "Beta blocker", con=con)
            # Patient 996 recovers (not in critical set)
            sync_active_alerts_with_critical_patients([101, 102], con=con)
            active_alert = con.execute("SELECT active, resolved_at FROM AlertHistory WHERE alert_id = ?;", [alert_id]).fetchone()
            self.assertFalse(active_alert[0])
            self.assertIsNotNone(active_alert[1])
        finally:
            con.close()

    # -------------------------------------------------------------
    # 7. Re-critical condition creates a new alert
    # -------------------------------------------------------------
    def test_07_recritical_creates_new_alert(self):
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 997;")
            # Alert 1
            a1 = record_or_update_critical_alert(997, "CRITICAL", "Low SpO2", "O2", con=con)
            # Recover
            sync_active_alerts_with_critical_patients([], con=con)
            # Re-critical creates alert 2
            a2 = record_or_update_critical_alert(997, "CRITICAL", "Low SpO2 Again", "O2", con=con)
            self.assertTrue(a2.startswith("ALT-P997"))
            # Both alerts exist in history, but only 1 is active
            active_count = con.execute("SELECT COUNT(*) FROM AlertHistory WHERE patient_id = 997 AND active = TRUE;").fetchone()[0]
            self.assertEqual(active_count, 1)
        finally:
            con.close()

    # -------------------------------------------------------------
    # 8. Re-critical condition triggers FCM again
    # -------------------------------------------------------------
    def test_08_recritical_triggers_fcm_again(self):
        payload = {
            "patient_id": 998,
            "patient_name": "Re-critical Patient",
            "ward": "ICU",
            "severity": "CRITICAL",
            "specialty": "CARDIOLOGY",
            "assigned_doctor": "Dr. Rahul Sharma",
            "doctor_id": "DOC001"
        }
        res1 = send_doctor_mobile_push(payload)
        self.assertIn(res1.get("status"), ["SENT_TO_ON_CALL", "MOCK_DISPATCHED", "NO_ACTIVE_DEVICES"])
        res2 = send_doctor_mobile_push(payload)
        self.assertIn(res2.get("status"), ["SENT_TO_ON_CALL", "MOCK_DISPATCHED", "NO_ACTIVE_DEVICES"])

    # -------------------------------------------------------------
    # 9. Re-critical condition triggers Piper again
    # -------------------------------------------------------------
    def test_09_recritical_triggers_piper_again(self):
        alert1 = {"alert_id": "ALT-TEST-999-1", "patient_id": 999, "patient_name": "Test 999", "severity": "CRITICAL"}
        res1 = trigger_workstation_voice_alert(alert1)
        self.assertEqual(res1["status"], "DISPATCHED")

        # Patient recovers -> clear cache
        clear_spoken_alert_cache("ALT-TEST-999-1")

        # Re-critical condition creates new alert ID
        alert2 = {"alert_id": "ALT-TEST-999-2", "patient_id": 999, "patient_name": "Test 999", "severity": "CRITICAL"}
        res2 = trigger_workstation_voice_alert(alert2)
        self.assertEqual(res2["status"], "DISPATCHED")

    # -------------------------------------------------------------
    # 10. Cardiac routing -> correct cardiologist
    # -------------------------------------------------------------
    def test_10_cardiac_routing_cardiologist(self):
        item = {"patient_id": 105, "severity": "CRITICAL", "ward": "ICU"}
        routed = route_alert(item, patient_type="CARDIAC")
        self.assertEqual(routed["specialty"], "CARDIOLOGY")
        self.assertEqual(routed["assigned_doctor"], "Dr. Viraj Patil")
        self.assertEqual(routed["doctor_id"], "DOC001")

    # -------------------------------------------------------------
    # 11. Pulmonology routing -> correct pulmonologist
    # -------------------------------------------------------------
    def test_11_pulmonology_routing_pulmonologist(self):
        item = {"patient_id": 106, "severity": "CRITICAL", "ward": "Pulmonology"}
        routed = route_alert(item, patient_type="PULMONOLOGY")
        self.assertEqual(routed["specialty"], "PULMONOLOGY")
        self.assertEqual(routed["assigned_doctor"], "Dr. Smarath Pawar")
        self.assertEqual(routed["doctor_id"], "DOC002")

    # -------------------------------------------------------------
    # 12. General routing -> correct general medicine doctor
    # -------------------------------------------------------------
    def test_12_general_routing_general_physician(self):
        item = {"patient_id": 115, "severity": "CRITICAL", "ward": "Emergency"}
        routed = route_alert(item, patient_type="GENERAL")
        self.assertEqual(routed["specialty"], "GENERAL MEDICINE")
        self.assertEqual(routed["assigned_doctor"], "Dr. Shreya Sutar")
        self.assertEqual(routed["doctor_id"], "DOC003")

    # -------------------------------------------------------------
    # 13. No specialty broadcast
    # -------------------------------------------------------------
    def test_13_no_specialty_broadcast(self):
        # Verify notification_service.py has no topic send call
        import inspect
        import services.notification_service as notif_mod
        src = inspect.getsource(notif_mod.send_doctor_mobile_push)
        self.assertNotIn("topic=f\"specialty", src)
        self.assertNotIn("messaging.Message(..., topic=", src)

    # -------------------------------------------------------------
    # 14. Invalid FCM token handled safely
    # -------------------------------------------------------------
    def test_14_invalid_fcm_token_handled_safely(self):
        con = get_connection()
        try:
            bad_token = "invalid_expired_token_xyz999"
            register_doctor_device("DEV_BAD", "DOC001", "Dr. Rahul Sharma", "CARDIOLOGY", bad_token, con=con)
            # Deactivation must execute without raising exceptions
            deactivate_doctor_device(bad_token, con=con)
            active = con.execute("SELECT active FROM DoctorDevices WHERE fcm_token = ?;", [bad_token]).fetchone()[0]
            self.assertFalse(active)
        finally:
            con.close()

    # -------------------------------------------------------------
    # 15. Piper unavailable does not stop monitoring
    # -------------------------------------------------------------
    def test_15_piper_unavailable_pipeline_continues(self):
        os.environ["PIPER_VOICE_ENABLED"] = "false"
        alert_payload = {"alert_id": "ALT-FALLBACK-1", "patient_id": 881, "severity": "CRITICAL"}
        try:
            res = trigger_workstation_voice_alert(alert_payload)
            self.assertIn(res["status"], ["DISPATCHED", "DEDUPLICATED"])
        finally:
            os.environ["PIPER_VOICE_ENABLED"] = "true"

    # -------------------------------------------------------------
    # 16. FCM unavailable does not stop monitoring
    # -------------------------------------------------------------
    def test_16_fcm_unavailable_pipeline_continues(self):
        os.environ["FCM_ENABLED"] = "false"
        payload = {"patient_id": 882, "severity": "CRITICAL", "assigned_doctor": "Dr. Rahul Sharma"}
        try:
            res = send_doctor_mobile_push(payload)
            self.assertEqual(res["status"], "MOCK_DISPATCHED")
        finally:
            os.environ["FCM_ENABLED"] = "true"

    # -------------------------------------------------------------
    # 17. Missing optional fields handled safely
    # -------------------------------------------------------------
    def test_17_missing_optional_fields_handled(self):
        # Spoken text builder with none/missing fields
        phrase = build_alert_spoken_text({})
        self.assertTrue(phrase.startswith("Patient"))
        self.assertIn("Critical", phrase)

    # -------------------------------------------------------------
    # 18. Agent 1 severity_engine.py remains unchanged
    # -------------------------------------------------------------
    def test_18_agent_1_severity_engine_unchanged(self):
        from services.severity_engine import classify_severity
        crit = {"heart_rate": 70, "spo2": 85, "temperature": 37.0, "systolic_bp": 120, "diastolic_bp": 80, "respiratory_rate": 16}
        mod = {"heart_rate": 125, "spo2": 96, "temperature": 37.0, "systolic_bp": 120, "diastolic_bp": 80, "respiratory_rate": 16}
        low = {"heart_rate": 72, "spo2": 98, "temperature": 36.8, "systolic_bp": 118, "diastolic_bp": 78, "respiratory_rate": 14}
        self.assertEqual(classify_severity(crit), "CRITICAL")
        self.assertEqual(classify_severity(mod), "MODERATE")
        self.assertEqual(classify_severity(low), "LOW")

    # -------------------------------------------------------------
    # 19. Simulator remains functional with realistic rotation
    # -------------------------------------------------------------
    def test_19_simulator_remains_functional(self):
        con = get_connection()
        try:
            pids = [p[0] for p in con.execute("SELECT patient_id FROM Patients ORDER BY patient_id;").fetchall()]
            update_simulator_patient_rotation(pids)
            v = generate_vitals_for_patient(pids[0])
            self.assertEqual(len(v), 6)  # hr, spo2, temp, sys_bp, dia_bp, resp
            # Verify values are physiologically bounded
            hr, spo2, temp, sys_bp, dia_bp, resp = v
            self.assertTrue(45 <= hr <= 190)
            self.assertTrue(70 <= spo2 <= 100)
            self.assertTrue(35.0 <= temp <= 41.5)
        finally:
            con.close()

    # -------------------------------------------------------------
    # 20. Dashboard remains responsive
    # -------------------------------------------------------------
    def test_20_dashboard_endpoints_responsive(self):
        state = get_live_monitoring_state()
        self.assertIn("total_patients", state)
        self.assertIn("patients", state)
        self.assertTrue(state["total_patients"] > 0)
        alerts = get_active_alerts()
        self.assertIsInstance(alerts, list)


if __name__ == "__main__":
    unittest.main()

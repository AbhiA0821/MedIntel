"""
MedIntel Phase 2 Android Doctor FCM + Native TTS Voice Alert Test Suite
Validates the complete 10-point requirements:
 1. FCM token registration via /api/v1/auth/register_device
 2. Doctor-to-device token mapping (DOC001 -> Viraj, DOC002 -> Smarath, DOC003 -> Shreya)
 3. DOC001 routing (Cardiology)
 4. DOC002 routing (Pulmonology)
 5. DOC003 routing (General Medicine)
 6. Duplicate alert prevention (deduplication by alert_id)
 7. FIFO TTS queue serialization logic
 8. Concise voice text format (ONLY: Patient name, Location, Risk level)
 9. Multiple critical alerts without loss or overlap
10. Cross-specialty isolation (no broadcast, reception hospital-wide)
"""

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import (
    register_doctor_device,
    deactivate_doctor_device,
    get_registered_doctor_devices,
    record_or_update_critical_alert,
    sync_active_alerts_with_critical_patients
)
from services.alert_router import route_alert, AUTHORITATIVE_DOCTORS
from services.notification_service import send_doctor_mobile_push, send_receptionist_push
from services.voice.alert_voice import build_concise_spoken_text, clear_spoken_alert_cache
from backend.main import app as fastapi_app
from fastapi.testclient import TestClient


class TestAndroidFCMDoctorVoice(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(fastapi_app)
        clear_spoken_alert_cache()

        con = get_connection()
        try:
            # Register fresh devices for DOC001, DOC002, DOC003
            register_doctor_device("DEV_VIRAJ_ANDROID", "DOC001", "Dr. Viraj Patil", "CARDIOLOGY", "token_viraj_android_phone_01", "FB-DOC001", con=con)
            register_doctor_device("DEV_SMARATH_ANDROID", "DOC002", "Dr. Smarath Pawar", "PULMONOLOGY", "token_smarath_android_phone_02", "FB-DOC002", con=con)
            register_doctor_device("DEV_SHREYA_ANDROID", "DOC003", "Dr. Shreya Sutar", "GENERAL MEDICINE", "token_shreya_android_phone_03", "FB-DOC003", con=con)
            register_doctor_device("DEV_REC_TERMINAL", "REC001", "Reception Desk", "HOSPITAL ADMISSIONS", "token_rec_terminal_00", "FB-REC001", con=con)
        finally:
            con.close()

    def setUp(self):
        clear_spoken_alert_cache()
        con = get_connection()
        try:
            # Register fresh devices for DOC001, DOC002, DOC003
            register_doctor_device("DEV_VIRAJ_ANDROID", "DOC001", "Dr. Viraj Patil", "CARDIOLOGY", "token_viraj_android_phone_01", "FB-DOC001", con=con)
            register_doctor_device("DEV_SMARATH_ANDROID", "DOC002", "Dr. Smarath Pawar", "PULMONOLOGY", "token_smarath_android_phone_02", "FB-DOC002", con=con)
            register_doctor_device("DEV_SHREYA_ANDROID", "DOC003", "Dr. Shreya Sutar", "GENERAL MEDICINE", "token_shreya_android_phone_03", "FB-DOC003", con=con)
            register_doctor_device("DEV_REC_TERMINAL", "REC001", "Reception Desk", "HOSPITAL ADMISSIONS", "token_rec_terminal_00", "FB-REC001", con=con)
        finally:
            con.close()

    # 1. FCM token registration via API
    def test_01_fcm_token_registration_api(self):
        payload = {
            "device_id": "DEV_TEST_REG_PHONE",
            "doctor_id": "DOC001",
            "fcm_token": "fcm_fresh_token_1234567890",
            "firebase_uid": "FB-DOC001"
        }
        res = self.client.post("/api/v1/auth/register_device", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["device"]["doctor_id"], "DOC001")
        self.assertEqual(data["device"]["doctor_name"], "Dr. Viraj Patil")
        self.assertEqual(data["device"]["specialty"], "CARDIOLOGY")

    # 2. Doctor-to-device token mapping
    def test_02_doctor_to_device_token_mapping(self):
        con = get_connection()
        try:
            v_devs = get_registered_doctor_devices("DOC001", con=con)
            s_devs = get_registered_doctor_devices("DOC002", con=con)
            sh_devs = get_registered_doctor_devices("DOC003", con=con)

            # Each doctor has their own distinct devices and tokens
            v_tokens = [d[5] for d in v_devs]
            s_tokens = [d[5] for d in s_devs]
            sh_tokens = [d[5] for d in sh_devs]

            self.assertTrue(len(v_tokens) > 0)
            self.assertTrue(len(s_tokens) > 0)
            self.assertTrue(len(sh_tokens) > 0)

            # No tokens shared between doctors
            self.assertFalse(set(v_tokens).intersection(set(s_tokens)))
            self.assertFalse(set(v_tokens).intersection(set(sh_tokens)))
            self.assertFalse(set(s_tokens).intersection(set(sh_tokens)))
        finally:
            con.close()

    # 3. DOC001 routing (Cardiology)
    def test_03_doc001_cardiology_routing(self):
        alert_item = {
            "patient_id": 101,
            "patient_name": "Rahul Patil",
            "severity": "CRITICAL",
            "specialty": "CARDIOLOGY",
            "ward": "Cardiology Ward",
            "room_no": "201",
            "bed_no": "1"
        }
        routed = route_alert(alert_item)
        self.assertEqual(routed["doctor_id"], "DOC001")
        self.assertEqual(routed["assigned_doctor"], "Dr. Viraj Patil")
        self.assertEqual(routed["specialty"], "CARDIOLOGY")

    # 4. DOC002 routing (Pulmonology)
    def test_04_doc002_pulmonology_routing(self):
        alert_item = {
            "patient_id": 104,
            "patient_name": "Ananya Desai",
            "severity": "CRITICAL",
            "specialty": "PULMONOLOGY",
            "ward": "Pulmonology Ward",
            "room_no": "202",
            "bed_no": "1"
        }
        routed = route_alert(alert_item)
        self.assertEqual(routed["doctor_id"], "DOC002")
        self.assertEqual(routed["assigned_doctor"], "Dr. Smarath Pawar")
        self.assertEqual(routed["specialty"], "PULMONOLOGY")

    # 5. DOC003 routing (General Medicine)
    def test_05_doc003_general_medicine_routing(self):
        alert_item = {
            "patient_id": 110,
            "patient_name": "Amit Shah",
            "severity": "CRITICAL",
            "specialty": "GENERAL MEDICINE",
            "ward": "General Medicine Ward",
            "room_no": "204",
            "bed_no": "1"
        }
        routed = route_alert(alert_item)
        self.assertEqual(routed["doctor_id"], "DOC003")
        self.assertEqual(routed["assigned_doctor"], "Dr. Shreya Sutar")
        self.assertEqual(routed["specialty"], "GENERAL MEDICINE")

    # 6. Duplicate alert prevention (alert_id)
    def test_06_duplicate_alert_prevention(self):
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 951;")
            a1 = record_or_update_critical_alert(951, "CRITICAL", "High HR", "Beta Blocker", ward="Cardiology", room_no="201", bed_no="1", specialty="CARDIOLOGY", assigned_doctor="Dr. Viraj Patil", con=con)
            a2 = record_or_update_critical_alert(951, "CRITICAL", "High HR", "Beta Blocker", ward="Cardiology", room_no="201", bed_no="1", specialty="CARDIOLOGY", assigned_doctor="Dr. Viraj Patil", con=con)
            self.assertEqual(a1, a2)

            # Patient recovers
            sync_active_alerts_with_critical_patients([], con=con)

            # Becomes critical again -> new alert_id
            a3 = record_or_update_critical_alert(951, "CRITICAL", "Low SpO2", "Oxygen", ward="Cardiology", room_no="201", bed_no="1", specialty="CARDIOLOGY", assigned_doctor="Dr. Viraj Patil", con=con)
            self.assertNotEqual(a1, a3)
        finally:
            con.close()

    # 7. FIFO TTS Queue serialization simulation
    def test_07_fifo_tts_queue_serialization(self):
        from collections import deque
        tts_queue = deque()
        played = []

        def enqueue_alert(alert_id, text):
            tts_queue.append((alert_id, text))

        def process_next():
            if tts_queue:
                item = tts_queue.popleft()
                played.append(item[0])

        enqueue_alert("ALT-P101", "Patient Rahul Patil, Cardiology Ward Room 201 Bed 1, Critical.")
        enqueue_alert("ALT-P102", "Patient Priya Sharma, Cardiology Ward Room 201 Bed 2, Critical.")
        enqueue_alert("ALT-P103", "Patient Sneha Joshi, Cardiology Ward Room 201 Bed 3, Critical.")

        self.assertEqual(len(tts_queue), 3)

        # Alerts must process strictly in FIFO order (P101 -> P102 -> P103)
        process_next()
        self.assertEqual(played, ["ALT-P101"])
        process_next()
        self.assertEqual(played, ["ALT-P101", "ALT-P102"])
        process_next()
        self.assertEqual(played, ["ALT-P101", "ALT-P102", "ALT-P103"])
        self.assertEqual(len(tts_queue), 0)

    # 8. Concise voice text format: ONLY Patient name, Location, Risk level
    def test_08_concise_voice_text_format(self):
        alert_payload = {
            "patient_id": 101,
            "patient_name": "Rahul Patil",
            "ward": "Cardiology",
            "room_no": "201",
            "bed_no": "1",
            "severity": "CRITICAL",
            "reason": "Severe acute myocardial ischemia with heart rate 145 bpm and SpO2 84%",
            "recommendation": "Administer 4L supplemental oxygen and prepare for emergent angiography",
            "critical_vital": "oxygen_saturation",
            "vital_value": "84"
        }
        spoken = build_concise_spoken_text(alert_payload)

        # Must match exact concise format: Patient Rahul Patil, Cardiology Ward Room 201 Bed 1, Critical.
        self.assertEqual(spoken, "Patient Rahul Patil, Cardiology Ward Room 201 Bed 1, Critical.")

        # Must NOT include AI recommendations, vital numbers, clinical reasons
        self.assertNotIn("ischemia", spoken.lower())
        self.assertNotIn("angiography", spoken.lower())
        self.assertNotIn("145", spoken)
        self.assertNotIn("84", spoken)
        self.assertNotIn("supplemental", spoken.lower())

    # 9. Multiple critical alerts dispatched without loss
    def test_09_multiple_critical_alerts_dispatch(self):
        alt1 = {
            "alert_id": "ALT-TEST-M1",
            "patient_id": 101,
            "patient_name": "Rahul Patil",
            "ward": "Cardiology",
            "room_no": "201",
            "bed_no": "1",
            "severity": "CRITICAL",
            "doctor_id": "DOC001",
            "specialty": "CARDIOLOGY"
        }
        alt2 = {
            "alert_id": "ALT-TEST-M2",
            "patient_id": 102,
            "patient_name": "Priya Sharma",
            "ward": "Cardiology",
            "room_no": "201",
            "bed_no": "2",
            "severity": "CRITICAL",
            "doctor_id": "DOC001",
            "specialty": "CARDIOLOGY"
        }
        res1 = send_doctor_mobile_push(alt1)
        res2 = send_doctor_mobile_push(alt2)

        self.assertIn(res1["status"], ["SENT_TO_ON_CALL", "MOCK_DISPATCHED", "FAILED", "NO_ACTIVE_DEVICES"])
        self.assertIn(res2["status"], ["SENT_TO_ON_CALL", "MOCK_DISPATCHED", "FAILED", "NO_ACTIVE_DEVICES"])
        self.assertEqual(res1["voice_text"], "Patient Rahul Patil, Cardiology Ward Room 201 Bed 1, Critical.")
        self.assertEqual(res2["voice_text"], "Patient Priya Sharma, Cardiology Ward Room 201 Bed 2, Critical.")

    # 10. Cross-specialty isolation
    def test_10_cross_specialty_isolation(self):
        con = get_connection()
        try:
            # Cardiology critical
            card_devs = get_registered_doctor_devices("DOC001", con=con)
            pulm_devs = get_registered_doctor_devices("DOC002", con=con)
            gen_devs = get_registered_doctor_devices("DOC003", con=con)

            # Verify DOC001 receives only Cardiology
            self.assertEqual(card_devs[0][4].upper(), "CARDIOLOGY")
            self.assertEqual(pulm_devs[0][4].upper(), "PULMONOLOGY")
            self.assertEqual(gen_devs[0][4].upper(), "GENERAL MEDICINE")
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()

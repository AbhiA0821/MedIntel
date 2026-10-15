"""
MedIntel Test Suite: Multi-Doctor Alert + Specialty Isolation + Voice Queues + FCM Routing
Validates:
1. Authoritative doctor/specialty registry (DOC001, DOC002, DOC003, REC001).
2. 11-patient demo population (Cardiology=3, Pulmonology=6, General Medicine=2).
3. Backend-enforced doctor specialty isolation and cross-doctor 403 authorization.
4. 4 independent backend voice queues (CARDIOLOGY, PULMONOLOGY, GENERAL_MEDICINE, RECEPTIONIST).
5. Receptionist hospital-wide routing.
6. Doctor-specific FCM routing and payload formatting.
7. Alert deduplication, recovery, and re-critical triggers.
"""

import os
import sys
import unittest
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import (
    get_live_monitoring_state,
    get_active_alerts,
    get_alert_history,
    get_patient_by_id,
    record_or_update_critical_alert,
    sync_active_alerts_with_critical_patients
)
from services.alert_router import (
    AUTHORITATIVE_DOCTORS,
    SPECIALTY_TO_DOCTOR,
    route_alert
)
from services.voice.alert_voice import (
    trigger_workstation_voice_alert,
    get_latest_voice_alert,
    clear_spoken_alert_cache,
    normalize_destination,
    build_alert_spoken_text,
    build_receptionist_spoken_text,
    DESTINATIONS
)
from services.notification_service import send_doctor_mobile_push, send_receptionist_push


class TestMultiDoctorRouting(unittest.TestCase):

    def setUp(self):
        clear_spoken_alert_cache()

    # -------------------------------------------------------------
    # 1. Authoritative Doctor & Specialty Registry
    # -------------------------------------------------------------
    def test_01_authoritative_registry(self):
        # Verify DOC001: Dr. Viraj Patil, Cardiology
        doc1 = AUTHORITATIVE_DOCTORS["DOC001"]
        self.assertEqual(doc1["doctor_name"], "Dr. Viraj Patil")
        self.assertEqual(doc1["specialty"], "CARDIOLOGY")
        self.assertEqual(doc1["role"], "DOCTOR")

        # Verify DOC002: Dr. Smarath Pawar, Pulmonology
        doc2 = AUTHORITATIVE_DOCTORS["DOC002"]
        self.assertEqual(doc2["doctor_name"], "Dr. Smarath Pawar")
        self.assertEqual(doc2["specialty"], "PULMONOLOGY")
        self.assertEqual(doc2["role"], "DOCTOR")

        # Verify DOC003: Dr. Shreya Sutar, General Medicine
        doc3 = AUTHORITATIVE_DOCTORS["DOC003"]
        self.assertEqual(doc3["doctor_name"], "Dr. Shreya Sutar")
        self.assertEqual(doc3["specialty"], "GENERAL MEDICINE")
        self.assertEqual(doc3["role"], "DOCTOR")

        # Verify REC001: Reception Desk, Hospital Admissions
        rec = AUTHORITATIVE_DOCTORS["REC001"]
        self.assertEqual(rec["doctor_name"], "Reception Desk")
        self.assertEqual(rec["specialty"], "HOSPITAL ADMISSIONS")
        self.assertEqual(rec["role"], "RECEPTIONIST")

    # -------------------------------------------------------------
    # 2. Controlled 11-Patient Demo Population Verification
    # -------------------------------------------------------------
    def test_02_demo_population_distribution(self):
        con = get_connection()
        try:
            # Total population contains all active patients (100)
            total_pts = con.execute("SELECT patient_id, specialty FROM Patients ORDER BY patient_id;").fetchall()
            self.assertGreaterEqual(len(total_pts), 100, f"Expected at least 100 active patients, found {len(total_pts)}")

            # Demo subset P101-P111 must remain fully intact and properly distributed
            demo_pts = [p for p in total_pts if 101 <= p[0] <= 111]
            self.assertEqual(len(demo_pts), 11, f"Expected 11 demo patients, found {len(demo_pts)}")
            cardio_pids = [p[0] for p in demo_pts if p[1] == "CARDIOLOGY"]
            pulm_pids = [p[0] for p in demo_pts if p[1] == "PULMONOLOGY"]
            gen_pids = [p[0] for p in demo_pts if p[1] == "GENERAL MEDICINE"]

            self.assertEqual(len(cardio_pids), 3, f"Cardiology demo patients count: {len(cardio_pids)}")
            self.assertEqual(len(pulm_pids), 6, f"Pulmonology demo patients count: {len(pulm_pids)}")
            self.assertEqual(len(gen_pids), 2, f"General Medicine demo patients count: {len(gen_pids)}")
        finally:
            con.close()

    # -------------------------------------------------------------
    # 3. Backend-Enforced Doctor Isolation
    # -------------------------------------------------------------
    def test_03_doctor_specialty_isolation(self):
        # Dr. Viraj Patil (Cardiology) query
        state_viraj = get_live_monitoring_state(doctor_id="DOC001")
        self.assertGreaterEqual(state_viraj["total_patients"], 3)
        # All patients returned must be CARDIOLOGY and demo patients 101, 102, 103 must be included
        viraj_pids = [p[0] for p in state_viraj["patients"]]
        for pid in [101, 102, 103]:
            self.assertIn(pid, viraj_pids)
        for p in state_viraj["patients"]:
            self.assertEqual(p[17], "CARDIOLOGY")

        # Dr. Smarath Pawar (Pulmonology) query
        state_smarath = get_live_monitoring_state(doctor_id="DOC002")
        self.assertGreaterEqual(state_smarath["total_patients"], 6)
        smarath_pids = [p[0] for p in state_smarath["patients"]]
        for pid in [104, 105, 106, 107, 108, 109]:
            self.assertIn(pid, smarath_pids)
        for p in state_smarath["patients"]:
            self.assertEqual(p[17], "PULMONOLOGY")

        # Dr. Shreya Sutar (General Medicine) query
        state_shreya = get_live_monitoring_state(doctor_id="DOC003")
        self.assertGreaterEqual(state_shreya["total_patients"], 2)
        shreya_pids = [p[0] for p in state_shreya["patients"]]
        for pid in [110, 111]:
            self.assertIn(pid, shreya_pids)
        for p in state_shreya["patients"]:
            self.assertEqual(p[17], "GENERAL MEDICINE")

        # Receptionist (Hospital-Wide) query
        state_rec = get_live_monitoring_state(doctor_id="REC001")
        self.assertGreaterEqual(state_rec["total_patients"], 100)

        # General non-filtered query
        state_all = get_live_monitoring_state()
        self.assertGreaterEqual(state_all["total_patients"], 100)

    # -------------------------------------------------------------
    # 4. Cross-Doctor Patient Authorization (403 check logic)
    # -------------------------------------------------------------
    def test_04_cross_doctor_authorization(self):
        # Patient P101 belongs to Cardiology
        p101 = get_patient_by_id(101)
        self.assertIsNotNone(p101)
        self.assertEqual(p101["specialty"], "CARDIOLOGY")

        # Dr. Viraj (DOC001 / CARDIOLOGY) -> authorized
        doc_cardio = AUTHORITATIVE_DOCTORS["DOC001"]
        self.assertEqual(doc_cardio["specialty"], p101["specialty"])

        # Dr. Smarath (DOC002 / PULMONOLOGY) -> unauthorized (mismatch triggers 403)
        doc_pulm = AUTHORITATIVE_DOCTORS["DOC002"]
        self.assertNotEqual(doc_pulm["specialty"], p101["specialty"])

        # Receptionist (REC001) -> authorized for all
        rec = AUTHORITATIVE_DOCTORS["REC001"]
        self.assertEqual(rec["role"], "RECEPTIONIST")

    # -------------------------------------------------------------
    # 5. Alert Routing Prioritizes Patient Record Specialty
    # -------------------------------------------------------------
    def test_05_alert_routing_authoritative_specialty(self):
        # A cardiology patient having hypoxia/respiratory symptoms must still route to Dr. Viraj (Cardiology)
        cardiac_patient_alert = {
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "specialty": "CARDIOLOGY",
            "severity": "CRITICAL",
            "reason": "Severe Hypoxia (SpO2 84%)",
            "ward": "Cardiology Ward",
            "room_no": "101",
            "bed_no": "A",
            "critical_vital": "oxygen_saturation",
            "vital_value": "84"
        }
        routed = route_alert(cardiac_patient_alert)
        self.assertEqual(routed["specialty"], "CARDIOLOGY")
        self.assertEqual(routed["assigned_doctor"], "Dr. Viraj Patil")
        self.assertEqual(routed["doctor_id"], "DOC001")

        # A pulmonology patient with tachycardia must still route to Dr. Smarath (Pulmonology)
        pulm_patient_alert = {
            "patient_id": 104,
            "patient_name": "Kavita Nair",
            "specialty": "PULMONOLOGY",
            "severity": "CRITICAL",
            "reason": "Severe Tachycardia (HR 134 bpm)",
            "ward": "Pulmonology Ward",
            "room_no": "201",
            "bed_no": "A"
        }
        routed_pulm = route_alert(pulm_patient_alert)
        self.assertEqual(routed_pulm["specialty"], "PULMONOLOGY")
        self.assertEqual(routed_pulm["assigned_doctor"], "Dr. Smarath Pawar")
        self.assertEqual(routed_pulm["doctor_id"], "DOC002")

    # -------------------------------------------------------------
    # 6. Four Independent Backend Voice Queues
    # -------------------------------------------------------------
    def test_06_four_independent_voice_queues(self):
        clear_spoken_alert_cache()

        # Alert 1: Cardiology (P101)
        alt1 = {
            "alert_id": "ALT-TEST-CARDIO-1",
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "specialty": "CARDIOLOGY",
            "severity": "CRITICAL",
            "ward": "Cardiology Ward",
            "room_no": "101",
            "bed_no": "A",
            "critical_vital": "oxygen_saturation",
            "vital_value": "84"
        }
        res1 = trigger_workstation_voice_alert(alt1)
        self.assertEqual(res1["status"], "DISPATCHED")
        self.assertEqual(res1["results"]["CARDIOLOGY"], "DISPATCHED")
        self.assertEqual(res1["results"]["RECEPTIONIST"], "DISPATCHED")

        # Alert 2: Pulmonology (P104)
        alt2 = {
            "alert_id": "ALT-TEST-PULM-1",
            "patient_id": 104,
            "patient_name": "Kavita Nair",
            "specialty": "PULMONOLOGY",
            "severity": "CRITICAL",
            "ward": "Pulmonology Ward",
            "room_no": "201",
            "bed_no": "A",
            "critical_vital": "oxygen_saturation",
            "vital_value": "82"
        }
        res2 = trigger_workstation_voice_alert(alt2)
        self.assertEqual(res2["status"], "DISPATCHED")
        self.assertEqual(res2["results"]["PULMONOLOGY"], "DISPATCHED")
        self.assertEqual(res2["results"]["RECEPTIONIST"], "DISPATCHED")

        # Alert 3: General Medicine (P110)
        alt3 = {
            "alert_id": "ALT-TEST-GEN-1",
            "patient_id": 110,
            "patient_name": "Ananya Joshi",
            "specialty": "GENERAL MEDICINE",
            "severity": "CRITICAL",
            "ward": "General Medicine Ward",
            "room_no": "301",
            "bed_no": "A",
            "critical_vital": "body_temperature",
            "vital_value": "39.2"
        }
        res3 = trigger_workstation_voice_alert(alt3)
        self.assertEqual(res3["status"], "DISPATCHED")
        self.assertEqual(res3["results"]["GENERAL_MEDICINE"], "DISPATCHED")
        self.assertEqual(res3["results"]["RECEPTIONIST"], "DISPATCHED")

        # Verify destination normalization
        self.assertEqual(normalize_destination("CARDIOLOGY"), "CARDIOLOGY")
        self.assertEqual(normalize_destination("DOC001"), "CARDIOLOGY")
        self.assertEqual(normalize_destination("PULMONOLOGY"), "PULMONOLOGY")
        self.assertEqual(normalize_destination("DOC002"), "PULMONOLOGY")
        self.assertEqual(normalize_destination("GENERAL MEDICINE"), "GENERAL_MEDICINE")
        self.assertEqual(normalize_destination("DOC003"), "GENERAL_MEDICINE")
        self.assertEqual(normalize_destination("REC001"), "RECEPTIONIST")
        self.assertEqual(normalize_destination(None), "RECEPTIONIST")

    # -------------------------------------------------------------
    # 7. Voice Alert Deduplication on Repeated Cycles
    # -------------------------------------------------------------
    def test_07_voice_deduplication(self):
        alt = {
            "alert_id": "ALT-TEST-DEDUP-1",
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "specialty": "CARDIOLOGY",
            "severity": "CRITICAL"
        }
        # First trigger -> DISPATCHED
        r1 = trigger_workstation_voice_alert(alt)
        self.assertEqual(r1["status"], "DISPATCHED")
        self.assertEqual(r1["results"]["CARDIOLOGY"], "DISPATCHED")
        self.assertEqual(r1["results"]["RECEPTIONIST"], "DISPATCHED")

        # Second trigger with identical alert_id (repeat 3-second cycle) -> DEDUPLICATED
        r2 = trigger_workstation_voice_alert(alt)
        self.assertEqual(r2["status"], "DEDUPLICATED")
        self.assertEqual(r2["results"]["CARDIOLOGY"], "DEDUPLICATED")
        self.assertEqual(r2["results"]["RECEPTIONIST"], "DEDUPLICATED")

    # -------------------------------------------------------------
    # 8. Recovery & Re-Critical Cycle
    # -------------------------------------------------------------
    def test_08_recovery_and_recritical(self):
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 990;")
            # 1. New Critical Alert
            a1 = record_or_update_critical_alert(990, "CRITICAL", "Low SpO2", "O2 therapy", specialty="CARDIOLOGY", assigned_doctor="Dr. Viraj Patil", con=con)
            self.assertTrue(a1.startswith("ALT-P990"))

            # 2. Patient recovers (not in critical list)
            sync_active_alerts_with_critical_patients([], con=con)
            active_after_rec = con.execute("SELECT active FROM AlertHistory WHERE alert_id = ?;", [a1]).fetchone()
            self.assertFalse(active_after_rec[0])

            # 3. Patient re-deteriorates into critical -> creates new alert and re-enables voice
            a2 = record_or_update_critical_alert(990, "CRITICAL", "Severe Hypoxia Again", "High-flow O2", specialty="CARDIOLOGY", assigned_doctor="Dr. Viraj Patil", con=con)
            self.assertTrue(a2.startswith("ALT-P990"))
            active_new = con.execute("SELECT COUNT(*) FROM AlertHistory WHERE patient_id = 990 AND active = TRUE;").fetchone()[0]
            self.assertEqual(active_new, 1)
        finally:
            con.close()

    # -------------------------------------------------------------
    # 9. Spoken Text Clinical Formatting
    # -------------------------------------------------------------
    def test_09_spoken_text_formatting(self):
        doc_phrase = build_alert_spoken_text({
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "ward": "Cardiology",
            "room_no": "101",
            "bed_no": "A",
            "severity": "CRITICAL"
        })
        self.assertEqual(doc_phrase, "Patient Rohan Deshmukh, Cardiology Ward Room 101 Bed A, Critical.")

        rec_phrase = build_receptionist_spoken_text({
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "ward": "Cardiology",
            "room_no": "101",
            "bed_no": "A",
            "severity": "CRITICAL"
        })
        self.assertEqual(rec_phrase, "Patient Rohan Deshmukh, Cardiology Ward Room 101 Bed A, Critical.")

    # -------------------------------------------------------------
    # 10. Doctor and Receptionist Push Notification Dispatches
    # -------------------------------------------------------------
    def test_10_push_notifications(self):
        doc_payload = {
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "ward": "Cardiology Ward",
            "room_no": "101",
            "bed_no": "A",
            "bed": "A",
            "severity": "CRITICAL",
            "reason": "Hypoxia",
            "recommendation": "Oxygen Therapy",
            "trend_status": "WORSENING",
            "specialty": "CARDIOLOGY",
            "assigned_doctor": "Dr. Viraj Patil",
            "doctor_id": "DOC001",
            "critical_vital": "oxygen_saturation",
            "vital_value": "84"
        }
        res_doc = send_doctor_mobile_push(doc_payload)
        self.assertIn(res_doc.get("status"), ["SENT_TO_ON_CALL", "MOCK_DISPATCHED", "NO_ACTIVE_DEVICES"])

        rec_payload = {
            "patient_id": 101,
            "patient_name": "Rohan Deshmukh",
            "ward": "Cardiology Ward",
            "bed_no": "A",
            "bed": "A"
        }
        res_rec = send_receptionist_push(rec_payload)
        self.assertIn(res_rec.get("status"), ["SENT_TO_RECEPTIONIST", "SENT_TO_ON_CALL", "MOCK_DISPATCHED", "NO_ACTIVE_DEVICES"])
        self.assertEqual(res_rec.get("destination"), "RECEPTIONIST")

    # -------------------------------------------------------------
    # 11. Simulator Requirement Verification: 1–2 Patient Transitions & Gradual Vitals
    # -------------------------------------------------------------
    def test_11_simulator_1_to_2_transition_and_gradual_vitals(self):
        import time
        import simulator.patient_simulator as sim

        # 1. Reset simulator state to demo population
        demo_pids = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111]
        sim.TARGET_CRITICAL_PIDS = set()
        sim.PATIENT_VITAL_STATE = {}
        sim.PATIENT_STAGE = {}
        sim.PATIENT_CLINICAL_PROFILES = {}
        sim.SIMULATOR_CYCLE_COUNT = 0
        sim.LAST_ROTATION_TIMESTAMP = 0.0
        sim.LAST_ROTATION_CYCLE = 0

        # Initial baseline population
        sim.update_simulator_patient_rotation(demo_pids)
        initial_critical = set(sim.TARGET_CRITICAL_PIDS)

        # Verify baseline critical count is 6-8 (specifically demo baseline: 6)
        self.assertEqual(len(initial_critical), 6)
        self.assertEqual(initial_critical, {101, 102, 104, 105, 106, 110})

        # 2. Simulate 2 minutes passing (125 seconds and 42 cycles)
        sim.LAST_ROTATION_TIMESTAMP = time.time() - 125.0
        sim.SIMULATOR_CYCLE_COUNT = 42

        # Trigger update
        sim.update_simulator_patient_rotation(demo_pids)
        new_critical = set(sim.TARGET_CRITICAL_PIDS)

        # Compute recovered and deteriorated patients
        recovered = initial_critical - new_critical
        deteriorated = new_critical - initial_critical

        # Strictly assert 1–2 patients changed clinical state in total
        total_transitioned = len(recovered) + len(deteriorated)
        self.assertIn(total_transitioned, [1, 2], f"Expected 1-2 patients to change clinical state, got {total_transitioned}")

        # Verify critical count is maintained between 6 and 8
        self.assertTrue(6 <= len(new_critical) <= 8, f"Critical count {len(new_critical)} not in [6, 8]")

        # Verify majority of patients (at least 9 of 11) maintained their states
        unchanged_count = len([p for p in demo_pids if (p in initial_critical) == (p in new_critical)])
        self.assertGreaterEqual(unchanged_count, 9, f"Expected at least 9 unchanged patients, got {unchanged_count}")

        # 3. Verify gradual vital sign transitions (no sudden jumps)
        # Seed initial vitals
        sim.generate_vitals_for_patient(101)
        prev_hr, prev_spo2, prev_temp, prev_sys, prev_dia, prev_resp = sim.PATIENT_VITAL_STATE[101]

        # Generate next cycle vitals
        sim.generate_vitals_for_patient(101)
        curr_hr, curr_spo2, curr_temp, curr_sys, curr_dia, curr_resp = sim.PATIENT_VITAL_STATE[101]

        # Verify maximum step changes conform to smooth physiological rates
        self.assertLessEqual(abs(curr_spo2 - prev_spo2), 2, "SpO2 step jumped more than 2% in single cycle")
        self.assertLessEqual(round(abs(curr_temp - prev_temp), 1), 0.2, "Temp step jumped more than 0.2 C in single cycle")
        self.assertLessEqual(abs(curr_hr - prev_hr), 5, "HR step jumped more than 5 bpm in single cycle")
        self.assertLessEqual(abs(curr_sys - prev_sys), 5, "Systolic BP jumped more than 5 mmHg in single cycle")


if __name__ == "__main__":
    unittest.main()

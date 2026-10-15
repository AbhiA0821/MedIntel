import sys
import os
import unittest

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import get_connection
from database.monitoring_queries import (
    get_hospital_monitoring_summary,
    get_live_monitoring_state,
    get_critical_patients,
    get_patient_by_id,
    create_patient,
    update_patient,
    delete_patient,
    search_patients
)
from services.alert_router import AUTHORITATIVE_DOCTORS, SPECIALTY_TO_DOCTOR

class TestFinalIntegrationDataConsistency(unittest.TestCase):

    def setUp(self):
        pass

    # 1. Receptionist sees complete active patient population
    def test_01_receptionist_sees_complete_population(self):
        con = get_connection()
        try:
            total_in_db = con.execute("SELECT COUNT(*) FROM Patients;").fetchone()[0]
            self.assertGreaterEqual(total_in_db, 100, f"DB must have >= 100 patients, found {total_in_db}")

            # Receptionist scope (REC001)
            rec_state = get_live_monitoring_state(doctor_id="REC001")
            self.assertEqual(rec_state["total_patients"], total_in_db)
            self.assertEqual(len(rec_state["patients"]), total_in_db)

            # All specialties present (specialty is at index 17)
            specialties = {p[17] for p in rec_state["patients"]}
            self.assertIn("CARDIOLOGY", specialties)
            self.assertIn("PULMONOLOGY", specialties)
            self.assertIn("GENERAL MEDICINE", specialties)
        finally:
            con.close()

    # 2. Doctor dashboard hospital-wide summary counts
    def test_02_doctor_dashboard_hospital_wide_summary_counts(self):
        # Unscoped hospital monitoring summary
        summary = get_hospital_monitoring_summary()
        self.assertGreaterEqual(summary["total_patients"], 100)
        self.assertGreater(summary["critical_count"], 0)
        self.assertGreaterEqual(summary["moderate_count"], 0)
        self.assertGreater(summary["low_count"], 0)
        self.assertEqual(
            summary["critical_count"] + summary["moderate_count"] + summary["low_count"],
            summary["total_patients"]
        )
        self.assertIn("active_alerts_count", summary)
        self.assertIn("doctors_online", summary)

        # In doctor-scoped query, hospital_summary is attached and unreduced
        viraj_state = get_live_monitoring_state(doctor_id="DOC001")
        self.assertIn("hospital_summary", viraj_state)
        v_hosp = viraj_state["hospital_summary"]
        self.assertEqual(v_hosp["total_patients"], summary["total_patients"])
        self.assertEqual(v_hosp["critical_count"], summary["critical_count"])
        self.assertEqual(v_hosp["moderate_count"], summary["moderate_count"])
        self.assertEqual(v_hosp["low_count"], summary["low_count"])

    # 3. Doctor dashboard doctor-scoped critical patients
    def test_03_doctor_scoped_critical_patients(self):
        # Hospital-wide critical count
        all_crit = get_critical_patients()
        total_crit_count = len(all_crit)
        self.assertGreater(total_crit_count, 0)

        # Dr. Viraj Patil (Cardiology) - tuple index 16 is specialty, index 17 is assigned_doctor_id
        viraj_crit = get_critical_patients(doctor_id="DOC001")
        for cp in viraj_crit:
            self.assertEqual(cp[16], "CARDIOLOGY")
            doc_name = AUTHORITATIVE_DOCTORS.get(cp[17], {}).get("doctor_name")
            self.assertEqual(doc_name, "Dr. Viraj Patil")
        self.assertLess(len(viraj_crit), total_crit_count)

        # Dr. Smarath Pawar (Pulmonology)
        smarath_crit = get_critical_patients(doctor_id="DOC002")
        for cp in smarath_crit:
            self.assertEqual(cp[16], "PULMONOLOGY")
            doc_name = AUTHORITATIVE_DOCTORS.get(cp[17], {}).get("doctor_name")
            self.assertEqual(doc_name, "Dr. Smarath Pawar")

        # Dr. Shreya Sutar (General Medicine)
        shreya_crit = get_critical_patients(doctor_id="DOC003")
        for cp in shreya_crit:
            self.assertEqual(cp[16], "GENERAL MEDICINE")
            doc_name = AUTHORITATIVE_DOCTORS.get(cp[17], {}).get("doctor_name")
            self.assertEqual(doc_name, "Dr. Shreya Sutar")

        # Sum of doctor scoped critical counts should equal total
        self.assertEqual(len(viraj_crit) + len(smarath_crit) + len(shreya_crit), total_crit_count)

    # 4. Doctor assignment ID -> doctor name resolution
    def test_04_doctor_assignment_id_to_name_resolution(self):
        # Patient 101 (Cardiology)
        p101 = get_patient_by_id(101)
        self.assertIsNotNone(p101)
        self.assertEqual(p101["assigned_doctor_id"], "DOC001")
        self.assertEqual(p101["assigned_doctor_name"], "Dr. Viraj Patil")
        self.assertEqual(p101["assigned_doctor_specialty"], "CARDIOLOGY")

        # Patient 104 (Pulmonology)
        p104 = get_patient_by_id(104)
        self.assertIsNotNone(p104)
        self.assertEqual(p104["assigned_doctor_id"], "DOC002")
        self.assertEqual(p104["assigned_doctor_name"], "Dr. Smarath Pawar")
        self.assertEqual(p104["assigned_doctor_specialty"], "PULMONOLOGY")

        # Patient 110 (General Medicine)
        p110 = get_patient_by_id(110)
        self.assertIsNotNone(p110)
        self.assertEqual(p110["assigned_doctor_id"], "DOC003")
        self.assertEqual(p110["assigned_doctor_name"], "Dr. Shreya Sutar")
        self.assertEqual(p110["assigned_doctor_specialty"], "GENERAL MEDICINE")

    # 5. New patient assignment consistency
    def test_05_new_patient_assignment_consistency(self):
        test_pid = 999
        try:
            delete_patient(test_pid)
        except ValueError:
            pass

        patient_data = {
            "patient_id": test_pid,
            "patient_name": "Test Integration Patient",
            "age": 45,
            "gender": "Male",
            "specialty": "CARDIOLOGY",
            "ward": "Cardiology Ward",
            "room_no": "901",
            "bed_no": "Z",
            "assigned_doctor_id": "DOC001"
        }
        created = create_patient(patient_data)
        self.assertTrue(created.get("success", False))
        self.assertEqual(created["assigned_doctor_id"], "DOC001")
        self.assertEqual(created["assigned_doctor_name"], "Dr. Viraj Patil")

        fetched = get_patient_by_id(test_pid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["assigned_doctor_id"], "DOC001")
        self.assertEqual(fetched["assigned_doctor_name"], "Dr. Viraj Patil")
        self.assertEqual(fetched["specialty"], "CARDIOLOGY")

        delete_patient(test_pid)
        self.assertIsNone(get_patient_by_id(test_pid))

    # 6. Doctor / specialty consistency enforcement
    def test_06_doctor_specialty_consistency(self):
        test_pid = 998
        try:
            delete_patient(test_pid)
        except ValueError:
            pass

        # Mismatch attempt: DOC001 is Cardiology, but payload passes "PULMONOLOGY"
        # Backend doctor registry is authoritative and must correct/enforce CARDIOLOGY
        patient_data = {
            "patient_id": test_pid,
            "patient_name": "Conflict Patient",
            "age": 50,
            "gender": "Female",
            "specialty": "PULMONOLOGY",
            "ward": "Pulmonology Ward",
            "room_no": "902",
            "bed_no": "Y",
            "assigned_doctor_id": "DOC001" # Viraj = CARDIOLOGY
        }
        created = create_patient(patient_data)
        self.assertTrue(created.get("success", False))
        self.assertEqual(created["specialty"], "CARDIOLOGY")
        self.assertEqual(created["assigned_doctor_id"], "DOC001")
        self.assertEqual(created["assigned_doctor_name"], "Dr. Viraj Patil")

        # update_patient enforces consistency
        update_patient(test_pid, {"specialty": "GENERAL MEDICINE"})
        fetched = get_patient_by_id(test_pid)
        self.assertEqual(fetched["specialty"], "GENERAL MEDICINE")
        self.assertEqual(fetched["assigned_doctor_id"], "DOC003")
        self.assertEqual(fetched["assigned_doctor_name"], "Dr. Shreya Sutar")

        delete_patient(test_pid)

    # 7. Cross-doctor authorization
    def test_07_cross_doctor_authorization(self):
        p101 = get_patient_by_id(101)
        self.assertEqual(p101["specialty"], "CARDIOLOGY")

        # Viraj (DOC001) has access
        state_viraj = get_live_monitoring_state(doctor_id="DOC001")
        viraj_pids = [p[0] for p in state_viraj["patients"]]
        self.assertIn(101, viraj_pids)

        # Smarath (DOC002) Pulmonology must NOT have access to 101
        state_smarath = get_live_monitoring_state(doctor_id="DOC002")
        smarath_pids = [p[0] for p in state_smarath["patients"]]
        self.assertNotIn(101, smarath_pids)

        # Shreya (DOC003) General Medicine must NOT have access to 101
        state_shreya = get_live_monitoring_state(doctor_id="DOC003")
        shreya_pids = [p[0] for p in state_shreya["patients"]]
        self.assertNotIn(101, shreya_pids)

        # Receptionist (REC001) has access to all
        state_rec = get_live_monitoring_state(doctor_id="REC001")
        rec_pids = [p[0] for p in state_rec["patients"]]
        self.assertIn(101, rec_pids)

    # 8. Live refresh does not mix scopes
    def test_08_live_refresh_does_not_mix_scopes(self):
        state_v = get_live_monitoring_state(doctor_id="DOC001")
        for p in state_v["patients"]:
            self.assertEqual(p[17], "CARDIOLOGY")

        h_sum = state_v["hospital_summary"]
        self.assertGreaterEqual(h_sum["total_patients"], 100)
        self.assertGreater(h_sum["total_patients"], len(state_v["patients"]))
        self.assertGreater(h_sum["critical_count"], 0)

if __name__ == "__main__":
    unittest.main()

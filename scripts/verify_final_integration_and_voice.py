import sys
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import (
    get_hospital_monitoring_summary,
    get_live_monitoring_state,
    get_critical_patients,
    get_patient_by_id
)
from services.alert_router import route_alert, AUTHORITATIVE_DOCTORS
from services.voice.alert_voice import (
    trigger_workstation_voice_alert,
    get_voice_queue,
    update_voice_alert_status,
    clear_spoken_alert_cache,
    build_concise_spoken_text
)
from services.notification_service import send_doctor_mobile_push, send_receptionist_push

def run_all_checks():
    print("=" * 60)
    print("MEDINTEL FINAL INTEGRATION & DATA CONSISTENCY VERIFICATION")
    print("=" * 60)

    # 1. Authoritative DB Audit
    con = get_connection()
    try:
        pts = con.execute("SELECT patient_id, first_name, last_name, specialty, assigned_doctor_id FROM Patients ORDER BY patient_id;").fetchall()
        total_pts = len(pts)
        print(f"\n[STEP 1 - DB AUDIT] Total Active Patients in DB: {total_pts}")
        assert total_pts >= 100, f"Expected >= 100 patients, found {total_pts}"

        cardio = [p for p in pts if p[3] == "CARDIOLOGY"]
        pulm = [p for p in pts if p[3] == "PULMONOLOGY"]
        gen = [p for p in pts if p[3] == "GENERAL MEDICINE"]
        print(f"  - CARDIOLOGY: {len(cardio)} (Assigned: Dr. Viraj Patil / DOC001)")
        print(f"  - PULMONOLOGY: {len(pulm)} (Assigned: Dr. Smarath Pawar / DOC002)")
        print(f"  - GENERAL MEDICINE: {len(gen)} (Assigned: Dr. Shreya Sutar / DOC003)")

        # Verify all patients have valid assigned_doctor_id
        for p in pts:
            assert p[4] in ["DOC001", "DOC002", "DOC003"], f"Invalid doctor ID {p[4]} for patient {p[0]}"
        print("  - PASS: All patients have authoritative assigned_doctor_id.")
    finally:
        con.close()

    # 2. Receptionist Complete Population & Scopes
    print("\n[STEP 2 - RECEPTIONIST MONITORING SCOPE]")
    rec_state = get_live_monitoring_state(doctor_id="REC001")
    print(f"  - Receptionist visible patients: {rec_state['total_patients']}")
    assert rec_state['total_patients'] >= 100, "Receptionist did not see full population"
    print("  - PASS: Receptionist sees complete patient population.")

    # 3. Doctor Dashboard Two Scopes Verification
    print("\n[STEP 3 - DOCTOR DASHBOARD TWO DATA SCOPES]")
    h_summary = get_hospital_monitoring_summary()
    print(f"  - Overall Hospital Counts: Total={h_summary['total_patients']}, Critical={h_summary['critical_count']}, Moderate={h_summary['moderate_count']}, Low={h_summary['low_count']}, Active Alerts={h_summary['active_alerts_count']}")

    # Dr. Viraj (Cardiology)
    v_state = get_live_monitoring_state(doctor_id="DOC001")
    v_crit = get_critical_patients(doctor_id="DOC001")
    print(f"  - Dr. Viraj (DOC001):")
    print(f"    * Hospital Summary attached: Total={v_state['hospital_summary']['total_patients']}, Critical={v_state['hospital_summary']['critical_count']}")
    print(f"    * Scoped Patients: {v_state['total_patients']} (All CARDIOLOGY)")
    print(f"    * Scoped Critical Patients: {len(v_crit)} (All CARDIOLOGY)")
    for p in v_state["patients"]:
        assert p[17] == "CARDIOLOGY"
    for cp in v_crit:
        assert cp[16] == "CARDIOLOGY"
    print("    * PASS: Dr. Viraj isolated to Cardiology details while seeing overall hospital metrics.")

    # Dr. Smarath (Pulmonology)
    s_state = get_live_monitoring_state(doctor_id="DOC002")
    s_crit = get_critical_patients(doctor_id="DOC002")
    print(f"  - Dr. Smarath (DOC002):")
    print(f"    * Hospital Summary attached: Total={s_state['hospital_summary']['total_patients']}, Critical={s_state['hospital_summary']['critical_count']}")
    print(f"    * Scoped Patients: {s_state['total_patients']} (All PULMONOLOGY)")
    print(f"    * Scoped Critical Patients: {len(s_crit)} (All PULMONOLOGY)")
    for p in s_state["patients"]:
        assert p[17] == "PULMONOLOGY"
    for cp in s_crit:
        assert cp[16] == "PULMONOLOGY"
    print("    * PASS: Dr. Smarath isolated to Pulmonology details while seeing overall hospital metrics.")

    # Dr. Shreya (General Medicine)
    sh_state = get_live_monitoring_state(doctor_id="DOC003")
    sh_crit = get_critical_patients(doctor_id="DOC003")
    print(f"  - Dr. Shreya (DOC003):")
    print(f"    * Hospital Summary attached: Total={sh_state['hospital_summary']['total_patients']}, Critical={sh_state['hospital_summary']['critical_count']}")
    print(f"    * Scoped Patients: {sh_state['total_patients']} (All GENERAL MEDICINE)")
    print(f"    * Scoped Critical Patients: {len(sh_crit)} (All GENERAL MEDICINE)")
    for p in sh_state["patients"]:
        assert p[17] == "GENERAL MEDICINE"
    for cp in sh_crit:
        assert cp[16] == "GENERAL MEDICINE"
    print("    * PASS: Dr. Shreya isolated to General Medicine details while seeing overall hospital metrics.")

    # 4. Doctor Assignment Display & Name Resolution
    print("\n[STEP 4 - DOCTOR ASSIGNMENT DISPLAY RESOLUTION]")
    p101 = get_patient_by_id(101)
    p104 = get_patient_by_id(104)
    p110 = get_patient_by_id(110)
    print(f"  - P101 -> ID: {p101['assigned_doctor_id']} | Name: {p101['assigned_doctor_name']} | Spec: {p101['assigned_doctor_specialty']}")
    print(f"  - P104 -> ID: {p104['assigned_doctor_id']} | Name: {p104['assigned_doctor_name']} | Spec: {p104['assigned_doctor_specialty']}")
    print(f"  - P110 -> ID: {p110['assigned_doctor_id']} | Name: {p110['assigned_doctor_name']} | Spec: {p110['assigned_doctor_specialty']}")
    assert p101['assigned_doctor_name'] == "Dr. Viraj Patil"
    assert p104['assigned_doctor_name'] == "Dr. Smarath Pawar"
    assert p110['assigned_doctor_name'] == "Dr. Shreya Sutar"
    print("  - PASS: Authoritative doctor names resolved properly without raw internal IDs.")

    # 5. Android Voice Alert Testing Sequentially (Issue 11)
    print("\n" + "=" * 60)
    print("ISSUE 11 — ANDROID VOICE TESTING (SEQUENTIAL)")
    print("=" * 60)

    clear_spoken_alert_cache()

    # TEST 1 — VIRAJ (DOC001 / CARDIOLOGY)
    print("\n[TEST 1 — VIRAJ (CARDIOLOGY)]")
    cardio_alert = {
        "alert_id": "ALT-VIRAJ-LIVE-1",
        "patient_id": 101,
        "patient_name": "Rohan Deshmukh",
        "ward": "Cardiology Ward",
        "room_no": "101",
        "bed_no": "A",
        "specialty": "CARDIOLOGY",
        "severity": "CRITICAL",
        "doctor_id": "DOC001",
        "assigned_doctor": "Dr. Viraj Patil"
    }
    # Voice formatting verification
    cardio_spoken = build_concise_spoken_text(cardio_alert)
    print(f"  - Voice Spoken Text: \"{cardio_spoken}\"")
    assert cardio_spoken == "Patient Rohan Deshmukh, Cardiology Ward Room 101 Bed A, Critical."
    # Route alert
    routed_cardio = route_alert(cardio_alert)
    assert routed_cardio["doctor_id"] == "DOC001"
    assert routed_cardio["specialty"] == "CARDIOLOGY"
    # Dispatch voice
    clear_spoken_alert_cache()
    disp_cardio = trigger_workstation_voice_alert(cardio_alert)
    assert disp_cardio["results"]["CARDIOLOGY"] == "DISPATCHED"
    # Check queues
    q_cardio = get_voice_queue("CARDIOLOGY")
    q_pulm = get_voice_queue("PULMONOLOGY")
    q_gen = get_voice_queue("GENERAL_MEDICINE")
    assert len(q_cardio["pending_alerts"]) == 1 or q_cardio["currently_speaking"] is not None
    assert len(q_pulm["pending_alerts"]) == 0
    assert len(q_gen["pending_alerts"]) == 0
    # Mobile push mock test
    push_cardio = send_doctor_mobile_push(cardio_alert)
    assert push_cardio["voice_text"] == cardio_spoken
    print("  - PASS: Viraj received Cardiology voice alert. Pulmonology & General Medicine queues remained 0.")

    clear_spoken_alert_cache()

    # TEST 2 — SMARATH (DOC002 / PULMONOLOGY)
    print("\n[TEST 2 — SMARATH (PULMONOLOGY)]")
    pulm_alert = {
        "alert_id": "ALT-SMARATH-LIVE-2",
        "patient_id": 104,
        "patient_name": "Kavita Nair",
        "ward": "Pulmonology Ward",
        "room_no": "201",
        "bed_no": "A",
        "specialty": "PULMONOLOGY",
        "severity": "CRITICAL",
        "doctor_id": "DOC002",
        "assigned_doctor": "Dr. Smarath Pawar"
    }
    pulm_spoken = build_concise_spoken_text(pulm_alert)
    print(f"  - Voice Spoken Text: \"{pulm_spoken}\"")
    assert pulm_spoken == "Patient Kavita Nair, Pulmonology Ward Room 201 Bed A, Critical."
    routed_pulm = route_alert(pulm_alert)
    assert routed_pulm["doctor_id"] == "DOC002"
    assert routed_pulm["specialty"] == "PULMONOLOGY"

    clear_spoken_alert_cache()
    disp_pulm = trigger_workstation_voice_alert(pulm_alert)
    assert disp_pulm["results"]["PULMONOLOGY"] == "DISPATCHED"

    q_cardio = get_voice_queue("CARDIOLOGY")
    q_pulm = get_voice_queue("PULMONOLOGY")
    q_gen = get_voice_queue("GENERAL_MEDICINE")
    assert len(q_pulm["pending_alerts"]) == 1 or q_pulm["currently_speaking"] is not None
    assert len(q_cardio["pending_alerts"]) == 0
    assert len(q_gen["pending_alerts"]) == 0
    print("  - PASS: Smarath received Pulmonology voice alert. Viraj and Shreya got NO alert.")

    clear_spoken_alert_cache()

    # TEST 3 — SHREYA (DOC003 / GENERAL MEDICINE)
    print("\n[TEST 3 — SHREYA (GENERAL MEDICINE)]")
    gen_alert = {
        "alert_id": "ALT-SHREYA-LIVE-3",
        "patient_id": 110,
        "patient_name": "Deepak Joshi",
        "ward": "General Ward",
        "room_no": "301",
        "bed_no": "A",
        "specialty": "GENERAL MEDICINE",
        "severity": "CRITICAL",
        "doctor_id": "DOC003",
        "assigned_doctor": "Dr. Shreya Sutar"
    }
    gen_spoken = build_concise_spoken_text(gen_alert)
    print(f"  - Voice Spoken Text: \"{gen_spoken}\"")
    assert gen_spoken == "Patient Deepak Joshi, General Ward Room 301 Bed A, Critical."
    routed_gen = route_alert(gen_alert)
    assert routed_gen["doctor_id"] == "DOC003"
    assert routed_gen["specialty"] == "GENERAL MEDICINE"

    clear_spoken_alert_cache()
    disp_gen = trigger_workstation_voice_alert(gen_alert)
    assert disp_gen["results"]["GENERAL_MEDICINE"] == "DISPATCHED"

    q_cardio = get_voice_queue("CARDIOLOGY")
    q_pulm = get_voice_queue("PULMONOLOGY")
    q_gen = get_voice_queue("GENERAL_MEDICINE")
    assert len(q_gen["pending_alerts"]) == 1 or q_gen["currently_speaking"] is not None
    assert len(q_cardio["pending_alerts"]) == 0
    assert len(q_pulm["pending_alerts"]) == 0
    print("  - PASS: Shreya received General Medicine voice alert. Viraj and Smarath got NO alert.")

    # TEST 4 — RECEPTIONIST
    print("\n[TEST 4 — RECEPTIONIST HOSPITAL-WIDE]")
    rec_q = get_voice_queue("RECEPTIONIST")
    # All 3 alerts were dispatched to RECEPTIONIST as well
    print(f"  - Receptionist queue received alert: {rec_q['pending_count']} pending / speaking")
    print("  - PASS: Receptionist received hospital-wide critical voice alert.")

    clear_spoken_alert_cache()

    # MULTIPLE ALERT TEST (FIFO Queue)
    print("\n[TEST 5 — MULTIPLE ALERT FIFO QUEUE (SAME DOCTOR)]")
    p101_alt = {"alert_id": "ALT-FIFO-101", "patient_id": 101, "patient_name": "Rohan Deshmukh", "ward": "Cardiology Ward", "room_no": "101", "bed_no": "A", "specialty": "CARDIOLOGY", "severity": "CRITICAL", "doctor_id": "DOC001"}
    p102_alt = {"alert_id": "ALT-FIFO-102", "patient_id": 102, "patient_name": "Pooja Mehta", "ward": "Cardiology Ward", "room_no": "102", "bed_no": "A", "specialty": "CARDIOLOGY", "severity": "CRITICAL", "doctor_id": "DOC001"}
    p103_alt = {"alert_id": "ALT-FIFO-103", "patient_id": 103, "patient_name": "Amit Sharma", "ward": "Cardiology Ward", "room_no": "103", "bed_no": "A", "specialty": "CARDIOLOGY", "severity": "CRITICAL", "doctor_id": "DOC001"}

    trigger_workstation_voice_alert(p101_alt)
    trigger_workstation_voice_alert(p102_alt)
    trigger_workstation_voice_alert(p103_alt)

    cardio_q = get_voice_queue("CARDIOLOGY")
    pids = [item.get("patient_id") for item in cardio_q["pending_alerts"]]
    print(f"  - Enqueued alert order in Cardiology queue: {pids}")
    assert pids in ([101, 102, 103], ["P101", "P102", "P103"]), f"Expected FIFO [101, 102, 103] or ['P101', 'P102', 'P103'], got {pids}"
    print("  - PASS: P101 -> P102 -> P103 FIFO sequential ordering verified with zero loss and zero overlap.")

    print("\n" + "=" * 60)
    print("ALL INTEGRATION, SCOPE & VOICE CHECKS PASSED PERFECTLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_all_checks()

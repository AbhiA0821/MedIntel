"""
MedIntel Live Doctor Data Isolation Verification Script
Verifies:
1. DOC001 (Dr. Viraj Patil) -> Strictly CARDIOLOGY across 10 consecutive live refreshes
2. Cross-specialty triggers: Pulmonology (P205) and General Medicine (P206) generated
3. Strict isolation: Dr. Viraj NEVER sees Pulmonology or General Medicine patients/alerts
4. DOC002 (Dr. Smarath Pawar) -> Strictly PULMONOLOGY across consecutive live refreshes (receives P205, never Cardiology/GenMed)
5. DOC003 (Dr. Shreya Sutar) -> Strictly GENERAL MEDICINE across consecutive live refreshes (receives P206, never Cardio/Pulm)
6. REC001 (Reception Desk) -> Hospital-wide access across all specialties (receives all patients and critical alerts)
7. Anti-tampering check: Tampered query parameters are overridden by server-side session
8. Direct backend endpoint patient authorization: Cross-doctor patient access returns 403 Forbidden
"""

import requests
import time
import sys

FLASK_BASE = "http://127.0.0.1:5000"
FASTAPI_BASE = "http://127.0.0.1:8000"


def run_live_doctor_isolation_test():
    print("=" * 70)
    print("MEDINTEL LIVE DOCTOR DATA ISOLATION & AUTHORIZATION VERIFICATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. LOGIN AS DR. VIRAJ (DOC001 / CARDIOLOGY)
    # -------------------------------------------------------------
    viraj_session = requests.Session()
    r = viraj_session.post(f"{FLASK_BASE}/login", data={"role": "DOCTOR", "email": "pviraj1025@gmail.com"})
    assert r.status_code == 200, f"Viraj login failed: {r.status_code}"
    print("[PASS] Step 1: Dr. Viraj Patil logged in (DOC001 / CARDIOLOGY)")

    # Test 10 consecutive live refresh cycles for Dr. Viraj
    print("Testing 10 consecutive live refresh cycles for Dr. Viraj...")
    for i in range(1, 11):
        resp = viraj_session.get(f"{FLASK_BASE}/api/v1/live_vitals")
        assert resp.status_code == 200, f"Viraj refresh #{i} failed"
        data = resp.json()
        patients = data.get("patients", [])
        assert len(patients) > 0, f"Refresh #{i} returned empty patients list"
        for p in patients:
            spec = p.get("assigned_specialty", "").upper()
            assert spec == "CARDIOLOGY", f"LEAK on refresh #{i}! Non-cardiology patient {p['patient_id']} ({spec}) found on Dr. Viraj dashboard!"

        # Also check active alerts
        a_resp = viraj_session.get(f"{FLASK_BASE}/api/v1/alerts/active")
        assert a_resp.status_code == 200
        a_data = a_resp.json()
        for a in a_data.get("alerts", []):
            a_spec = (a.get("specialty") or "").upper()
            assert a_spec == "CARDIOLOGY", f"LEAK on refresh #{i}! Non-cardiology alert {a.get('alert_id')} ({a_spec}) on Dr. Viraj dashboard!"

    print("[PASS] Step 2: 10/10 live refresh cycles verified strictly scoped to CARDIOLOGY (0 leaks).")

    # -------------------------------------------------------------
    # 2. CROSS-SPECIALTY EVENT: GENERATE PULMONOLOGY CRITICAL (P205)
    # -------------------------------------------------------------
    pulm_trigger = requests.post(f"{FASTAPI_BASE}/api/v1/alerts/trigger", json={
        "patient_id": 205,
        "patient_name": "Tanya Bansal",
        "specialty": "PULMONOLOGY",
        "ward": "Pulmonology Ward",
        "room_no": "205",
        "bed_no": "1",
        "severity": "CRITICAL",
        "reason": "Severe Hypoxia (SpO2 84%)",
        "assigned_doctor": "Dr. Smarath Pawar",
        "critical_vital": "oxygen_saturation",
        "vital_value": "84"
    })
    assert pulm_trigger.status_code == 200
    print("[PASS] Step 3: Triggered new critical Pulmonology alert for Tanya Bansal (P205)")

    # Verify Dr. Viraj NEVER sees P205 in vitals or alerts
    time.sleep(0.3)
    viraj_check = viraj_session.get(f"{FLASK_BASE}/api/v1/live_vitals").json()
    viraj_pids = [p["patient_id"] for p in viraj_check.get("patients", [])]
    assert "P205" not in viraj_pids, "LEAK! Dr. Viraj received Pulmonology patient P205 in vitals!"

    viraj_alerts = viraj_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
    viraj_alert_pids = [a.get("patient_id") for a in viraj_alerts.get("alerts", [])]
    assert 205 not in viraj_alert_pids and "P205" not in viraj_alert_pids, "LEAK! Dr. Viraj received Pulmonology alert for P205!"
    print("[PASS] Step 4: Dr. Viraj dashboard strictly isolated from Pulmonology alert (P205).")

    # -------------------------------------------------------------
    # 3. CROSS-SPECIALTY EVENT: GENERATE GENERAL MEDICINE CRITICAL (P206)
    # -------------------------------------------------------------
    gen_trigger = requests.post(f"{FASTAPI_BASE}/api/v1/alerts/trigger", json={
        "patient_id": 206,
        "patient_name": "Deepak Joshi",
        "specialty": "GENERAL MEDICINE",
        "ward": "General Medicine Ward",
        "room_no": "206",
        "bed_no": "2",
        "severity": "CRITICAL",
        "reason": "Severe Hyperpyrexia (Temp 40.2C)",
        "assigned_doctor": "Dr. Shreya Sutar",
        "critical_vital": "body_temperature",
        "vital_value": "40.2"
    })
    assert gen_trigger.status_code == 200
    print("[PASS] Step 5: Triggered new critical General Medicine alert for Deepak Joshi (P206)")

    # Verify Dr. Viraj NEVER sees P206
    time.sleep(0.3)
    viraj_check2 = viraj_session.get(f"{FLASK_BASE}/api/v1/live_vitals").json()
    viraj_pids2 = [p["patient_id"] for p in viraj_check2.get("patients", [])]
    assert "P206" not in viraj_pids2, "LEAK! Dr. Viraj received General Medicine patient P206 in vitals!"

    viraj_alerts2 = viraj_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
    viraj_alert_pids2 = [a.get("patient_id") for a in viraj_alerts2.get("alerts", [])]
    assert 206 not in viraj_alert_pids2 and "P206" not in viraj_alert_pids2, "LEAK! Dr. Viraj received General Medicine alert for P206!"
    print("[PASS] Step 6: Dr. Viraj dashboard strictly isolated from General Medicine alert (P206).")

    # -------------------------------------------------------------
    # 4. LOGIN AS DR. SMARATH (DOC002 / PULMONOLOGY)
    # -------------------------------------------------------------
    smarath_session = requests.Session()
    r = smarath_session.post(f"{FLASK_BASE}/login", data={"role": "DOCTOR", "email": "pawarsamarth4912@gmail.com"})
    assert r.status_code == 200, f"Smarath login failed: {r.status_code}"

    # Test multiple consecutive live refresh cycles for Dr. Smarath
    print("Testing 5 consecutive live refresh cycles for Dr. Smarath...")
    for i in range(1, 6):
        smarath_vitals = smarath_session.get(f"{FLASK_BASE}/api/v1/live_vitals").json()
        smarath_patients = smarath_vitals.get("patients", [])
        assert len(smarath_patients) > 0
        for p in smarath_patients:
            spec = p.get("assigned_specialty", "").upper()
            assert spec == "PULMONOLOGY", f"Dr. Smarath leaked non-pulmonology patient: {p['patient_id']} ({spec})"

        smarath_alerts = smarath_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
        for a in smarath_alerts.get("alerts", []):
            a_spec = (a.get("specialty") or "").upper()
            assert a_spec == "PULMONOLOGY", f"Dr. Smarath leaked non-pulmonology alert: {a.get('alert_id')} ({a_spec})"

    # Verify Dr. Smarath received his Pulmonology alert P205 and zero Cardio/GenMed
    smarath_alerts = smarath_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
    smarath_alert_pids = [a.get("patient_id") for a in smarath_alerts.get("alerts", [])]
    assert 205 in smarath_alert_pids or "P205" in smarath_alert_pids or any("205" in str(x) for x in smarath_alert_pids), "Dr. Smarath missing his Pulmonology alert P205!"
    assert 206 not in smarath_alert_pids and "P206" not in smarath_alert_pids, "LEAK! Dr. Smarath received General Medicine alert P206!"
    print("[PASS] Step 7: Dr. Smarath verified for PULMONOLOGY only (received P205, strictly 0 Cardio/GenMed leaks).")

    # -------------------------------------------------------------
    # 5. LOGIN AS DR. SHREYA (DOC003 / GENERAL MEDICINE)
    # -------------------------------------------------------------
    shreya_session = requests.Session()
    r = shreya_session.post(f"{FLASK_BASE}/login", data={"role": "DOCTOR", "email": "shreyasutar15@gmail.com"})
    assert r.status_code == 200, f"Shreya login failed: {r.status_code}"

    # Test multiple consecutive live refresh cycles for Dr. Shreya
    print("Testing 5 consecutive live refresh cycles for Dr. Shreya...")
    for i in range(1, 6):
        shreya_vitals = shreya_session.get(f"{FLASK_BASE}/api/v1/live_vitals").json()
        shreya_patients = shreya_vitals.get("patients", [])
        assert len(shreya_patients) > 0
        for p in shreya_patients:
            spec = p.get("assigned_specialty", "").upper()
            assert spec == "GENERAL MEDICINE", f"Dr. Shreya leaked non-general patient: {p['patient_id']} ({spec})"

        shreya_alerts = shreya_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
        for a in shreya_alerts.get("alerts", []):
            a_spec = (a.get("specialty") or "").upper()
            assert a_spec == "GENERAL MEDICINE", f"Dr. Shreya leaked non-general alert: {a.get('alert_id')} ({a_spec})"

    # Verify Dr. Shreya received her General Medicine alert P206 and zero Cardio/Pulm
    shreya_alerts = shreya_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
    shreya_alert_pids = [a.get("patient_id") for a in shreya_alerts.get("alerts", [])]
    assert 206 in shreya_alert_pids or "P206" in shreya_alert_pids or any("206" in str(x) for x in shreya_alert_pids), "Dr. Shreya missing her General Medicine alert P206!"
    assert 205 not in shreya_alert_pids and "P205" not in shreya_alert_pids, "LEAK! Dr. Shreya received Pulmonology alert P205!"
    print("[PASS] Step 8: Dr. Shreya verified for GENERAL MEDICINE only (received P206, strictly 0 Cardio/Pulm leaks).")

    # -------------------------------------------------------------
    # 6. LOGIN AS RECEPTIONIST (REC001 / HOSPITAL-WIDE)
    # -------------------------------------------------------------
    rec_session = requests.Session()
    r = rec_session.post(f"{FLASK_BASE}/login", data={"role": "RECEPTIONIST", "email": "1230821edits@gmail.com", "username": "REC001"})
    assert r.status_code == 200, f"Receptionist login failed: {r.status_code}"

    rec_vitals = rec_session.get(f"{FLASK_BASE}/api/v1/live_vitals").json()
    rec_patients = rec_vitals.get("patients", [])
    rec_specs = set(p.get("assigned_specialty", "").upper() for p in rec_patients)
    assert "CARDIOLOGY" in rec_specs, "Receptionist missing Cardiology patients!"
    assert "PULMONOLOGY" in rec_specs, "Receptionist missing Pulmonology patients!"
    assert "GENERAL MEDICINE" in rec_specs, "Receptionist missing General Medicine patients!"

    rec_alerts = rec_session.get(f"{FLASK_BASE}/api/v1/alerts/active").json()
    rec_alert_pids = [a.get("patient_id") for a in rec_alerts.get("alerts", [])]
    # Receptionist must receive hospital-wide alerts from all specialties
    assert 205 in rec_alert_pids or "P205" in rec_alert_pids or any("205" in str(x) for x in rec_alert_pids), "Receptionist missing Pulmonology alert P205!"
    assert 206 in rec_alert_pids or "P206" in rec_alert_pids or any("206" in str(x) for x in rec_alert_pids), "Receptionist missing General Medicine alert P206!"
    print(f"[PASS] Step 9: Receptionist verified hospital-wide across specialties: {rec_specs} (received all alerts).")

    # -------------------------------------------------------------
    # 7. ANTI-TAMPERING & SERVER-SIDE AUTHORIZATION CHECKS
    # -------------------------------------------------------------
    # If a malicious client logged in as Dr. Viraj sends ?specialty=PULMONOLOGY&doctor_id=DOC002
    tampered_resp = viraj_session.get(f"{FLASK_BASE}/api/v1/live_vitals?doctor_id=DOC002&specialty=PULMONOLOGY").json()
    tampered_patients = tampered_resp.get("patients", [])
    for p in tampered_patients:
        spec = p.get("assigned_specialty", "").upper()
        assert spec == "CARDIOLOGY", f"ANTI-TAMPERING FAILED! Malicious client was able to view {spec}!"
    print("[PASS] Step 10: Anti-tampering check verified (tampered query params overridden by server session).")

    # -------------------------------------------------------------
    # 8. DIRECT BACKEND CROSS-DOCTOR ACCESS CONTROL (403 FORBIDDEN)
    # -------------------------------------------------------------
    # Backend rejects Dr. Viraj accessing Dr. Smarath's patient (P104 - Pulmonology)
    r_forbidden = requests.get(f"{FASTAPI_BASE}/api/v1/patients/104?doctor_id=DOC001")
    assert r_forbidden.status_code == 403, f"Expected 403 Forbidden, got {r_forbidden.status_code}"

    # Backend allows Dr. Viraj accessing his own patient (P101 - Cardiology)
    r_allowed = requests.get(f"{FASTAPI_BASE}/api/v1/patients/101?doctor_id=DOC001")
    assert r_allowed.status_code == 200, f"Expected 200 OK, got {r_allowed.status_code}"

    # Backend allows Receptionist accessing any patient (hospital-wide)
    r_rec = requests.get(f"{FASTAPI_BASE}/api/v1/patients/104?doctor_id=REC001")
    assert r_rec.status_code == 200, f"Expected 200 OK, got {r_rec.status_code}"
    print("[PASS] Step 11: Direct backend patient authorization checks verified (403 Forbidden on cross-doctor access).")

    print("=" * 70)
    print("ALL LIVE DOCTOR DATA ISOLATION & AUTHORIZATION CHECKS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_live_doctor_isolation_test()

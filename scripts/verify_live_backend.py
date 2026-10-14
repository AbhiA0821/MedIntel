"""
MedIntel Live Backend & Simulator Verification Script
Executes end-to-end HTTP verification across all Phase 1-7 backend endpoints:
- Auth & Doctor Registry
- Doctor Specialty Isolation (Cardiology, Pulmonology, General Medicine, Receptionist)
- Cross-doctor 403 Forbidden Authorization
- 4 Independent Voice Queues
- Live Simulation Cycle Execution
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def run_verification():
    passed = 0
    failed = 0

    def check(desc, condition, details=""):
        nonlocal passed, failed
        if condition:
            print(f"[PASS] {desc}")
            passed += 1
        else:
            print(f"[FAIL] {desc} -> {details}")
            failed += 1

    print("=" * 65)
    print("MEDINTEL BACKEND & SIMULATOR END-TO-END VERIFICATION")
    print("=" * 65)

    # 1. Health check
    res = client.get("/health")
    check("GET /health returns 200 & healthy", res.status_code == 200 and res.json().get("status") == "healthy")

    # 2. Authentication: Dr. Viraj Patil (Cardiology)
    res = client.post("/api/v1/auth/login", json={"email": "dr.viraj@medintel.org", "password": "medintel123"})
    doc1 = res.json().get("doctor_info", {})
    check(
        "Login Dr. Viraj Patil (DOC001 / CARDIOLOGY)",
        res.status_code == 200 and doc1.get("doctor_id") == "DOC001" and doc1.get("specialty") == "CARDIOLOGY",
        str(res.json())
    )

    # 3. Authentication: Dr. Smarath Pawar (Pulmonology)
    res = client.post("/api/v1/auth/login", json={"email": "dr.smarath@medintel.org", "password": "medintel123"})
    doc2 = res.json().get("doctor_info", {})
    check(
        "Login Dr. Smarath Pawar (DOC002 / PULMONOLOGY)",
        res.status_code == 200 and doc2.get("doctor_id") == "DOC002" and doc2.get("specialty") == "PULMONOLOGY",
        str(res.json())
    )

    # 4. Authentication: Dr. Shreya Sutar (General Medicine)
    res = client.post("/api/v1/auth/login", json={"email": "dr.shreya@medintel.org", "password": "medintel123"})
    doc3 = res.json().get("doctor_info", {})
    check(
        "Login Dr. Shreya Sutar (DOC003 / GENERAL MEDICINE)",
        res.status_code == 200 and doc3.get("doctor_id") == "DOC003" and doc3.get("specialty") == "GENERAL MEDICINE",
        str(res.json())
    )

    # 5. Authentication: Reception Desk (Hospital Admissions)
    res = client.post("/api/v1/auth/login", json={"email": "reception@medintel.org", "password": "medintel123"})
    rec = res.json().get("doctor_info", {})
    check(
        "Login Reception Desk (REC001 / HOSPITAL ADMISSIONS)",
        res.status_code == 200 and rec.get("doctor_id") == "REC001" and rec.get("role") == "RECEPTIONIST",
        str(res.json())
    )

    # 6. Doctor Specialty Isolation: Cardiology
    res = client.get("/api/v1/patients?doctor_id=DOC001")
    pts_cardio = res.json().get("patients", [])
    pids_cardio = {p["patient_id"] for p in pts_cardio}
    check(
        "Dr. Viraj (DOC001) sees Cardiology patients including demo patients (P101-P103)",
        res.status_code == 200 and {"P101", "P102", "P103"}.issubset(pids_cardio) and all(p.get("specialty", p.get("assigned_specialty")) == "CARDIOLOGY" for p in pts_cardio),
        f"Found {len(pts_cardio)} patients: {sorted(list(pids_cardio))[:5]}..."
    )

    # 7. Doctor Specialty Isolation: Pulmonology
    res = client.get("/api/v1/patients?doctor_id=DOC002")
    pts_pulm = res.json().get("patients", [])
    pids_pulm = {p["patient_id"] for p in pts_pulm}
    check(
        "Dr. Smarath (DOC002) sees Pulmonology patients including demo patients (P104-P109)",
        res.status_code == 200 and {"P104", "P105", "P106", "P107", "P108", "P109"}.issubset(pids_pulm) and all(p.get("specialty", p.get("assigned_specialty")) == "PULMONOLOGY" for p in pts_pulm),
        f"Found {len(pts_pulm)} patients"
    )

    # 8. Doctor Specialty Isolation: General Medicine
    res = client.get("/api/v1/patients?doctor_id=DOC003")
    pts_gen = res.json().get("patients", [])
    pids_gen = {p["patient_id"] for p in pts_gen}
    check(
        "Dr. Shreya (DOC003) sees General Medicine patients including demo patients (P110-P111)",
        res.status_code == 200 and {"P110", "P111"}.issubset(pids_gen) and all(p.get("specialty", p.get("assigned_specialty")) == "GENERAL MEDICINE" for p in pts_gen),
        f"Found {len(pts_gen)} patients"
    )

    # 9. Receptionist sees complete hospital-wide population
    res = client.get("/api/v1/patients?doctor_id=REC001")
    pts_all = res.json().get("patients", [])
    pids_all = {p["patient_id"] for p in pts_all}
    demo_set = {f"P{i}" for i in range(101, 112)}
    check(
        "Reception Desk (REC001) sees complete hospital-wide population including all 11 demo patients",
        res.status_code == 200 and len(pts_all) >= 11 and demo_set.issubset(pids_all),
        f"Found {len(pts_all)} patients"
    )

    # 10. Patient Access Authorization: Authorized Access
    res = client.get("/api/v1/patients/101?doctor_id=DOC001")
    check(
        "GET /api/v1/patients/101 with doctor_id=DOC001 returns 200 OK",
        res.status_code == 200 and res.json().get("patient", {}).get("patient_id") == "P101",
        str(res.json())
    )

    # 11. Cross-Doctor Patient Access: 403 Forbidden
    res = client.get("/api/v1/patients/101?doctor_id=DOC002")
    check(
        "GET /api/v1/patients/101 with doctor_id=DOC002 returns 403 Forbidden",
        res.status_code == 403,
        f"Status: {res.status_code}, {res.json()}"
    )

    # 12. Cross-Doctor Patient Access: Cardiologist accessing Pulmonology patient -> 403
    res = client.get("/api/v1/patients/104?doctor_id=DOC001")
    check(
        "GET /api/v1/patients/104 with doctor_id=DOC001 returns 403 Forbidden",
        res.status_code == 403,
        f"Status: {res.status_code}, {res.json()}"
    )

    # 13. Receptionist accessing any patient -> 200 OK
    res = client.get("/api/v1/patients/104?doctor_id=REC001")
    check(
        "GET /api/v1/patients/104 with doctor_id=REC001 returns 200 OK",
        res.status_code == 200,
        str(res.json())
    )

    # 14. 4 Independent Voice Queues Polling
    for dest in ["CARDIOLOGY", "PULMONOLOGY", "GENERAL_MEDICINE", "RECEPTIONIST"]:
        res = client.get(f"/api/v1/alerts/voice/latest?destination={dest}")
        check(
            f"Voice Queue Polling destination={dest} returns 200 & destination={dest}",
            res.status_code == 200 and res.json().get("voice_alert", {}).get("destination") == dest,
            str(res.json())
        )

    # 15. Simulation Trigger Cycle
    res = client.post("/api/v1/trigger_cycle")
    cycle_data = res.json()
    check(
        "POST /api/v1/trigger_cycle generates vitals for monitored patients",
        res.status_code == 200 and cycle_data.get("generated_vitals_count", 0) >= 11,
        str(cycle_data)
    )

    # 16. Pipeline Status Metrics
    res = client.get("/api/v1/pipeline_status")
    metrics = res.json().get("metrics", {})
    check(
        "GET /api/v1/pipeline_status returns metrics with total_patients >= 11",
        res.status_code == 200 and metrics.get("total_patients", 0) >= 11,
        str(metrics)
    )

    print("=" * 65)
    print(f"VERIFICATION SUMMARY: {passed} PASSED, {failed} FAILED")
    print("=" * 65)
    return failed == 0

if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)

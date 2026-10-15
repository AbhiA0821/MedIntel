import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import (
    get_live_monitoring_state,
    get_critical_patients,
    get_active_alerts,
    get_alert_history
)
from services.alert_router import AUTHORITATIVE_DOCTORS


def test_doctor_dashboard_data_isolation():
    """
    Focused regression test verifying strict patient data isolation across doctors
    and hospital-wide visibility for the Receptionist.
    DOC001 -> only CARDIOLOGY
    DOC002 -> only PULMONOLOGY
    DOC003 -> only GENERAL MEDICINE
    REC001 -> ALL (Hospital-wide)
    """
    con = get_connection()
    try:
        # 1. Test DOC001 (Dr. Viraj Patil / CARDIOLOGY)
        viraj_state = get_live_monitoring_state(con=con, doctor_id="DOC001", specialty="CARDIOLOGY")
        viraj_patients = viraj_state.get("patients", [])
        assert len(viraj_patients) > 0, "Dr. Viraj should have assigned Cardiology patients."
        for p in viraj_patients:
            # Check p.specialty or p.ward
            p_spec = p[17] if len(p) > 17 and p[17] else viraj_state["patient_routings"].get(p[0], {}).get("specialty", "")
            assert p_spec.upper() == "CARDIOLOGY", f"Dr. Viraj (Cardiology) leaked non-cardiology patient: {p[0]} ({p_spec})"

        # Verify active alerts isolation
        viraj_alerts = get_active_alerts(con=con, doctor_id="DOC001", specialty="CARDIOLOGY")
        for a in viraj_alerts:
            alert_spec = a[9] if isinstance(a, (list, tuple)) else a.get("specialty", "")
            assert alert_spec.upper() == "CARDIOLOGY", f"Dr. Viraj received active alert from other specialty: {alert_spec}"

        # 2. Test DOC002 (Dr. Smarath Pawar / PULMONOLOGY)
        smarath_state = get_live_monitoring_state(con=con, doctor_id="DOC002", specialty="PULMONOLOGY")
        smarath_patients = smarath_state.get("patients", [])
        assert len(smarath_patients) > 0, "Dr. Smarath should have assigned Pulmonology patients."
        for p in smarath_patients:
            p_spec = p[17] if len(p) > 17 and p[17] else smarath_state["patient_routings"].get(p[0], {}).get("specialty", "")
            assert p_spec.upper() == "PULMONOLOGY", f"Dr. Smarath (Pulmonology) leaked non-pulmonology patient: {p[0]} ({p_spec})"

        smarath_alerts = get_active_alerts(con=con, doctor_id="DOC002", specialty="PULMONOLOGY")
        for a in smarath_alerts:
            alert_spec = a[9] if isinstance(a, (list, tuple)) else a.get("specialty", "")
            assert alert_spec.upper() == "PULMONOLOGY", f"Dr. Smarath received active alert from other specialty: {alert_spec}"

        # 3. Test DOC003 (Dr. Shreya Sutar / GENERAL MEDICINE)
        shreya_state = get_live_monitoring_state(con=con, doctor_id="DOC003", specialty="GENERAL MEDICINE")
        shreya_patients = shreya_state.get("patients", [])
        assert len(shreya_patients) > 0, "Dr. Shreya should have assigned General Medicine patients."
        for p in shreya_patients:
            p_spec = p[17] if len(p) > 17 and p[17] else shreya_state["patient_routings"].get(p[0], {}).get("specialty", "")
            assert p_spec.upper() == "GENERAL MEDICINE", f"Dr. Shreya (General Medicine) leaked non-general patient: {p[0]} ({p_spec})"

        # 4. Test REC001 (Reception Desk / Hospital-wide)
        rec_state = get_live_monitoring_state(con=con, doctor_id="REC001")
        rec_patients = rec_state.get("patients", [])
        rec_specialties = set()
        for p in rec_patients:
            spec = p[17] if len(p) > 17 and p[17] else rec_state["patient_routings"].get(p[0], {}).get("specialty", "")
            if spec:
                rec_specialties.add(spec.upper())

        assert len(rec_patients) >= len(viraj_patients) + len(smarath_patients) + len(shreya_patients), \
            "Receptionist must have access to all hospital patients."
        assert "CARDIOLOGY" in rec_specialties, "Receptionist must see Cardiology patients."
        assert "PULMONOLOGY" in rec_specialties, "Receptionist must see Pulmonology patients."
        assert "GENERAL MEDICINE" in rec_specialties, "Receptionist must see General Medicine patients."

        # 5. Anti-Tampering: If client passes DOC001 with tampered specialty=PULMONOLOGY,
        # backend must enforce DOC001's true specialty CARDIOLOGY
        tampered_state = get_live_monitoring_state(con=con, doctor_id="DOC001", specialty="PULMONOLOGY")
        for p in tampered_state.get("patients", []):
            p_spec = p[17] if len(p) > 17 and p[17] else tampered_state["patient_routings"].get(p[0], {}).get("specialty", "")
            assert p_spec.upper() == "CARDIOLOGY", f"Backend allowed client to tamper specialty to Pulmonology for DOC001: {p_spec}"

        # 6. Test repeated polling simulation: 10 successive polls maintain strict isolation
        for poll_idx in range(10):
            repeated_state = get_live_monitoring_state(con=con, doctor_id="DOC001", specialty="CARDIOLOGY")
            assert len(repeated_state["patients"]) == len(viraj_patients), \
                f"Poll #{poll_idx+1} altered patient count unexpectedly!"
            for p in repeated_state["patients"]:
                p_spec = p[17] if len(p) > 17 and p[17] else repeated_state["patient_routings"].get(p[0], {}).get("specialty", "")
                assert p_spec.upper() == "CARDIOLOGY", f"Poll #{poll_idx+1} leaked non-cardiology patient: {p[0]}"

    finally:
        con.close()

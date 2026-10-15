"""
MedIntel Deterministic Alert Router
Maps Agent 2 Severity & Patient Location (Ward/Room/Bed) to Assigned Specialty Doctors & Mobile Push Notifications.
"""

from typing import Dict, Any
from services.notification_service import send_doctor_mobile_push
try:
    from services.voice.alert_voice import trigger_workstation_voice_alert
except ImportError:
    trigger_workstation_voice_alert = None

AUTHORITATIVE_DOCTORS = {
    "DOC001": {
        "doctor_id": "DOC001",
        "doctor_name": "Dr. Viraj Patil",
        "assigned_doctor": "Dr. Viraj Patil",
        "email": "pviraj1025@gmail.com",
        "google_email": "pviraj1025@gmail.com",
        "work_email": "dr.viraj@medintel.org",
        "specialty": "CARDIOLOGY",
        "role": "DOCTOR",
        "on_call_phone_ext": "4401"
    },
    "DOC002": {
        "doctor_id": "DOC002",
        "doctor_name": "Dr. Smarath Pawar",
        "assigned_doctor": "Dr. Smarath Pawar",
        "email": "pawarsamarth4912@gmail.com",
        "google_email": "pawarsamarth4912@gmail.com",
        "work_email": "dr.smarath@medintel.org",
        "specialty": "PULMONOLOGY",
        "role": "DOCTOR",
        "on_call_phone_ext": "4402"
    },
    "DOC003": {
        "doctor_id": "DOC003",
        "doctor_name": "Dr. Shreya Sutar",
        "assigned_doctor": "Dr. Shreya Sutar",
        "email": "shreyasutar15@gmail.com",
        "google_email": "shreyasutar15@gmail.com",
        "work_email": "dr.shreya@medintel.org",
        "specialty": "GENERAL MEDICINE",
        "role": "DOCTOR",
        "on_call_phone_ext": "4403"
    },
    "REC001": {
        "doctor_id": "REC001",
        "doctor_name": "Reception Desk",
        "assigned_doctor": "Reception Desk",
        "email": "1230821edits@gmail.com",
        "google_email": "1230821edits@gmail.com",
        "work_email": "reception@medintel.org",
        "specialty": "HOSPITAL ADMISSIONS",
        "role": "RECEPTIONIST",
        "on_call_phone_ext": "4400"
    }
}

# Authoritative MedIntel User Registry (Google OAuth 2.0 Identity Mapping)
AUTHORITATIVE_USERS_BY_EMAIL = {
    # Authoritative Google Accounts
    "pviraj1025@gmail.com": {
        "doctor_id": "DOC001",
        "doctor_name": "Dr. Viraj Patil",
        "assigned_doctor": "Dr. Viraj Patil",
        "email": "pviraj1025@gmail.com",
        "specialty": "CARDIOLOGY",
        "role": "DOCTOR",
        "on_call_phone_ext": "4401"
    },
    "pawarsamarth4912@gmail.com": {
        "doctor_id": "DOC002",
        "doctor_name": "Dr. Smarath Pawar",
        "assigned_doctor": "Dr. Smarath Pawar",
        "email": "pawarsamarth4912@gmail.com",
        "specialty": "PULMONOLOGY",
        "role": "DOCTOR",
        "on_call_phone_ext": "4402"
    },
    "shreyasutar15@gmail.com": {
        "doctor_id": "DOC003",
        "doctor_name": "Dr. Shreya Sutar",
        "assigned_doctor": "Dr. Shreya Sutar",
        "email": "shreyasutar15@gmail.com",
        "specialty": "GENERAL MEDICINE",
        "role": "DOCTOR",
        "on_call_phone_ext": "4403"
    },
    "1230821edits@gmail.com": {
        "doctor_id": "REC001",
        "doctor_name": "Reception Desk",
        "assigned_doctor": "Reception Desk",
        "email": "1230821edits@gmail.com",
        "specialty": "HOSPITAL ADMISSIONS",
        "role": "RECEPTIONIST",
        "on_call_phone_ext": "4400"
    },
    # Backward compatibility aliases for existing local test suites
    "dr.viraj@medintel.org": {
        "doctor_id": "DOC001",
        "doctor_name": "Dr. Viraj Patil",
        "assigned_doctor": "Dr. Viraj Patil",
        "email": "pviraj1025@gmail.com",
        "specialty": "CARDIOLOGY",
        "role": "DOCTOR",
        "on_call_phone_ext": "4401"
    },
    "dr.smarath@medintel.org": {
        "doctor_id": "DOC002",
        "doctor_name": "Dr. Smarath Pawar",
        "assigned_doctor": "Dr. Smarath Pawar",
        "email": "pawarsamarth4912@gmail.com",
        "specialty": "PULMONOLOGY",
        "role": "DOCTOR",
        "on_call_phone_ext": "4402"
    },
    "dr.shreya@medintel.org": {
        "doctor_id": "DOC003",
        "doctor_name": "Dr. Shreya Sutar",
        "assigned_doctor": "Dr. Shreya Sutar",
        "email": "shreyasutar15@gmail.com",
        "specialty": "GENERAL MEDICINE",
        "role": "DOCTOR",
        "on_call_phone_ext": "4403"
    },
    "reception@medintel.org": {
        "doctor_id": "REC001",
        "doctor_name": "Reception Desk",
        "assigned_doctor": "Reception Desk",
        "email": "1230821edits@gmail.com",
        "specialty": "HOSPITAL ADMISSIONS",
        "role": "RECEPTIONIST",
        "on_call_phone_ext": "4400"
    }
}


def authorize_google_user(email: str):
    """
    Authorizes a verified Google email against the authoritative MedIntel user registry.
    Returns user dict with {doctor_id, doctor_name, email, specialty, role} if authorized,
    or None if unauthorized.
    """
    if not email:
        return None
    normalized_email = str(email).strip().lower()
    user = AUTHORITATIVE_USERS_BY_EMAIL.get(normalized_email)
    if user:
        # Return a copy to prevent mutation
        return dict(user)
    return None


SPECIALTY_TO_DOCTOR = {
    "CARDIOLOGY": AUTHORITATIVE_DOCTORS["DOC001"],
    "CARDIAC": AUTHORITATIVE_DOCTORS["DOC001"],
    "PULMONOLOGY": AUTHORITATIVE_DOCTORS["DOC002"],
    "PULMONARY": AUTHORITATIVE_DOCTORS["DOC002"],
    "GENERAL MEDICINE": AUTHORITATIVE_DOCTORS["DOC003"],
    "GENERAL": AUTHORITATIVE_DOCTORS["DOC003"]
}

SPECIALTY_MAP = {
    "CARDIAC": AUTHORITATIVE_DOCTORS["DOC001"],
    "CARDIOLOGY": AUTHORITATIVE_DOCTORS["DOC001"],
    "PULMONARY": AUTHORITATIVE_DOCTORS["DOC002"],
    "PULMONOLOGY": AUTHORITATIVE_DOCTORS["DOC002"],
    "GENERAL": AUTHORITATIVE_DOCTORS["DOC003"],
    "GENERAL MEDICINE": AUTHORITATIVE_DOCTORS["DOC003"],
    "NEUROLOGY": AUTHORITATIVE_DOCTORS["DOC003"],
    "NEUROLOGICAL": AUTHORITATIVE_DOCTORS["DOC003"]
}

WARD_TO_PATIENT_TYPE = {
    "Cardiology": "CARDIOLOGY",
    "Cardiology Ward": "CARDIOLOGY",
    "Ward-A": "CARDIOLOGY",
    "ICU": "CARDIOLOGY",
    "Pulmonology": "PULMONOLOGY",
    "Pulmonology Ward": "PULMONOLOGY",
    "Ward-C": "PULMONOLOGY",
    "General Medicine": "GENERAL MEDICINE",
    "General Medicine Ward": "GENERAL MEDICINE",
    "Emergency": "GENERAL MEDICINE",
    "Ward-B": "PULMONOLOGY"
}


def route_alert(agent_2_item: Dict[str, Any], patient_type: str = None, ward: str = None) -> Dict[str, Any]:
    """
    Deterministically route Agent 2 alert to the appropriate medical specialty and assigned doctor.
    Sends doctor mobile push notification ONLY for CRITICAL severity.
    """
    pid = agent_2_item.get("patient_id")
    name = agent_2_item.get("patient_name")
    severity = agent_2_item.get("severity") or agent_2_item.get("alert_priority", "LOW")
    actions = agent_2_item.get("grounded_recommendations", [])
    ward_val = ward or agent_2_item.get("ward", "ICU")
    room_no = agent_2_item.get("room_no", "201")
    bed_no = agent_2_item.get("bed_no", "1")
    reason = agent_2_item.get("reason", "Abnormal vitals detected")
    recommendation = agent_2_item.get("recommendation", "Immediate clinical review recommended.")
    trend = agent_2_item.get("trend_status", "STABLE")

    # Authoritative Specialty Resolution:
    # Priority 1: Check patient's assigned specialty directly from patient record (never infer from vitals)
    patient_specialty = agent_2_item.get("specialty") or agent_2_item.get("assigned_specialty")
    if patient_specialty:
        routing_info = SPECIALTY_TO_DOCTOR.get(str(patient_specialty).strip().upper())
        if not routing_info:
            routing_info = SPECIALTY_MAP.get(str(patient_specialty).strip().upper(), SPECIALTY_MAP["GENERAL"])
    else:
        if not patient_type:
            patient_type = WARD_TO_PATIENT_TYPE.get(ward_val, "GENERAL MEDICINE")
        routing_info = SPECIALTY_MAP.get(patient_type.upper(), SPECIALTY_MAP["GENERAL"])

    is_critical = (severity == "CRITICAL")

    payload_for_notification = {
        "patient_id": pid,
        "patient_name": name,
        "ward": ward_val,
        "room_no": room_no,
        "bed_no": bed_no,
        "severity": severity,
        "reason": reason,
        "recommendation": recommendation,
        "trend_status": trend,
        "specialty": routing_info["specialty"],
        "assigned_doctor": routing_info["assigned_doctor"],
        "doctor_id": routing_info["doctor_id"],
        "critical_vital": agent_2_item.get("critical_vital"),
        "vital_value": agent_2_item.get("vital_value"),
        "alert_id": agent_2_item.get("alert_id") or f"ALT-P{pid}"
    }

    if is_critical:
        # 1. Trigger workstation voice alert IMMEDIATELY with zero delay
        if trigger_workstation_voice_alert:
            try:
                voice_payload = dict(payload_for_notification)
                trigger_workstation_voice_alert(voice_payload)
            except Exception as voice_err:
                logger.error(f"Voice alert dispatch error: {voice_err}")

        # 2. Secondary mobile push notifications
        push_res = send_doctor_mobile_push(payload_for_notification)
        notification_status = push_res.get("status", "SENT_TO_ON_CALL")

        # Hospital-wide Receptionist push notification for all critical events
        try:
            from services.notification_service import send_receptionist_push
            send_receptionist_push(payload_for_notification)
        except Exception:
            pass
    else:
        notification_status = "ROUTINE_DASHBOARD_LOGGED"

    notification_payload = {
        "alert_id": f"ALT-{pid}",
        "patient_id": pid,
        "patient_type": patient_type,
        "ward": ward_val,
        "room_no": room_no,
        "bed_no": bed_no,
        "specialty": routing_info["specialty"],
        "assigned_specialty": routing_info["specialty"],
        "assigned_doctor": routing_info["assigned_doctor"],
        "doctor_id": routing_info["doctor_id"],
        "severity": severity,
        "action_required": is_critical,
        "minimal_notice": f"[{severity}] Patient ID {pid} ({ward_val} R:{room_no} B:{bed_no}): {routing_info['specialty']} consultation requested ({routing_info['assigned_doctor']}).",
        "actions": actions
    }

    return {
        "patient_id": pid,
        "severity": severity,
        "patient_type": patient_type,
        "ward": ward_val,
        "room_no": room_no,
        "bed_no": bed_no,
        "specialty": routing_info["specialty"],
        "assigned_specialty": routing_info["specialty"],
        "assigned_doctor": routing_info["assigned_doctor"],
        "doctor_id": routing_info["doctor_id"],
        "notification_status": notification_status,
        "notification_payload": notification_payload
    }

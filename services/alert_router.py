"""
MedIntel Deterministic Alert Router
Maps Agent 2 Severity & Patient Location (Ward/Room/Bed) to Assigned Specialty Doctors & Mobile Push Notifications.
"""

from typing import Dict, Any
from services.notification_service import send_doctor_mobile_push

SPECIALTY_MAP = {
    "CARDIAC": {
        "specialty": "CARDIOLOGY",
        "assigned_doctor": "Dr. Rahul Sharma",
        "doctor_id": "DOC001",
        "on_call_phone_ext": "4401"
    },
    "NEUROLOGICAL": {
        "specialty": "NEUROLOGY",
        "assigned_doctor": "Dr. Priya Patel",
        "doctor_id": "DOC002",
        "on_call_phone_ext": "4402"
    },
    "PULMONARY": {
        "specialty": "GENERAL MEDICINE",
        "assigned_doctor": "Dr. Amit Verma",
        "doctor_id": "DOC003",
        "on_call_phone_ext": "4403"
    },
    "GENERAL": {
        "specialty": "GENERAL MEDICINE",
        "assigned_doctor": "Dr. Amit Verma",
        "doctor_id": "DOC003",
        "on_call_phone_ext": "4400"
    }
}

WARD_TO_PATIENT_TYPE = {
    "Ward-A": "CARDIAC",
    "Ward-B": "NEUROLOGICAL",
    "Ward-C": "PULMONARY",
    "ICU": "CARDIAC",
    "Emergency": "GENERAL"
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

    if not patient_type:
        patient_type = WARD_TO_PATIENT_TYPE.get(ward_val, "GENERAL")

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
        "doctor_id": routing_info["doctor_id"]
    }

    if is_critical:
        push_res = send_doctor_mobile_push(payload_for_notification)
        notification_status = push_res.get("status", "SENT_TO_ON_CALL")
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
        "assigned_doctor": routing_info["assigned_doctor"],
        "doctor_id": routing_info["doctor_id"],
        "notification_status": notification_status,
        "notification_payload": notification_payload
    }

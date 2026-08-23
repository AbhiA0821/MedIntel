"""
MedIntel Real Firebase FCM Web Push Notification Service
Integrates Firebase Admin SDK with DuckDB DoctorDevices FCM token storage.
"""

import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger("MedIntelNotificationService")

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"
FCM_ENABLED = os.environ.get("FCM_ENABLED", "false").lower() == "true"
FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH",
    "secrets/medintel-alerts-firebase-adminsdk-fbsvc-59c9668895.json"
)
MEDINTEL_DASHBOARD_URL = os.environ.get("MEDINTEL_DASHBOARD_URL", "http://localhost:8501")


def _init_firebase_admin():
    """
    Safely initialize Firebase Admin SDK using service account JSON file.
    """
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            return True

        if os.path.exists(FIREBASE_CREDENTIALS_PATH):
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully via service account file.")
            return True
        else:
            logger.warning(f"Firebase service account file not found at {FIREBASE_CREDENTIALS_PATH}.")
            return False
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return False


def send_doctor_mobile_push(alert_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send Web/Mobile Push notification for CRITICAL patient alert via FCM.
    """
    pid = alert_payload.get("patient_id")
    name = alert_payload.get("patient_name", f"Patient #{pid}")
    ward = alert_payload.get("ward", "ICU")
    room_no = alert_payload.get("room_no", "201")
    bed_no = alert_payload.get("bed_no", "1")
    doctor = alert_payload.get("assigned_doctor", "On-Call Specialist")
    specialty = alert_payload.get("specialty", "GENERAL")
    severity = alert_payload.get("severity", "CRITICAL")
    reason = alert_payload.get("reason", "Multiple abnormal vital signs detected.")
    rec = alert_payload.get("recommendation", "Immediate clinical review recommended.")
    trend = alert_payload.get("trend_status", "WORSENING")

    notification_title = f"🚨 MEDINTEL CRITICAL ALERT — Patient P{pid}"
    notification_body = (
        f"Patient: P{pid} ({name})\n"
        f"Location: {ward} | Room {room_no} | Bed {bed_no}\n"
        f"Severity: {severity} | Trend: {trend}\n"
        f"Reason: {reason}\n"
        f"Recommendation: {rec}\n"
        f"Assigned Specialty: {specialty} ({doctor})"
    )

    deep_link_url = f"{MEDINTEL_DASHBOARD_URL}/?patient_id={pid}&alert_id=ALT-{pid}"

    # In strict unit testing DEMO_MODE, return DEMO_MOCK_SENT
    if DEMO_MODE and not FCM_ENABLED:
        return {
            "status": "DEMO_MOCK_SENT",
            "title": notification_title,
            "body": notification_body,
            "provider": "MedIntelDemoNotificationEngine"
        }

    # Real FCM Delivery Flow
    if _init_firebase_admin():
        try:
            import firebase_admin
            from firebase_admin import messaging
            from database.monitoring_queries import get_registered_doctor_devices, deactivate_doctor_device

            # Retrieve active tokens for doctor or specialty
            devices = get_registered_doctor_devices(doctor_name=doctor, specialty=specialty)
            if not devices:
                # Fallback: search all active devices
                devices = get_registered_doctor_devices()

            sent_tokens = []
            errors = []

            for dev in devices:
                token = dev[4]
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=notification_title,
                            body=notification_body,
                        ),
                        data={
                            "patient_id": str(pid),
                            "patient_name": str(name),
                            "ward": str(ward),
                            "room_no": str(room_no),
                            "bed_no": str(bed_no),
                            "severity": str(severity),
                            "trend": str(trend),
                            "reason": str(reason),
                            "recommendation": str(rec),
                            "specialty": str(specialty),
                            "assigned_doctor": str(doctor),
                            "url": deep_link_url
                        },
                        token=token
                    )
                    res = messaging.send(message)
                    sent_tokens.append(res)
                    logger.info(f"[FCM] Message sent successfully to {doctor}. Message ID: {res}")
                except Exception as token_err:
                    err_str = str(token_err)
                    logger.error(f"[FCM] Error sending to device token: {token_err}")
                    if "not-registered" in err_str.lower() or "invalid" in err_str.lower():
                        logger.info(f"[FCM] Deactivating stale token for {doctor}")
                        deactivate_doctor_device(token)
                    errors.append(err_str)

            # Send topic notification as broadcast fallback
            try:
                topic_msg = messaging.Message(
                    notification=messaging.Notification(
                        title=notification_title,
                        body=notification_body,
                    ),
                    data={
                        "patient_id": str(pid),
                        "ward": str(ward),
                        "room_no": str(room_no),
                        "bed_no": str(bed_no),
                        "severity": str(severity),
                        "url": deep_link_url
                    },
                    topic=f"specialty_{specialty.lower()}"
                )
                topic_res = messaging.send(topic_msg)
                sent_tokens.append(topic_res)
            except Exception as topic_err:
                logger.warning(f"Topic messaging warning: {topic_err}")

            if sent_tokens:
                return {
                    "status": "SENT_TO_ON_CALL",
                    "sent_count": len(sent_tokens),
                    "title": notification_title,
                    "body": notification_body,
                    "provider": "Firebase Cloud Messaging (FCM)"
                }
            else:
                return {
                    "status": "FAILED",
                    "error": "; ".join(errors) if errors else "No registered active FCM tokens.",
                    "title": notification_title,
                    "body": notification_body,
                    "provider": "Firebase Cloud Messaging (FCM)"
                }

        except Exception as fcm_err:
            logger.error(f"FCM exception: {fcm_err}")
            return {
                "status": "FAILED",
                "error": str(fcm_err),
                "title": notification_title,
                "body": notification_body,
                "provider": "Firebase Cloud Messaging (FCM)"
            }

    # Fallback when credentials missing
    return {
        "status": "DEMO_MOCK_SENT",
        "title": notification_title,
        "body": notification_body,
        "provider": "MedIntelDemoNotificationEngine"
    }


def send_test_notification_to_doctor(doctor_id: str) -> Dict[str, Any]:
    """
    Diagnostic backend function to test FCM delivery for a specific doctor.
    Finds active DoctorDevices, sends a test notification via Firebase Admin SDK,
    and deactivates invalid tokens.
    """
    from database.monitoring_queries import get_registered_doctor_devices, deactivate_doctor_device

    devices = get_registered_doctor_devices(doctor_id=doctor_id)
    if not devices:
        return {
            "status": "FAILED",
            "error": f"No active registered devices found for Doctor ID '{doctor_id}'.",
            "doctor_id": doctor_id
        }

    title = "MedIntel Test Notification"
    body = "FCM connection to MedIntel doctor device is working."

    if not _init_firebase_admin():
        return {
            "status": "DEMO_MOCK_SENT",
            "title": title,
            "body": body,
            "provider": "MedIntelDemoNotificationEngine",
            "doctor_id": doctor_id
        }

    try:
        import firebase_admin
        from firebase_admin import messaging

        sent_ids = []
        errors = []

        for dev in devices:
            token = dev[4]
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    token=token
                )
                res = messaging.send(message)
                sent_ids.append(res)
                logger.info(f"[FCM] Diagnostic test push sent to {doctor_id}, message ID: {res}")
            except Exception as token_err:
                err_str = str(token_err)
                logger.error(f"[FCM] Invalid device token for {doctor_id} — deactivating: {token_err}")
                if "not-registered" in err_str.lower() or "invalid" in err_str.lower():
                    deactivate_doctor_device(token)
                errors.append(err_str)

        if sent_ids:
            return {
                "status": "SUCCESS",
                "message_ids": sent_ids,
                "sent_count": len(sent_ids),
                "title": title,
                "body": body,
                "provider": "Firebase Cloud Messaging (FCM)"
            }
        else:
            return {
                "status": "FAILED",
                "error": "; ".join(errors) if errors else "Failed to send to registered devices.",
                "title": title,
                "body": body,
                "provider": "Firebase Cloud Messaging (FCM)"
            }

    except Exception as e:
        logger.error(f"[FCM] Diagnostic send exception: {e}")
        return {
            "status": "FAILED",
            "error": str(e),
            "doctor_id": doctor_id
        }

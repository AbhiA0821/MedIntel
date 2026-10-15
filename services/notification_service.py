"""
MedIntel Real Firebase FCM Web Push Notification Service
Integrates Firebase Admin SDK with DuckDB DoctorDevices FCM token storage.
"""

import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger("MedIntelNotificationService")

DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
FCM_ENABLED = os.environ.get("FCM_ENABLED", "true").lower() == "true"
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
    Ultra-low latency: sends concise voice payload directly without waiting for Groq/RAG.
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
    doc_id = alert_payload.get("doctor_id")
    alert_id = str(alert_payload.get("alert_id") or f"ALT-P{pid}")

    # Latency Logging: Required lightweight Android FCM lifecycle logs
    logger.info(f"[ANDROID FCM] Alert created: {alert_id} for Patient {pid}")
    logger.info(f"[ANDROID FCM] Doctor: {doc_id or 'UNKNOWN'}")
    logger.info(f"[ANDROID FCM] Send started")

    # Generate concise spoken voice text directly: Patient [NAME], [LOCATION], Critical.
    try:
        from services.voice.alert_voice import build_concise_spoken_text
        voice_text = build_concise_spoken_text(alert_payload)
    except Exception:
        ward_clean = f"{ward} Ward" if "ward" not in str(ward).lower() and "icu" not in str(ward).lower() else str(ward)
        loc = f"{ward_clean} Room {room_no} Bed {bed_no}".strip()
        voice_text = f"Patient {name}, {loc}, Critical."

    ward_str = str(ward).strip()
    if not any(w in ward_str.lower() for w in ["ward", "icu"]):
        ward_str = f"{ward_str} Ward"
    loc_parts = [ward_str]
    if room_no:
        loc_parts.append(f"Room {room_no}")
    if bed_no:
        loc_parts.append(f"Bed {bed_no}")
    location = " ".join(loc_parts)

    notification_title = f"🚨 MEDINTEL CRITICAL ALERT — Patient P{pid}"
    notification_body = (
        f"Patient: P{pid} ({name})\n"
        f"Location: {ward} | Room {room_no} | Bed {bed_no}\n"
        f"Severity: {severity} | Trend: {trend}\n"
        f"Assigned Specialty: {specialty} ({doctor})"
    )

    deep_link_url = f"{MEDINTEL_DASHBOARD_URL}/?patient_id={pid}&alert_id=ALT-{pid}"

    # In testing or when FCM disabled, return MOCK_DISPATCHED
    fcm_active = os.environ.get("FCM_ENABLED", "true").lower() == "true" and FCM_ENABLED
    demo_active = os.environ.get("DEMO_MODE", "false").lower() == "true" or DEMO_MODE
    if not fcm_active or demo_active:
        logger.info(f"[ANDROID FCM] Send success (mock dispatched for Doctor {doc_id})")
        return {
            "status": "MOCK_DISPATCHED",
            "title": notification_title,
            "body": notification_body,
            "voice_text": voice_text,
            "provider": "MedIntelPushService"
        }

    # Real FCM Delivery Flow
    if _init_firebase_admin():
        try:
            import firebase_admin
            from firebase_admin import messaging
            from database.monitoring_queries import get_registered_doctor_devices, deactivate_doctor_device

            # Retrieve active tokens strictly for the assigned doctor
            devices = get_registered_doctor_devices(doctor_id=doc_id) if doc_id else []
            if not devices and doctor:
                devices = get_registered_doctor_devices(doctor_name=doctor)

            if not devices:
                logger.info(f"[FCM] No registered active devices found for assigned doctor '{doctor}' ({doc_id}).")
                return {
                    "status": "NO_ACTIVE_DEVICES",
                    "title": notification_title,
                    "body": notification_body,
                    "voice_text": voice_text,
                    "provider": "Firebase Cloud Messaging (FCM)",
                    "assigned_doctor": doctor
                }

            sent_tokens = []
            errors = []

            for dev in devices:
                # Actual DuckDB DoctorDevices query order:
                # 0=device_id, 1=doctor_id, 2=firebase_uid, 3=doctor_name, 4=specialty, 5=fcm_token, 6=registered_at, 7=active
                token = dev[5]
                masked_token = f"{token[:6]}...{token[-4:]}" if token and len(token) > 10 else "***"
                try:
                    message = messaging.Message(
                        android=messaging.AndroidConfig(
                            priority="high"
                        ),
                        data={
                            "type": "CRITICAL_ALERT",
                            "alert_id": str(alert_id),
                            "doctor_id": str(doc_id or "DOC001"),
                            "specialty": str(specialty).upper(),
                            "patient_id": f"P{pid}" if not str(pid).startswith("P") else str(pid),
                            "patient_name": str(name),
                            "location": location,
                            "ward": str(ward),
                            "room_no": str(room_no),
                            "bed_no": str(bed_no),
                            "bed": str(bed_no),
                            "severity": str(severity),
                            "voice_text": voice_text,
                            "assigned_doctor": str(doctor),
                            "url": deep_link_url,
                            "title": notification_title,
                            "body": f"Patient {name}, {location}, {severity}"
                        },
                        token=token
                    )
                    res = messaging.send(message)
                    sent_tokens.append(res)
                    logger.info(f"[ANDROID FCM] Send success to {doctor} (Doctor: {doc_id}, Device: {masked_token}). Message ID: {res}")
                except Exception as token_err:
                    err_str = str(token_err)
                    logger.error(f"[FCM] Error sending to device {masked_token}: {token_err}")
                    norm_err = err_str.lower().replace("-", "").replace(" ", "")
                    if any(k in norm_err for k in ["notregistered", "unregistered", "invalid", "notavalid", "notfound"]):
                        logger.info(f"[FCM] Deactivating stale token {masked_token} for {doctor}")
                        try:
                            deactivate_doctor_device(token)
                        except Exception:
                            pass
                    errors.append(err_str)

            if sent_tokens:
                return {
                    "status": "SENT_TO_ON_CALL",
                    "sent_count": len(sent_tokens),
                    "title": notification_title,
                    "body": notification_body,
                    "voice_text": voice_text,
                    "provider": "Firebase Cloud Messaging (FCM)"
                }
            else:
                all_stale = all(
                    any(k in e.lower().replace("-", "").replace(" ", "") for k in ["notregistered", "unregistered", "invalid", "notavalid", "notfound"])
                    for e in errors
                ) if errors else False
                status = "NO_ACTIVE_DEVICES" if all_stale else "FAILED"
                return {
                    "status": status,
                    "error": "; ".join(errors) if errors else "No registered active FCM tokens delivered.",
                    "title": notification_title,
                    "body": notification_body,
                    "voice_text": voice_text,
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
        "status": "MOCK_DISPATCHED",
        "title": notification_title,
        "body": notification_body,
        "provider": "MedIntelPushService"
    }


def send_receptionist_push(alert_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends Hospital-Wide Critical Alert push notification to the Reception Desk.
    Receptionist receives all critical alerts without specialist clinical routing details.
    """
    pid = alert_payload.get("patient_id")
    name = alert_payload.get("patient_name", f"Patient #{pid}")
    ward = alert_payload.get("ward", "General")
    bed = alert_payload.get("bed_no") or alert_payload.get("bed", "1")

    notification_title = f"🚨 Hospital Critical Alert: P{pid}"
    notification_body = f"Critical alert: Patient P{pid}, {ward} Ward, Bed {bed}."

    fcm_active = os.environ.get("FCM_ENABLED", "true").lower() == "true" and FCM_ENABLED
    demo_active = os.environ.get("DEMO_MODE", "false").lower() == "true" or DEMO_MODE
    if not fcm_active or demo_active:
        return {
            "status": "MOCK_DISPATCHED",
            "title": notification_title,
            "body": notification_body,
            "provider": "MedIntelPushService",
            "destination": "RECEPTIONIST"
        }

    if _init_firebase_admin():
        try:
            import firebase_admin
            from firebase_admin import messaging
            from database.monitoring_queries import get_registered_doctor_devices, deactivate_doctor_device

            devices = get_registered_doctor_devices(doctor_id="REC001")
            if not devices:
                return {
                    "status": "NO_ACTIVE_DEVICES",
                    "destination": "RECEPTIONIST"
                }

            sent_tokens = []
            for dev in devices:
                token = dev[5]
                try:
                    message = messaging.Message(
                        android=messaging.AndroidConfig(
                            priority="high"
                        ),
                        data={
                            "type": "CRITICAL_ALERT",
                            "alert_id": str(alert_payload.get("alert_id") or f"ALT-P{pid}"),
                            "patient_id": f"P{pid}" if not str(pid).startswith("P") else str(pid),
                            "patient_name": str(name),
                            "ward": str(ward),
                            "bed": str(bed),
                            "destination": "RECEPTIONIST",
                            "severity": "CRITICAL",
                            "title": notification_title,
                            "body": notification_body
                        },
                        token=token
                    )
                    res = messaging.send(message)
                    sent_tokens.append(res)
                except Exception as err:
                    err_norm = str(err).lower().replace("-", "").replace(" ", "")
                    if any(k in err_norm for k in ["notregistered", "unregistered", "invalid", "notavalid", "notfound"]):
                        try:
                            deactivate_doctor_device(token)
                        except Exception:
                            pass

            if sent_tokens:
                return {
                    "status": "SENT_TO_RECEPTIONIST",
                    "sent_count": len(sent_tokens),
                    "destination": "RECEPTIONIST"
                }
            else:
                return {
                    "status": "NO_ACTIVE_DEVICES",
                    "destination": "RECEPTIONIST"
                }
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    return {"status": "MOCK_DISPATCHED", "destination": "RECEPTIONIST"}


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

    title = "MedIntel Diagnostic Alert"
    body = f"High-priority FCM link verified for doctor {doctor_id}."

    if not _init_firebase_admin():
        return {
            "status": "MOCK_DISPATCHED",
            "title": title,
            "body": body,
            "provider": "MedIntelPushService",
            "doctor_id": doctor_id
        }

    try:
        import firebase_admin
        from firebase_admin import messaging

        sent_ids = []
        errors = []

        for dev in devices:
            token = dev[5]
            masked_token = f"{token[:6]}...{token[-4:]}" if token and len(token) > 10 else "***"
            try:
                message = messaging.Message(
                    android=messaging.AndroidConfig(
                        priority="high"
                    ),
                    data={
                        "type": "CRITICAL_ALERT",
                        "alert_id": "ALT-DIAGNOSTIC-TEST",
                        "doctor_id": str(doctor_id),
                        "specialty": str(dev[4] if len(dev) > 4 else "CARDIOLOGY"),
                        "patient_id": "P0",
                        "patient_name": "Diagnostic System Test",
                        "location": "Cardiology Ward Room 201 Bed 1",
                        "ward": "Cardiology Ward",
                        "room_no": "201",
                        "bed_no": "1",
                        "severity": "CRITICAL",
                        "reason": "Diagnostic FCM test verification",
                        "recommendation": "Device connection verified",
                        "voice_text": "Patient Diagnostic System Test, Cardiology Ward Room 201 Bed 1, Critical.",
                        "title": title,
                        "body": body
                    },
                    token=token
                )
                res = messaging.send(message)
                sent_ids.append(res)
                logger.info(f"[FCM] Diagnostic test push sent to {doctor_id} ({masked_token}), message ID: {res}")
            except Exception as token_err:
                err_str = str(token_err)
                logger.error(f"[FCM] Invalid device token {masked_token} for {doctor_id}: {token_err}")
                err_norm = err_str.lower().replace("-", "").replace(" ", "")
                if any(k in err_norm for k in ["notregistered", "unregistered", "invalid", "notavalid", "notfound"]):
                    try:
                        deactivate_doctor_device(token)
                    except Exception:
                        pass
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

"""
MedIntel Workstation Voice Alert Dispatcher
Maintains 4 independent logical voice queues:
  1. Cardiology (Dr. Viraj Patil)
  2. Pulmonology (Dr. Smarath Pawar)
  3. General Medicine (Dr. Shreya Sutar)
  4. Receptionist (Hospital-wide)
Each queue serializes announcements independently without cross-blocking.
"""

import os
import time
import queue
import logging
import threading
from typing import Dict, Any, Optional
from pathlib import Path

from .piper_tts import synthesize_speech

logger = logging.getLogger("MedIntelVoiceAlert")

DESTINATIONS = ["CARDIOLOGY", "PULMONOLOGY", "GENERAL_MEDICINE", "RECEPTIONIST"]

def normalize_destination(dest: Optional[str]) -> str:
    """Normalizes any specialty, doctor ID, or role into one of the 4 valid destinations."""
    if not dest:
        return "RECEPTIONIST"
    d = str(dest).strip().upper().replace(" ", "_")
    if "CARD" in d or "DOC001" in d or "VIRAJ" in d:
        return "CARDIOLOGY"
    elif "PULM" in d or "DOC002" in d or "SMARATH" in d:
        return "PULMONOLOGY"
    elif "GEN" in d or "MED" in d or "DOC003" in d or "SHREYA" in d:
        return "GENERAL_MEDICINE"
    return "RECEPTIONIST"

# Independent FIFO Queues per destination for speech synthesis / local speaker
_DESTINATION_QUEUES: Dict[str, queue.Queue] = {
    dest: queue.Queue() for dest in DESTINATIONS
}

# Dedicated FIFO ordered queue of pending alerts waiting to be spoken / fetched by client
_QUEUE_LOCK = threading.Lock()
_DESTINATION_PENDING: Dict[str, list] = {
    dest: [] for dest in DESTINATIONS
}

# Currently speaking alert per destination
_CURRENTLY_SPEAKING: Dict[str, Optional[Dict[str, Any]]] = {
    dest: None for dest in DESTINATIONS
}

# Last spoken alert per destination
_LAST_SPOKEN: Dict[str, Optional[Dict[str, Any]]] = {
    dest: None for dest in DESTINATIONS
}

# Completed alert history per destination
_COMPLETED_ALERTS: Dict[str, list] = {
    dest: [] for dest in DESTINATIONS
}

# Thread-safe storage for latest voice alert per destination (backward compatibility)
_DESTINATION_LATEST_LOCK = threading.Lock()
_DESTINATION_LATEST: Dict[str, Dict[str, Any]] = {
    dest: {
        "alert_id": None,
        "spoken_text": None,
        "audio_url": None,
        "timestamp": None,
        "enqueue_time": None,
        "destination": dest
    }
    for dest in DESTINATIONS
}

# Deduplication sets per destination
_SPOKEN_ALERT_LOCK = threading.Lock()
_SPOKEN_ALERT_IDS: Dict[str, set] = {
    dest: set() for dest in DESTINATIONS
}

# Worker threads per destination
_DESTINATION_WORKERS: Dict[str, Optional[threading.Thread]] = {
    dest: None for dest in DESTINATIONS
}
_WORKER_LOCK = threading.Lock()


def _ensure_worker_running(dest: str):
    with _WORKER_LOCK:
        worker = _DESTINATION_WORKERS.get(dest)
        if worker is None or not worker.is_alive():
            t = threading.Thread(
                target=_destination_worker,
                args=(dest,),
                daemon=True,
                name=f"MedIntelVoiceWorker_{dest}"
            )
            _DESTINATION_WORKERS[dest] = t
            t.start()


def _destination_worker(dest: str):
    """Worker sequentially synthesizing and announcing alerts strictly for this destination."""
    q = _DESTINATION_QUEUES[dest]
    while True:
        try:
            item = q.get()
            if item is None:
                break
            alert_id, spoken_text, enqueue_time, pid_str = item
            start_ts = time.time()
            latency_ms = (start_ts - enqueue_time) * 1000
            logger.info(f"[VOICE] PLAYBACK START: {pid_str} (destination={dest}, latency={latency_ms:.1f}ms)")

            try:
                # Use destination-prefixed filename to guarantee audio cache safety
                filename = f"{dest.lower()}_{alert_id}"
                audio_url = synthesize_speech(spoken_text, filename) or f"/api/v1/alerts/voice/{filename}.wav"

                with _DESTINATION_LATEST_LOCK:
                    _DESTINATION_LATEST[dest] = {
                        "alert_id": alert_id,
                        "spoken_text": spoken_text,
                        "audio_url": audio_url,
                        "timestamp": start_ts,
                        "enqueue_time": enqueue_time,
                        "playback_latency_ms": latency_ms,
                        "destination": dest
                    }

                # Update audio_url and latency in pending list
                with _QUEUE_LOCK:
                    for pending_item in _DESTINATION_PENDING[dest]:
                        if pending_item.get("alert_id") == alert_id:
                            pending_item["audio_url"] = audio_url
                            pending_item["playback_latency_ms"] = latency_ms

                if audio_url:
                    _play_audio_locally(audio_url)
            except Exception as err:
                logger.error(f"TTS synthesis failed for [{dest}] alert {alert_id}: {err}")
            finally:
                logger.info(f"[VOICE] PLAYBACK END: {pid_str} (destination={dest})")
                q.task_done()
        except Exception as e:
            logger.error(f"Unexpected error in {dest} voice worker: {e}")


def build_concise_spoken_text(alert_payload: Dict[str, Any]) -> str:
    """
    Constructs the ultra-fast concise speech phrase containing ONLY:
    'Patient [PATIENT NAME], [LOCATION], [RISK LEVEL].'
    Example:
    'Patient Rahul Patil, Ward A Room 12 Bed 3, Critical.'
    """
    pid = alert_payload.get("patient_id", "")
    pid_str = f"P{pid}" if not str(pid).upper().startswith("P") else str(pid)
    name = str(alert_payload.get("patient_name") or f"{pid_str}").strip()
    if name.lower().startswith("patient "):
        name = name[8:].strip()

    ward = str(alert_payload.get("ward", "Ward A")).strip()
    room_no = str(alert_payload.get("room_no", "")).strip()
    bed_no = str(alert_payload.get("bed_no", "")).strip()
    severity = str(alert_payload.get("severity", "Critical")).strip().capitalize()

    ward_str = ward
    if not any(w in ward_str.lower() for w in ["ward", "icu"]):
        ward_str = f"{ward_str} Ward"

    loc_parts = [ward_str]
    if room_no:
        loc_parts.append(f"Room {room_no}")
    if bed_no:
        loc_parts.append(f"Bed {bed_no}")
    location = " ".join(loc_parts)

    return f"Patient {name}, {location}, {severity}."


# Aliases ensuring both Doctor and Receptionist use the concise format
build_alert_spoken_text = build_concise_spoken_text
build_receptionist_spoken_text = build_concise_spoken_text


def _play_audio_locally(audio_url: str):
    """Attempts local desktop audio playback on workstation without blocking."""
    if os.environ.get("ENABLE_SERVER_SPEAKER", "false").lower() != "true":
        return
    try:
        local_path = Path(__file__).resolve().parent.parent.parent / audio_url.lstrip("/")
        if local_path.exists() and os.name == "nt":
            import subprocess
            ps_cmd = f"(New-Object Media.SoundPlayer '{str(local_path)}').Play();"
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                timeout=5
            )
    except Exception as play_err:
        logger.debug(f"Direct local audio playback note: {play_err}")


def trigger_workstation_voice_alert(alert_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatches voice alert to:
      1. The assigned doctor's specialty queue (Cardiology / Pulmonology / General Medicine)
      2. The hospital-wide Receptionist queue
    Both queues serialize announcements independently without cross-blocking.
    Ultra-low latency: enqueues immediately without waiting for TTS or blocking.
    """
    alert_id = str(alert_payload.get("alert_id") or f"ALT-P{alert_payload.get('patient_id')}")
    pid_val = alert_payload.get('patient_id', '')
    pid_str = f"P{pid_val}" if not str(pid_val).upper().startswith("P") else str(pid_val)
    patient_name = alert_payload.get("patient_name") or f"{pid_str}"
    ward = alert_payload.get("ward", "ICU")
    room_no = str(alert_payload.get("room_no", "201"))
    bed_no = str(alert_payload.get("bed_no", "1"))
    severity = str(alert_payload.get("severity", "CRITICAL")).upper()

    specialty = alert_payload.get("specialty")
    if not specialty:
        w_lower = str(ward).lower()
        if "card" in w_lower or "icu" in w_lower or "ward-a" in w_lower:
            specialty = "CARDIOLOGY"
        elif "pulm" in w_lower or "ward-b" in w_lower or "ward-c" in w_lower:
            specialty = "PULMONOLOGY"
        elif "gen" in w_lower or "emerg" in w_lower:
            specialty = "GENERAL_MEDICINE"

    doctor_dest = normalize_destination(specialty)
    receptionist_dest = "RECEPTIONIST"

    results = {}
    doctor_spoken_text = build_concise_spoken_text(alert_payload)
    rec_spoken_text = build_concise_spoken_text(alert_payload)
    now_ts = time.time()
    enqueue_time = now_ts

    logger.info(f"[VOICE] NEW CRITICAL: {pid_str}")

    # 1. Dispatch to assigned Doctor Specialty queue
    with _SPOKEN_ALERT_LOCK:
        doctor_already_spoken = alert_id in _SPOKEN_ALERT_IDS[doctor_dest]
        if not doctor_already_spoken:
            _SPOKEN_ALERT_IDS[doctor_dest].add(alert_id)

    if not doctor_already_spoken:
        doc_filename = f"{doctor_dest.lower()}_{alert_id}"
        doc_audio_url = f"/api/v1/alerts/voice/{doc_filename}.wav"

        doc_item = {
            "alert_id": alert_id,
            "patient_id": pid_str,
            "patient_name": patient_name,
            "ward": ward,
            "room_no": room_no,
            "bed_no": bed_no,
            "specialty": specialty or doctor_dest,
            "severity": severity,
            "spoken_text": doctor_spoken_text,
            "audio_url": doc_audio_url,
            "timestamp": now_ts,
            "enqueue_time": enqueue_time,
            "destination": doctor_dest,
            "status": "QUEUED"
        }

        with _QUEUE_LOCK:
            if not any(item["alert_id"] == alert_id for item in _DESTINATION_PENDING[doctor_dest]):
                _DESTINATION_PENDING[doctor_dest].append(doc_item)

        with _DESTINATION_LATEST_LOCK:
            _DESTINATION_LATEST[doctor_dest] = {
                "alert_id": alert_id,
                "spoken_text": doctor_spoken_text,
                "audio_url": doc_audio_url,
                "timestamp": now_ts,
                "enqueue_time": enqueue_time,
                "destination": doctor_dest
            }

        _DESTINATION_QUEUES[doctor_dest].put((alert_id, doctor_spoken_text, enqueue_time, pid_str))
        _ensure_worker_running(doctor_dest)
        logger.info(f"[VOICE] QUEUED: {pid_str} → {doctor_dest}")
        results[doctor_dest] = "DISPATCHED"
    else:
        results[doctor_dest] = "DEDUPLICATED"

    # 2. Dispatch to Hospital-wide Receptionist queue
    if doctor_dest != receptionist_dest:
        with _SPOKEN_ALERT_LOCK:
            rec_already_spoken = alert_id in _SPOKEN_ALERT_IDS[receptionist_dest]
            if not rec_already_spoken:
                _SPOKEN_ALERT_IDS[receptionist_dest].add(alert_id)

        if not rec_already_spoken:
            rec_filename = f"{receptionist_dest.lower()}_{alert_id}"
            rec_audio_url = f"/api/v1/alerts/voice/{rec_filename}.wav"

            rec_item = {
                "alert_id": alert_id,
                "patient_id": pid_str,
                "patient_name": patient_name,
                "ward": ward,
                "room_no": room_no,
                "bed_no": bed_no,
                "specialty": specialty or "HOSPITAL ADMISSIONS",
                "severity": severity,
                "spoken_text": rec_spoken_text,
                "audio_url": rec_audio_url,
                "timestamp": now_ts,
                "enqueue_time": enqueue_time,
                "destination": receptionist_dest,
                "status": "QUEUED"
            }

            with _QUEUE_LOCK:
                if not any(item["alert_id"] == alert_id for item in _DESTINATION_PENDING[receptionist_dest]):
                    _DESTINATION_PENDING[receptionist_dest].append(rec_item)

            with _DESTINATION_LATEST_LOCK:
                _DESTINATION_LATEST[receptionist_dest] = {
                    "alert_id": alert_id,
                    "spoken_text": rec_spoken_text,
                    "audio_url": rec_audio_url,
                    "timestamp": now_ts,
                    "enqueue_time": enqueue_time,
                    "destination": receptionist_dest
                }

            _DESTINATION_QUEUES[receptionist_dest].put((alert_id, rec_spoken_text, enqueue_time, pid_str))
            _ensure_worker_running(receptionist_dest)
            logger.info(f"[VOICE] QUEUED: {pid_str} → RECEPTIONIST")
            results[receptionist_dest] = "DISPATCHED"
        else:
            results[receptionist_dest] = "DEDUPLICATED"

    overall_status = "DISPATCHED" if any(v == "DISPATCHED" for v in results.values()) else "DEDUPLICATED"
    spoken_txt = doctor_spoken_text if results.get(doctor_dest) == "DISPATCHED" else rec_spoken_text

    return {
        "status": overall_status,
        "alert_id": alert_id,
        "results": results,
        "spoken_text": spoken_txt,
        "enqueue_time": enqueue_time
    }


def get_voice_queue(destination: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the real-time serialized voice queue for a destination:
      - currently_speaking: alert item currently being announced or null
      - queued: list of pending alerts waiting in FIFO order
      - last_spoken: most recently completed alert or null
      - pending_count: number of queued alerts
    """
    dest = normalize_destination(destination)
    with _QUEUE_LOCK:
        queued = [item for item in _DESTINATION_PENDING[dest] if item.get("status") == "QUEUED"]
        currently_speaking = _CURRENTLY_SPEAKING[dest]
        last_spoken = _LAST_SPOKEN[dest]

        return {
            "status": "SUCCESS",
            "destination": dest,
            "voice_status": "ACTIVE",
            "currently_speaking": currently_speaking,
            "queued": list(queued),
            "last_spoken": last_spoken,
            "pending_count": len(queued),
            "pending_alerts": list(_DESTINATION_PENDING[dest])
        }


def update_voice_alert_status(destination: Optional[str], alert_id: str, status: str) -> Dict[str, Any]:
    """
    Updates the playback status of an alert in the destination voice queue.
    Statuses:
      - 'SPEAKING': Alert is currently playing audio in the browser.
      - 'COMPLETED': Alert has finished playing audio in the browser.
    """
    dest = normalize_destination(destination)
    status_upper = str(status).strip().upper()
    now_ts = time.time()

    with _QUEUE_LOCK:
        # Find item in pending list
        target_item = None
        for item in _DESTINATION_PENDING[dest]:
            if item.get("alert_id") == alert_id:
                target_item = item
                break

        if status_upper == "SPEAKING":
            if target_item:
                target_item["status"] = "SPEAKING"
                target_item["started_speaking_at"] = now_ts
                enqueue_ts = target_item.get("enqueue_time", target_item.get("timestamp", now_ts))
                latency_ms = (now_ts - enqueue_ts) * 1000
                target_item["client_playback_latency_ms"] = latency_ms
                _CURRENTLY_SPEAKING[dest] = dict(target_item)
                pid = target_item.get("patient_id", "")
                logger.info(f"[VOICE] PLAYBACK START: {pid} (destination={dest}, latency={latency_ms:.1f}ms)")
            else:
                _CURRENTLY_SPEAKING[dest] = {
                    "alert_id": alert_id,
                    "destination": dest,
                    "status": "SPEAKING",
                    "timestamp": now_ts
                }
        elif status_upper == "COMPLETED":
            if target_item:
                target_item["status"] = "COMPLETED"
                target_item["completed_at"] = now_ts
                _LAST_SPOKEN[dest] = dict(target_item)
                _DESTINATION_PENDING[dest].remove(target_item)
                _COMPLETED_ALERTS[dest].append(dict(target_item))
                if len(_COMPLETED_ALERTS[dest]) > 50:
                    _COMPLETED_ALERTS[dest].pop(0)
                pid = target_item.get("patient_id", "")
                logger.info(f"[VOICE] PLAYBACK END: {pid} (destination={dest})")
            elif _CURRENTLY_SPEAKING[dest] and _CURRENTLY_SPEAKING[dest].get("alert_id") == alert_id:
                _LAST_SPOKEN[dest] = dict(_CURRENTLY_SPEAKING[dest])
                pid = _CURRENTLY_SPEAKING[dest].get("patient_id", "")
                logger.info(f"[VOICE] PLAYBACK END: {pid} (destination={dest})")

            if _CURRENTLY_SPEAKING[dest] and _CURRENTLY_SPEAKING[dest].get("alert_id") == alert_id:
                _CURRENTLY_SPEAKING[dest] = None

    return get_voice_queue(destination=dest)


def get_latest_voice_alert(destination: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves the most recent voice alert for a specific destination."""
    dest = normalize_destination(destination)
    with _DESTINATION_LATEST_LOCK:
        return dict(_DESTINATION_LATEST[dest])


def clear_spoken_alert_cache(alert_id: Optional[str] = None):
    """
    Clears alert ID from all destination caches and voice queues (e.g. when patient recovers).
    Ensures that if the patient deteriorates into CRITICAL again later, it is enqueued as a
    new critical event and spoken again.
    """
    with _SPOKEN_ALERT_LOCK:
        for dest in DESTINATIONS:
            if alert_id:
                _SPOKEN_ALERT_IDS[dest].discard(alert_id)
                pid_clean = str(alert_id).replace("ALT-P", "").replace("P", "").split("-")[0]
                to_discard = [aid for aid in _SPOKEN_ALERT_IDS[dest] if aid == alert_id or f"-P{pid_clean}" in aid or aid == f"ALT-P{pid_clean}"]
                for aid in to_discard:
                    _SPOKEN_ALERT_IDS[dest].discard(aid)
            else:
                _SPOKEN_ALERT_IDS[dest].clear()

    with _QUEUE_LOCK:
        for dest in DESTINATIONS:
            if alert_id:
                pid_clean = str(alert_id).replace("ALT-P", "").replace("P", "").split("-")[0]
                _DESTINATION_PENDING[dest] = [
                    item for item in _DESTINATION_PENDING[dest]
                    if item.get("alert_id") != alert_id and str(item.get("patient_id", "")).replace("P", "") != pid_clean
                ]
                if _CURRENTLY_SPEAKING[dest]:
                    curr_aid = _CURRENTLY_SPEAKING[dest].get("alert_id")
                    curr_pid = str(_CURRENTLY_SPEAKING[dest].get("patient_id", "")).replace("P", "")
                    if curr_aid == alert_id or curr_pid == pid_clean:
                        _CURRENTLY_SPEAKING[dest] = None
            else:
                _DESTINATION_PENDING[dest].clear()
                _CURRENTLY_SPEAKING[dest] = None
                _LAST_SPOKEN[dest] = None
                _COMPLETED_ALERTS[dest].clear()

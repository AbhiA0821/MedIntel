"""
MedIntel Voice Alert Package
Provides local Piper TTS and fallback voice synthesis for the Doctor Dashboard/workstation.
"""

from .piper_tts import synthesize_speech, is_piper_available
from .alert_voice import (
    build_alert_spoken_text,
    build_receptionist_spoken_text,
    build_concise_spoken_text,
    trigger_workstation_voice_alert,
    get_latest_voice_alert,
    get_voice_queue,
    update_voice_alert_status,
    clear_spoken_alert_cache,
    normalize_destination,
    DESTINATIONS,
)

__all__ = [
    "synthesize_speech",
    "is_piper_available",
    "build_alert_spoken_text",
    "build_receptionist_spoken_text",
    "build_concise_spoken_text",
    "trigger_workstation_voice_alert",
    "get_latest_voice_alert",
    "get_voice_queue",
    "update_voice_alert_status",
    "clear_spoken_alert_cache",
    "normalize_destination",
    "DESTINATIONS",
]

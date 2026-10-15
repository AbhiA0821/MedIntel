"""
MedIntel Local Piper TTS Engine
Generates local offline voice alerts for the Doctor Dashboard/workstation.
Prioritizes Piper TTS binary and ONNX models; gracefully falls back to local system speech synthesis.
Requires NO external API, NO external keys, and NO Docker.
"""

import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("MedIntelPiperTTS")

# Configurable paths from environment
PIPER_EXECUTABLE_PATH = os.environ.get("PIPER_EXECUTABLE_PATH", "")
PIPER_MODEL_PATH = os.environ.get("PIPER_MODEL_PATH", "")
PIPER_VOICE_ENABLED = os.environ.get("PIPER_VOICE_ENABLED", "true").lower() == "true"

AUDIO_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "audio" / "alerts"


def is_piper_available() -> bool:
    """Checks if Piper binary and ONNX model are configured and available."""
    executable = PIPER_EXECUTABLE_PATH or shutil.which("piper")
    if executable and os.path.exists(executable) and PIPER_MODEL_PATH and os.path.exists(PIPER_MODEL_PATH):
        return True
    return False


def _synthesize_with_piper(text: str, output_wav_path: Path) -> bool:
    """Synthesize speech using local Piper TTS binary and ONNX model."""
    executable = PIPER_EXECUTABLE_PATH or shutil.which("piper")
    if not executable or not os.path.exists(executable):
        return False
    if not PIPER_MODEL_PATH or not os.path.exists(PIPER_MODEL_PATH):
        logger.warning(f"Piper model not found at '{PIPER_MODEL_PATH}'.")
        return False

    try:
        cmd = [
            executable,
            "--model", PIPER_MODEL_PATH,
            "--output_file", str(output_wav_path)
        ]
        result = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True
        )
        return output_wav_path.exists() and output_wav_path.stat().st_size > 0
    except Exception as e:
        logger.warning(f"Piper TTS binary execution failed: {e}. Falling back to system synthesis.")
        return False


def _synthesize_with_system_fallback(text: str, output_wav_path: Path) -> bool:
    """
    Offline fallback synthesizer using OS-native speech capabilities.
    On Windows: Uses System.Speech.Synthesis to output a local .wav file without network or extra packages.
    On Unix/Linux: Uses espeak / spd-say if available.
    """
    try:
        if os.name == "nt":
            # Clean text for PowerShell command line
            safe_text = text.replace('"', '""').replace("`", "``")
            safe_path = str(output_wav_path).replace('"', '""')
            ps_script = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate = 0; "
                f"$s.SetOutputToWaveFile('{safe_path}'); "
                f"$s.Speak('{safe_text}'); "
                f"$s.Dispose();"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                timeout=10
            )
            return output_wav_path.exists() and output_wav_path.stat().st_size > 0
        else:
            # Unix fallback with espeak if present
            espeak = shutil.which("espeak") or shutil.which("espeak-ng")
            if espeak:
                subprocess.run(
                    [espeak, "-w", str(output_wav_path), text],
                    capture_output=True,
                    timeout=10
                )
                return output_wav_path.exists() and output_wav_path.stat().st_size > 0
    except Exception as fallback_err:
        logger.warning(f"System fallback synthesis failed: {fallback_err}")
    return False


def synthesize_speech(text: str, filename: str) -> Optional[str]:
    """
    Synthesizes speech to a local WAV file in static/audio/alerts/.
    Returns relative web URL / file path string if successful, None if synthesis failed.
    Guaranteed not to raise unhandled exceptions.
    """
    if not PIPER_VOICE_ENABLED:
        logger.info("Piper voice synthesis disabled via PIPER_VOICE_ENABLED=false.")
        return None

    if not text or not str(text).strip():
        logger.warning("Empty text passed to synthesize_speech.")
        return None

    try:
        AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_filename = filename if filename.endswith(".wav") else f"{filename}.wav"
        output_wav = AUDIO_OUTPUT_DIR / safe_filename

        # Re-use existing audio if already generated and non-empty (0ms latency, no duplicate generation)
        if output_wav.exists() and output_wav.stat().st_size > 0:
            logger.debug(f"[VOICE SYNTHESIS] Reusing cached audio: {safe_filename}")
            return f"/api/v1/alerts/voice/{safe_filename}"

        # 1. Try Piper TTS if configured
        if is_piper_available():
            if _synthesize_with_piper(text, output_wav):
                logger.info(f"[PIPER TTS] Synthesized voice alert via Piper to {output_wav.name}")
                return f"/api/v1/alerts/voice/{safe_filename}"

        # 2. Try offline system fallback
        if _synthesize_with_system_fallback(text, output_wav):
            logger.info(f"[VOICE SYNTHESIS] Synthesized voice alert via system fallback to {output_wav.name}")
            return f"/api/v1/alerts/voice/{safe_filename}"

        logger.warning(f"[VOICE SYNTHESIS] Could not synthesize voice alert for text: {text[:50]}...")
        return None
    except Exception as e:
        logger.error(f"[VOICE SYNTHESIS ERROR] Unexpected error in synthesize_speech: {e}")
        return None

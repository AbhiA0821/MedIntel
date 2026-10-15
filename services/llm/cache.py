"""
MedIntel Clinical State Fingerprint Cache
Prevents redundant Groq LLM API invocations by caching valid explanations
for identical patient clinical states.
"""

import hashlib
import time
from typing import Dict, Any, Optional

# In-memory fingerprint cache: {fingerprint: (payload_dict, timestamp)}
_FINGERPRINT_CACHE: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 300  # 5-minute default TTL


def compute_clinical_state_fingerprint(
    patient_id: str,
    severity: str,
    abnormalities: list,
    vitals: dict
) -> str:
    """
    Computes a deterministic hash fingerprint representing the patient's current clinical state.
    Vitals are binned (HR +/- 3, SpO2 +/- 1, Temp +/- 0.3) so tiny simulator jitters reuse cache.
    """
    clean_id = str(patient_id).strip().upper()
    sorted_abn = ",".join(sorted(abnormalities)) if abnormalities else "NONE"

    hr = int(vitals.get("heart_rate", 75) // 4 * 4) if isinstance(vitals.get("heart_rate"), (int, float)) else 75
    spo2 = int(vitals.get("spo2", 98) // 2 * 2) if isinstance(vitals.get("spo2"), (int, float)) else 98
    temp = round(vitals.get("temperature", 37.0) * 2) / 2 if isinstance(vitals.get("temperature"), (int, float)) else 37.0

    raw_key = f"{clean_id}|{severity}|{sorted_abn}|{hr}|{spo2}|{temp}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def get_cached_explanation(fingerprint: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached payload if present and within TTL."""
    if fingerprint in _FINGERPRINT_CACHE:
        payload, timestamp = _FINGERPRINT_CACHE[fingerprint]
        if time.time() - timestamp <= CACHE_TTL_SECONDS:
            result = dict(payload)
            result["cached"] = True
            return result
        else:
            _FINGERPRINT_CACHE.pop(fingerprint, None)
    return None


def set_cached_explanation(fingerprint: str, payload: Dict[str, Any]) -> None:
    """Stores validated payload in cache with current timestamp."""
    _FINGERPRINT_CACHE[fingerprint] = (payload, time.time())


def clear_cache() -> None:
    """Clears all cached items (useful for testing)."""
    _FINGERPRINT_CACHE.clear()

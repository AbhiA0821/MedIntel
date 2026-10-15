"""
MedIntel Deterministic Rule-Based Safety Engine
Evaluates vital signs against clinical safety thresholds to determine patient severity.
"""

from typing import Any
from services.reason_detection import extract_vitals_from_patient, get_patient_reasons


def classify_severity(patient: Any) -> str:
    """
    Deterministic Safety Severity Engine.

    CRITICAL:
    - SpO2 < 90
    - Temperature > 38.5

    MODERATE:
    - Heart Rate > 120
    - Systolic BP > 160
    - Respiratory Rate > 24

    Otherwise:
    - LOW
    """
    v = extract_vitals_from_patient(patient)

    if v["spo2"] < 90 or v["temperature"] > 38.5:
        return "CRITICAL"
    elif v["heart_rate"] > 120 or v["systolic_bp"] > 160 or v["respiratory_rate"] > 24:
        return "MODERATE"
    else:
        return "LOW"


if __name__ == "__main__":
    test_patient_normal = {"heart_rate": 75, "spo2": 98, "temperature": 37.0, "systolic_bp": 118, "diastolic_bp": 78, "respiratory_rate": 16}
    test_patient_mod = {"heart_rate": 125, "spo2": 95, "temperature": 37.2, "systolic_bp": 140, "diastolic_bp": 85, "respiratory_rate": 20}
    test_patient_crit = {"heart_rate": 110, "spo2": 88, "temperature": 38.8, "systolic_bp": 130, "diastolic_bp": 80, "respiratory_rate": 22}

    print("Normal:", classify_severity(test_patient_normal))
    print("Moderate:", classify_severity(test_patient_mod))
    print("Critical:", classify_severity(test_patient_crit))
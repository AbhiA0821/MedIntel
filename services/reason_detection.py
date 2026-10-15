"""
MedIntel Abnormal Vital Signs Reason Detection Service
Identifies clinical reasons for abnormal vital sign readings based on deterministic threshold rules.
"""

from typing import Dict, Any, List


def extract_vitals_from_patient(patient: Any) -> Dict[str, Any]:
    """
    Normalizes patient representations (tuple, dict, or object) into standard vital dictionary.
    Tuple structure from DB query:
    Index 0: patient_id
    Index 1: first_name
    Index 2: last_name
    Index 3: heart_rate
    Index 4: spo2
    Index 5: temperature
    Index 6: systolic_bp
    Index 7: diastolic_bp
    Index 8: respiratory_rate (optional)
    """
    if isinstance(patient, (tuple, list)):
        return {
            "patient_id": patient[0] if len(patient) > 0 else 101,
            "heart_rate": patient[3] if len(patient) > 3 else 75,
            "spo2": patient[4] if len(patient) > 4 else 98,
            "temperature": patient[5] if len(patient) > 5 else 37.0,
            "systolic_bp": patient[6] if len(patient) > 6 else 120,
            "diastolic_bp": patient[7] if len(patient) > 7 else 80,
            "respiratory_rate": patient[8] if len(patient) > 8 else 16
        }
    elif isinstance(patient, dict):
        return {
            "patient_id": patient.get("patient_id", 101),
            "heart_rate": patient.get("heart_rate", 75),
            "spo2": patient.get("spo2", 98),
            "temperature": patient.get("temperature", 37.0),
            "systolic_bp": patient.get("systolic_bp", 120),
            "diastolic_bp": patient.get("diastolic_bp", 80),
            "respiratory_rate": patient.get("respiratory_rate", 16)
        }
    else:
        return {
            "patient_id": getattr(patient, "patient_id", 101),
            "heart_rate": getattr(patient, "heart_rate", 75),
            "spo2": getattr(patient, "spo2", 98),
            "temperature": getattr(patient, "temperature", 37.0),
            "systolic_bp": getattr(patient, "systolic_bp", 120),
            "diastolic_bp": getattr(patient, "diastolic_bp", 80),
            "respiratory_rate": getattr(patient, "respiratory_rate", 16)
        }


def get_patient_reasons(patient: Any) -> List[str]:
    """
    Detect abnormal vital signs reasons based on deterministic safety rules.
    """
    v = extract_vitals_from_patient(patient)
    reasons = []

    if v["spo2"] < 90:
        reasons.append("Low SpO2 (< 90%)")
    elif v["spo2"] < 92:
        reasons.append("Low Oxygen")

    if v["temperature"] > 38.5:
        reasons.append("High Temperature (> 38.5°C)")
    elif v["temperature"] > 38.0:
        reasons.append("High Temperature")
    elif v["temperature"] < 36.0:
        reasons.append("Low Temperature")

    if v["heart_rate"] > 120:
        reasons.append("Elevated Heart Rate (> 120 bpm)")
    elif v["heart_rate"] > 100:
        reasons.append("High Heart Rate")
    elif v["heart_rate"] < 60:
        reasons.append("Low Heart Rate")

    if v["systolic_bp"] > 160:
        reasons.append("High Blood Pressure (> 160 mmHg)")
    elif v["systolic_bp"] > 140 or v["diastolic_bp"] > 90:
        reasons.append("High Blood Pressure")
    elif v["systolic_bp"] < 90 or v["diastolic_bp"] < 60:
        reasons.append("Low Blood Pressure")

    if v["respiratory_rate"] > 24:
        reasons.append("Elevated Respiratory Rate (> 24/min)")

    return reasons
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
    Index 8: respiratory_rate
    """
    if isinstance(patient, (tuple, list)):
        return {
            "patient_id": patient[0],
            "heart_rate": patient[3],
            "spo2": patient[4],
            "temperature": patient[5],
            "systolic_bp": patient[6],
            "diastolic_bp": patient[7],
            "respiratory_rate": patient[8]
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
    if v["temperature"] > 38.5:
        reasons.append("High Temperature (> 38.5°C)")
    if v["heart_rate"] > 120:
        reasons.append("Elevated Heart Rate (> 120 bpm)")
    if v["systolic_bp"] > 160:
        reasons.append("High Blood Pressure (> 160 mmHg)")
    if v["respiratory_rate"] > 24:
        reasons.append("Elevated Respiratory Rate (> 24/min)")

    return reasons
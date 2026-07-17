from services.reason_detection import get_patient_reasons


def classify_severity(patient):
    reasons= get_patient_reasons(patient)
    if "Low Oxygen" in reasons:
        return "Critical"
    elif len(reasons)>=3:
        return "Critical"
    elif len(reasons)==2:
        return "Moderate"
    else:
        return "Low"
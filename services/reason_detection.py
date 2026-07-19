def get_patient_reasons(patient):
    reasons = []

    heart_rate = patient["heart_rate"]
    spo2 = patient["spo2"]
    temperature = patient["temperature"]
    systolic_bp = patient["systolic_bp"]

    if spo2 < 92:
        reasons.append("Low Oxygen")

    if heart_rate > 100:
        reasons.append("High Heart Rate")

    if temperature > 38:
        reasons.append("High Temperature")

    if systolic_bp > 140:
        reasons.append("High Blood Pressure")

    return reasons
def get_patient_reasons(patient):
    reasons = []

    heart_rate = patient[3]
    spo2 = patient[4]
    temperature = patient[5]
    systolic_bp = patient[6]

    if spo2 < 92:
        reasons.append("Low Oxygen")

    if heart_rate > 100:
        reasons.append("High Heart Rate")

    if temperature > 38:
        reasons.append("High Temperature")

    if systolic_bp > 140:
        reasons.append("High Blood Pressure")

    return reasons
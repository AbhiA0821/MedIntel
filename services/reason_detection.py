def get_patient_reasons(patient):
    reasons = []

    heart_rate = patient[2]
    spo2 = patient[3]
    temperature = patient[4]
    systolic_bp = patient[5]

    if spo2 < 92:
        reasons.append("Low Oxygen")

    if heart_rate > 100:
        reasons.append("High Heart Rate")

    if temperature > 38:
        reasons.append("High Temperature")

    if systolic_bp > 140:
        reasons.append("High Blood Pressure")

    return reasons
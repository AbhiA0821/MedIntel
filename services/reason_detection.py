def get_patient_reasons(patient):
    """
    Detect abnormal vital signs for a patient.

    Expected patient tuple:
    (
        patient_id,
        first_name,
        last_name,
        heart_rate,
        spo2,
        temperature,
        systolic_bp,
        diastolic_bp
    )
    """

    heart_rate = patient[3]
    spo2 = patient[4]
    temperature = patient[5]
    systolic_bp = patient[6]
    diastolic_bp = patient[7]

    reasons = []

    # Oxygen saturation
    if spo2 < 92:
        reasons.append("Low Oxygen")

    # Heart rate
    if heart_rate > 100:
        reasons.append("High Heart Rate")
    elif heart_rate < 60:
        reasons.append("Low Heart Rate")

    # Temperature
    if temperature > 38:
        reasons.append("High Temperature")
    elif temperature < 36:
        reasons.append("Low Temperature")

    # Blood pressure
    if systolic_bp > 140 or diastolic_bp > 90:
        reasons.append("High Blood Pressure")
    elif systolic_bp < 90 or diastolic_bp < 60:
        reasons.append("Low Blood Pressure")

    return reasons
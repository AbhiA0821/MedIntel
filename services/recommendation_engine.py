from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity


def get_recommendations(patient):
    reasons = get_patient_reasons(patient)
    severity = classify_severity(patient).upper()

    recommendations = []

    for reason in reasons:
        if "Low SpO2" in reason or reason == "Low Oxygen":
            if severity == "CRITICAL":
                recommendations.append("Initiate high-flow oxygen therapy & emergency respiratory consult.")
            elif severity == "MODERATE":
                recommendations.append("Increase oxygen monitoring and evaluate O2 supplementation.")
            else:
                recommendations.append("Monitor oxygen saturation closely.")

        elif "Heart Rate" in reason:
            if severity == "CRITICAL":
                recommendations.append("Continuous ECG telemetry monitoring & immediate cardiology review.")
            elif severity == "MODERATE":
                recommendations.append("Monitor heart rate frequently and check 12-lead ECG.")
            else:
                recommendations.append("Monitor heart rate during routine vitals check.")

        elif "Temperature" in reason:
            if severity == "CRITICAL":
                recommendations.append("Initiate active fever management & blood culture protocol.")
            elif severity == "MODERATE":
                recommendations.append("Administer antipyretics as ordered & monitor body temperature.")
            else:
                recommendations.append("Monitor body temperature.")

        elif "Blood Pressure" in reason:
            if severity == "CRITICAL":
                recommendations.append("Immediate physician evaluation for severe blood pressure anomaly.")
            elif severity == "MODERATE":
                recommendations.append("Recheck blood pressure in 15 minutes & monitor closely.")
            else:
                recommendations.append("Monitor blood pressure.")

        elif "Respiratory Rate" in reason:
            if severity == "CRITICAL":
                recommendations.append("Immediate respiratory therapy evaluation & arterial blood gas check.")
            elif severity == "MODERATE":
                recommendations.append("Monitor respiratory rate and patient positioning.")
            else:
                recommendations.append("Monitor respiratory rate.")

    if not recommendations:
        recommendations.append("Continue routine patient vital sign monitoring.")

    return recommendations
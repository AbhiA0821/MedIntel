from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity


def get_recommendations(patient):

    reasons = get_patient_reasons(patient)
    severity = classify_severity(patient)

    recommendations = []

    for reason in reasons:

        if reason == "Low Oxygen":

            if severity == "Critical":
                recommendations.append("Initiate oxygen therapy immediately.")
            elif severity == "Moderate":
                recommendations.append("Increase oxygen monitoring.")
            else:
                recommendations.append("Monitor oxygen saturation.")

        elif reason == "High Heart Rate":

            if severity == "Critical":
                recommendations.append("Continuous ECG monitoring.")
            elif severity == "Moderate":
                recommendations.append("Monitor heart rate frequently.")
            else:
                recommendations.append("Monitor heart rate.")

        elif reason == "Low Heart Rate":

            if severity == "Critical":
                recommendations.append("Immediate cardiac assessment required.")
            elif severity == "Moderate":
                recommendations.append("Monitor heart rate frequently.")
            else:
                recommendations.append("Monitor heart rate.")

        elif reason == "High Temperature":

            if severity == "Critical":
                recommendations.append("Initiate fever management immediately.")
            elif severity == "Moderate":
                recommendations.append("Monitor body temperature frequently.")
            else:
                recommendations.append("Monitor body temperature.")

        elif reason == "Low Temperature":

            if severity == "Critical":
                recommendations.append("Initiate active warming measures.")
            elif severity == "Moderate":
                recommendations.append("Keep the patient warm.")
            else:
                recommendations.append("Monitor body temperature.")

        elif reason == "High Blood Pressure":

            if severity == "Critical":
                recommendations.append("Immediate physician evaluation required.")
            elif severity == "Moderate":
                recommendations.append("Monitor blood pressure frequently.")
            else:
                recommendations.append("Monitor blood pressure.")

        elif reason == "Low Blood Pressure":

            if severity == "Critical":
                recommendations.append("Assess circulatory status immediately.")
            elif severity == "Moderate":
                recommendations.append("Encourage adequate hydration.")
            else:
                recommendations.append("Monitor blood pressure.")

    return recommendations
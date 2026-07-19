from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity


def get_recommendations(patient):
    reasons = get_patient_reasons(patient)
    severity = classify_severity(patient)

    recommendations = []

    for reason in reasons:

        # Low Oxygen
        if reason == "Low Oxygen":

            if severity == "Critical":
                recommendations.extend([
                    "Initiate oxygen therapy immediately.",
                    "Continuously monitor oxygen saturation (SpO₂).",
                    "Assess respiratory status.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Increase oxygen monitoring.",
                    "Assess respiratory status.",
                    "Recheck SpO₂ frequently."
                ])

            else:
                recommendations.extend([
                    "Monitor oxygen saturation.",
                    "Reassess during routine vital checks."
                ])

        # High Heart Rate
        elif reason == "High Heart Rate":

            if severity == "Critical":
                recommendations.extend([
                    "Continuous ECG monitoring.",
                    "Immediate clinical evaluation required.",
                    "Assess for cardiac abnormalities.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Monitor heart rate frequently.",
                    "Perform ECG assessment.",
                    "Reassess patient condition."
                ])

            else:
                recommendations.extend([
                    "Monitor heart rate.",
                    "Reassess during routine vital checks."
                ])

        # Low Heart Rate
        elif reason == "Low Heart Rate":

            if severity == "Critical":
                recommendations.extend([
                    "Continuous ECG monitoring.",
                    "Immediate cardiac assessment required.",
                    "Assess for symptomatic bradycardia.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Monitor heart rate frequently.",
                    "Perform ECG assessment.",
                    "Assess for dizziness or fatigue."
                ])

            else:
                recommendations.extend([
                    "Monitor heart rate.",
                    "Reassess during routine vital checks."
                ])

        # High Temperature
        elif reason == "High Temperature":

            if severity == "Critical":
                recommendations.extend([
                    "Initiate fever management immediately.",
                    "Monitor body temperature continuously.",
                    "Assess for severe infection.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Monitor body temperature frequently.",
                    "Assess for signs of infection.",
                    "Encourage adequate hydration."
                ])

            else:
                recommendations.extend([
                    "Monitor body temperature.",
                    "Reassess during routine vital checks."
                ])

        # Low Temperature
        elif reason == "Low Temperature":

            if severity == "Critical":
                recommendations.extend([
                    "Initiate active warming measures immediately.",
                    "Monitor body temperature continuously.",
                    "Assess for hypothermia.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Keep the patient warm.",
                    "Monitor body temperature frequently.",
                    "Reassess patient condition."
                ])

            else:
                recommendations.extend([
                    "Monitor body temperature.",
                    "Ensure patient comfort."
                ])

        # High Blood Pressure
        elif reason == "High Blood Pressure":

            if severity == "Critical":
                recommendations.extend([
                    "Monitor blood pressure continuously.",
                    "Assess for hypertensive complications.",
                    "Immediate physician evaluation required.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Monitor blood pressure frequently.",
                    "Assess for symptoms of hypertension.",
                    "Reassess patient condition."
                ])

            else:
                recommendations.extend([
                    "Monitor blood pressure.",
                    "Reassess during routine vital checks."
                ])

        # Low Blood Pressure
        elif reason == "Low Blood Pressure":

            if severity == "Critical":
                recommendations.extend([
                    "Monitor blood pressure continuously.",
                    "Assess circulatory status immediately.",
                    "Evaluate fluid status.",
                    "Notify healthcare provider immediately."
                ])

            elif severity == "Moderate":
                recommendations.extend([
                    "Monitor blood pressure frequently.",
                    "Encourage adequate hydration.",
                    "Assess for dizziness or weakness."
                ])

            else:
                recommendations.extend([
                    "Monitor blood pressure.",
                    "Encourage adequate fluid intake."
                ])

    # Remove duplicate recommendations while preserving order
    recommendations = list(dict.fromkeys(recommendations))

    return recommendations


# -------------------------------
# Test Recommendation Engine
# -------------------------------
if __name__ == "__main__":

    patient = (
    1,
    "Rahul",
    "Sharma",
    130,
    84,
    39.2,
    170,
    105
)

    print("=" * 60)
    print("MEDINTEL - RECOMMENDATION ENGINE")
    print("=" * 60)

    reasons = get_patient_reasons(patient)
    severity = classify_severity(patient)
    recommendations = get_recommendations(patient)

    print(f"\nPatient Name : {patient[1]}")
    print(f"Detected Reasons : {', '.join(reasons)}")
    print(f"Severity : {severity}")

    print("\nRecommendations:")

    for i, recommendation in enumerate(recommendations, start=1):
        print(f"{i}. {recommendation}")

    print("\n" + "=" * 60)
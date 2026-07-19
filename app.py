#Calling function from other folders
from database.monitoring_queries import get_critical_patients
from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity
from services.recommendation_engine import get_recommendations
from services.alert_engine import generate_alert

def main():
    critical_patients = get_critical_patients()

    if not critical_patients:
        print("No critical patients found.")
        return

    for patient in critical_patients:

        reasons = get_patient_reasons(patient)
        severity = classify_severity(patient)
        recommendations = get_recommendations(patient)
        alert = generate_alert(patient)

        print("=" * 60)
        print(f"Patient : {patient[0]} {patient[1]}")
        print(f"Severity : {severity}")

        print("\nReasons:")
        for reason in reasons:
            print(f"- {reason}")

        print("\nRecommendations:")
        for rec in recommendations:
            print(f"- {rec}")

        print("\nAlert")
        print(f"{alert['alert_icon']} {alert['alert_message']}")


if __name__ == "__main__":
    main()
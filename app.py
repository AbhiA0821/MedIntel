import sys
from database.monitoring_queries import get_critical_patients
from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity
from services.recommendation_engine import get_recommendations
from services.alert_engine import generate_alert


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    critical_patients = get_critical_patients()

    if not critical_patients:
        print("No critical patients at this time.")
        return

    print("=== MEDINTEL CRITICAL PATIENT MONITORING ===")
    for patient in critical_patients:
        severity = classify_severity(patient)
        reasons = get_patient_reasons(patient)
        recommendations = get_recommendations(patient)
        alert = generate_alert(patient)
        print(f"\nPatient P{patient[0]}: {patient[1]} {patient[2]}")
        print(f"Severity: {severity}")
        print(f"Reasons: {', '.join(reasons)}")
        print(f"Recommendations: {', '.join(recommendations)}")
        print(f"Alert Priority: {alert.get('priority')}")


if __name__ == "__main__":
    main()
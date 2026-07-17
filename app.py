#Calling function from other folders
from database.monitoring_queries import get_critical_patients
from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity


def main():
    # Get all critical patients
    critical_patients = get_critical_patients()

    # Check if any critical patients exist
    if not critical_patients:
        print("No critical patients found.")
        return

    # Process each patient
    for patient in critical_patients:
        reasons = get_patient_reasons(patient)
        severity=classify_severity(patient)

        print("=" * 50)
        print(f"\nPatient : {patient[0]} {patient[1]}")
        print(f"Severity : {severity}")

        print("Reasons:")
        for reason in reasons:
            print(f"- {reason}")


if __name__ == "__main__":
    main()
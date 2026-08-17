from prefect import flow
from prefect.tasks import task
from prefect_pipeline.tasks.data_health_tasks import (
    check_database_connection,
    verify_patient_vitals_counts,
    validate_vital_ranges
)

@flow(name="medintel_health_check_flow")
def health_check_flow() -> dict:
    """
    Finite flow to verify database health, row counts, and data integrity.
    """
    db_status = check_database_connection()
    counts = verify_patient_vitals_counts()
    range_check = validate_vital_ranges()

    return {
        "flow": "medintel_health_check_flow",
        "db_status": db_status,
        "counts": counts,
        "range_check": range_check
    }

if __name__ == "__main__":
    result = health_check_flow()
    print("Health Check Flow completed successfully:")
    print(result)

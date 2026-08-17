from prefect import task
import duckdb
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "database" / "medintel.duckdb"

@task(name="check_database_connection", retries=2, retry_delay_seconds=2)
def check_database_connection() -> dict:
    """
    Verify DuckDB database connectivity and readiness.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DuckDB database file not found at {DB_PATH}")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        res = con.execute("SELECT 1").fetchone()
        status = "healthy" if res and res[0] == 1 else "unhealthy"
        return {"status": status, "db_path": str(DB_PATH)}
    finally:
        con.close()

@task(name="verify_patient_vitals_counts", retries=1, retry_delay_seconds=2)
def verify_patient_vitals_counts() -> dict:
    """
    Audit current row counts across Patients, VitalSigns, and ProcessedPatientVitals.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        patient_count = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
        vitals_count = con.execute("SELECT COUNT(*) FROM VitalSigns").fetchone()[0]
        
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        processed_count = 0
        if "ProcessedPatientVitals" in tables:
            processed_count = con.execute("SELECT COUNT(*) FROM ProcessedPatientVitals").fetchone()[0]

        return {
            "patients": patient_count,
            "raw_vitals": vitals_count,
            "processed_vitals": processed_count
        }
    finally:
        con.close()

@task(name="validate_vital_ranges", retries=1, retry_delay_seconds=2)
def validate_vital_ranges() -> dict:
    """
    Perform sanity checks on vital sign value ranges in DuckDB.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        table_to_check = "ProcessedPatientVitals" if "ProcessedPatientVitals" in tables else "VitalSigns"

        critical_spo2_count = con.execute(f"SELECT COUNT(*) FROM {table_to_check} WHERE spo2 < 90").fetchone()[0]
        high_hr_count = con.execute(f"SELECT COUNT(*) FROM {table_to_check} WHERE heart_rate > 120").fetchone()[0]
        high_temp_count = con.execute(f"SELECT COUNT(*) FROM {table_to_check} WHERE temperature > 38.5").fetchone()[0]

        return {
            "checked_table": table_to_check,
            "critical_spo2_records": critical_spo2_count,
            "high_heart_rate_records": high_hr_count,
            "high_temperature_records": high_temp_count
        }
    finally:
        con.close()

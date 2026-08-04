from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator

import subprocess
import duckdb


# =====================================================
# Configuration
# =====================================================

PROJECT_PATH = "/opt/medintel"
DATABASE_PATH = "/opt/medintel/database/medintel.duckdb"


# =====================================================
# Task 1 - Run PySpark ETL
# =====================================================

def run_pyspark_etl():

    print("=" * 60)
    print("Starting MedIntel PySpark ETL")
    print("=" * 60)

    result = subprocess.run(
        [
            "python",
            "-m",
            "pyspark_pipeline.preprocessing"
        ],
        cwd=PROJECT_PATH,
        capture_output=True,
        text=True
    )

    # Show PySpark output inside Airflow logs
    print(result.stdout)

    if result.stderr:
        print(result.stderr)

    # Fail Airflow task if PySpark fails
    if result.returncode != 0:
        raise RuntimeError(
            f"PySpark ETL failed with exit code "
            f"{result.returncode}"
        )

    print("PySpark ETL completed successfully.")


# =====================================================
# Task 2 - Verify Processed Data
# =====================================================

def verify_processed_data():

    print("=" * 60)
    print("Verifying ProcessedPatientVitals")
    print("=" * 60)

    con = duckdb.connect(DATABASE_PATH, read_only=True)

    try:

        # Check whether table exists
        table_exists = con.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'ProcessedPatientVitals'
        """).fetchone()[0]

        if table_exists == 0:
            raise ValueError(
                "ProcessedPatientVitals table does not exist."
            )

        # Count processed records
        total_records = con.execute("""
            SELECT COUNT(*)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        # Count patients
        total_patients = con.execute("""
            SELECT COUNT(DISTINCT patient_id)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        print(
            f"Processed records : {total_records}"
        )

        print(
            f"Patients represented : {total_patients}"
        )

        if total_records == 0:
            raise ValueError(
                "ProcessedPatientVitals contains no records."
            )

        print("=" * 60)
        print("Processed data verification successful.")
        print("=" * 60)

    finally:

        con.close()


# =====================================================
# Default Airflow Settings
# =====================================================

default_args = {

    "owner": "medintel",

    # Don't run historical missed DAG executions
    "depends_on_past": False,

    # Retry task if temporary failure occurs
    "retries": 2,

    # Wait before retry
    "retry_delay": timedelta(minutes=1),
}


# =====================================================
# MedIntel DAG
# =====================================================

with DAG(

    dag_id="medintel_pipeline",

    description=(
        "MedIntel healthcare data engineering "
        "pipeline using PySpark and DuckDB"
    ),

    default_args=default_args,

    # Run pipeline every 5 minutes
    schedule="*/5 * * * *",

    start_date=datetime(2026, 8, 1),

    catchup=False,

    tags=[
        "medintel",
        "healthcare",
        "pyspark",
        "duckdb"
    ],

) as dag:


    # =================================================
    # Start
    # =================================================

    start_pipeline = EmptyOperator(
        task_id="start_pipeline"
    )


    # =================================================
    # PySpark ETL
    # =================================================

    pyspark_etl = PythonOperator(
        task_id="run_pyspark_etl",
        python_callable=run_pyspark_etl,
        execution_timeout=timedelta(minutes=10)
    )


    # =================================================
    # Verify Processed Data
    # =================================================

    verify_data = PythonOperator(
        task_id="verify_processed_data",
        python_callable=verify_processed_data
    )


    # =================================================
    # End
    # =================================================

    end_pipeline = EmptyOperator(
        task_id="end_pipeline"
    )


    # =================================================
    # Task Dependencies
    # =================================================

    (
        start_pipeline
        >> pyspark_etl
        >> verify_data
        >> end_pipeline
    )
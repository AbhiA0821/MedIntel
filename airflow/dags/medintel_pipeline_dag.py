from datetime import datetime, timedelta
import subprocess

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator


# =====================================================
# Configuration
# =====================================================

PROJECT_PATH = "/opt/medintel"


# =====================================================
# Start Continuous MedIntel Monitoring
# =====================================================

def start_medintel_monitoring():
    """
    Start the MedIntel continuous monitoring service.

    The monitoring service performs:
        Vital Generation
            ↓
        Raw DuckDB Storage
            ↓
        PySpark Preprocessing
            ↓
        Processed DuckDB Storage
            ↓
        ML Prediction (later)
            ↓
        Recommendation (later)
            ↓
        Alert (later)

    The service itself maintains the approximately
    5-second continuous monitoring cycle.
    """

    print("=" * 60)
    print("STARTING MEDINTEL CONTINUOUS MONITORING")
    print("=" * 60)

    process = subprocess.Popen(
        [
            "python",
            "-u",
            "-m",
            "services.monitoring_pipeline"
        ],
        cwd=PROJECT_PATH
    )

    print(
        f"MedIntel monitoring process started "
        f"with PID: {process.pid}"
    )

    # Keep this Airflow task attached to the
    # monitoring process.
    return_code = process.wait()

    if return_code != 0:
        raise RuntimeError(
            "MedIntel monitoring service stopped "
            f"with exit code {return_code}"
        )


# =====================================================
# Airflow Configuration
# =====================================================

default_args = {
    "owner": "medintel",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


# =====================================================
# DAG
# =====================================================

with DAG(

    dag_id="medintel_continuous_monitoring",

    description=(
        "Orchestrates the continuous MedIntel "
        "patient monitoring pipeline"
    ),

    default_args=default_args,

    # Airflow starts the service manually/on deployment.
    # The service itself performs the 5-second loop.
    schedule=None,

    start_date=datetime(2026, 8, 1),

    catchup=False,

    max_active_runs=1,

    tags=[
        "medintel",
        "healthcare",
        "pyspark",
        "duckdb",
        "monitoring"
    ],

) as dag:

    # =================================================
    # Start
    # =================================================

    start_pipeline = EmptyOperator(
        task_id="start_pipeline"
    )

    # =================================================
    # Continuous Monitoring
    # =================================================

    run_monitoring = PythonOperator(
        task_id="run_continuous_monitoring",
        python_callable=start_medintel_monitoring
    )

    # =================================================
    # Dependencies
    # =================================================

    start_pipeline >> run_monitoring
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta


# Default settings applied to Airflow tasks
default_args = {
    "owner": "medintel-data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}


with DAG(
    dag_id="medintel_pipeline",

    description="MedIntel automated healthcare data engineering pipeline",

    default_args=default_args,

    start_date=datetime(2026, 8, 4),

    # Manual execution while developing/testing
    schedule=None,

    catchup=False,

    tags=["medintel", "data-engineering", "production"],

) as dag:

    # --------------------------------------------------
    # Task 1: Start Pipeline
    # --------------------------------------------------

    start_pipeline = EmptyOperator(
        task_id="start_pipeline"
    )


    # --------------------------------------------------
    # Task 2: Run existing PySpark ETL pipeline
    # --------------------------------------------------

    run_pyspark_etl = BashOperator(
        task_id="run_pyspark_etl",

        bash_command="""
        cd /opt/medintel &&
        python pyspark_pipeline/preprocessing.py
        """
    )


    # --------------------------------------------------
    # Task 3: End Pipeline
    # --------------------------------------------------

    end_pipeline = EmptyOperator(
        task_id="end_pipeline"
    )


    # Task dependency
    start_pipeline >> run_pyspark_etl >> end_pipeline
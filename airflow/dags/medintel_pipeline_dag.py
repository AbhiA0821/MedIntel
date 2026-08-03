from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="medintel_pipeline",
    start_date=datetime(2026,8,3),
    schedule=None,
    catchup=False,
    tags=["medintel","production"],
) as dag:
        run_pyspark_etl = BashOperator(
        task_id="run_pyspark_etl",
        bash_command="cd /opt/medintel && python pyspark_pipeline/preprocessing.py",
    )
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG(
    dag_id="medintel_first_dag",
    start_date=datetime(2026, 7, 31),
    schedule=None,
    catchup=False,
    tags=["medintel", "learning"],
) as dag:
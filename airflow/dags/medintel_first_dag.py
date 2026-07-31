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

    def load_patient_data():
        print("Loading patient data...")


#cretae a PythonOperator    Creates a task in DAG
    load_task = PythonOperator(
        task_id="load_patient_data",
        python_callable=load_patient_data,
    )
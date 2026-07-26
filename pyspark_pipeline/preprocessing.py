import os
import sys

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable


from pyspark.sql import SparkSession
from database.connection import get_connection
from simulator.patient_simulator import generate_vitals


# ---------------------------------------
# Create Spark Session
# ---------------------------------------
def create_spark_session():

    spark = (
        SparkSession.builder
        .appName("MedIntel")
        .master("local[*]")
        .getOrCreate()
    )

    return spark


# ---------------------------------------
# Read Patients from DuckDB
# ---------------------------------------
def get_all_patients():

    con = get_connection()

    query = """
        SELECT
            patient_id,
            first_name,
            last_name,
            age,
            gender,
            blood_group,
            ward,
            admission_date
        FROM Patients;
    """

    patients = con.execute(query).fetchall()

    con.close()

    return patients


# ---------------------------------------
# Generate Vitals for Every Patient
# ---------------------------------------
def generate_patient_records():

    patients = get_all_patients()

    records = []

    for patient in patients:

        vitals = generate_vitals()

        record = {
            "patient_id": patient[0],
            "first_name": patient[1],
            "last_name": patient[2],
            "age": patient[3],
            "gender": patient[4],
            "blood_group": patient[5],
            "ward": patient[6],
            "admission_date": patient[7],
            **vitals
        }

        records.append(record)

    return records


# ---------------------------------------
# Convert to Spark DataFrame
# ---------------------------------------
def create_dataframe(spark):

    records = generate_patient_records()

    df = spark.createDataFrame(records)

    return df


# ---------------------------------------
# Main
# ---------------------------------------
if __name__ == "__main__":

    spark = create_spark_session()

    df = create_dataframe(spark)

    print("\nPatient Data\n")

    df.show(truncate=False)

    print("\nTotal Patients :", df.count())
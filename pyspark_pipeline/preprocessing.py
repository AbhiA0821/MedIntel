import os
import sys

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable


from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when

from database.connection import get_connection
from simulator.patient_simulator import generate_vitals


# -------------------------------
# Create Spark Session
# -------------------------------
def create_spark_session():
    spark = (
        SparkSession.builder
        .appName("MedIntel")
        .master("local[*]")
        .getOrCreate()
    )
    return spark


# -------------------------------
# Read Patients from DuckDB
# -------------------------------
def get_all_patients():

    con = get_connection()

    patients = con.execute("""
        SELECT *
        FROM Patients
    """).fetchall()

    columns = [desc[0] for desc in con.description]

    con.close()

    return patients, columns


# -------------------------------
# Generate Patient Records
# -------------------------------
def generate_patient_records():

    patients, columns = get_all_patients()

    records = []

    for patient in patients:

        patient_dict = dict(zip(columns, patient))

        vitals = generate_vitals()

        patient_dict.update(vitals)

        records.append(patient_dict)

    return records


# -------------------------------
# Create Spark DataFrame
# -------------------------------
def create_dataframe(spark):

    records = generate_patient_records()

    df = spark.createDataFrame(records)

    return df


# -------------------------------
# Step 6.1 - Heart Rate Validation
# -------------------------------
def validate_heart_rate(df):

    df = df.withColumn(
        "hr_valid",
        when(
            (col("heart_rate") >= 40) &
            (col("heart_rate") <= 180),
            True
        ).otherwise(False)
    )

    return df


# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":

    spark = create_spark_session()

    df = create_dataframe(spark)

    # Validate Heart Rate
    df = validate_heart_rate(df)

    print("\n==============================")
    print("PATIENT DATA")
    print("==============================\n")

    df.show(truncate=False)

    print("\n==============================")
    print("DATAFRAME SCHEMA")
    print("==============================\n")

    df.printSchema()

    print("\n==============================")
    print("COLUMN NAMES")
    print("==============================\n")

    print(df.columns)

    print("\n==============================")
    print("TOTAL PATIENTS")
    print("==============================\n")

    print(df.count())

    print("\n==============================")
    print("HEART RATE VALIDATION")
    print("==============================\n")

    df.select(
        "patient_id",
        "heart_rate",
        "hr_valid"
    ).show(truncate=False)

    spark.stop()
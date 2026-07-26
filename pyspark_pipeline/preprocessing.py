import os
import sys

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when

from database.connection import get_connection
from simulator.patient_simulator import generate_vitals


# =====================================================
# Create Spark Session
# =====================================================

def create_spark_session():

    spark = (
        SparkSession.builder
        .appName("MedIntel")
        .master("local[*]")
        .getOrCreate()
    )

    return spark


# =====================================================
# Read Patients from DuckDB
# =====================================================

def get_all_patients():

    con = get_connection()

    patients = con.execute("""
        SELECT *
        FROM Patients
    """).fetchall()

    columns = [desc[0] for desc in con.description]

    con.close()

    return patients, columns


# =====================================================
# Generate Patient Records
# =====================================================

def generate_patient_records():

    patients, columns = get_all_patients()

    records = []

    for patient in patients:

        patient_dict = dict(zip(columns, patient))

        vitals = generate_vitals()

        patient_dict.update(vitals)

        records.append(patient_dict)

    return records


# =====================================================
# Create Spark DataFrame
# =====================================================

def create_dataframe(spark):

    records = generate_patient_records()

    return spark.createDataFrame(records)


# =====================================================
# Heart Rate Validation
# =====================================================

def validate_heart_rate(df):

    return df.withColumn(
        "hr_valid",
        when(
            (col("heart_rate") >= 40) &
            (col("heart_rate") <= 180),
            True
        ).otherwise(False)
    )


# =====================================================
# SpO2 Validation
# =====================================================

def validate_spo2(df):

    return df.withColumn(
        "spo2_valid",
        when(
            (col("spo2") >= 90) &
            (col("spo2") <= 100),
            True
        ).otherwise(False)
    )


# =====================================================
# Temperature Validation
# =====================================================

def validate_temperature(df):

    return df.withColumn(
        "temperature_valid",
        when(
            (col("temperature") >= 35.0) &
            (col("temperature") <= 42.0),
            True
        ).otherwise(False)
    )


# =====================================================
# Blood Pressure Validation
# =====================================================

def validate_blood_pressure(df):

    df = df.withColumn(
        "systolic_valid",
        when(
            (col("systolic_bp") >= 90) &
            (col("systolic_bp") <= 180),
            True
        ).otherwise(False)
    )

    df = df.withColumn(
        "diastolic_valid",
        when(
            (col("diastolic_bp") >= 60) &
            (col("diastolic_bp") <= 120),
            True
        ).otherwise(False)
    )

    return df


# =====================================================
# Respiratory Rate Validation
# =====================================================

def validate_respiratory_rate(df):

    return df.withColumn(
        "respiratory_valid",
        when(
            (col("respiratory_rate") >= 8) &
            (col("respiratory_rate") <= 30),
            True
        ).otherwise(False)
    )


# =====================================================
# Create Patient Status
# =====================================================

def create_status(df):

    df = df.withColumn(

        "status",

        when(col("spo2") < 90, "Critical")

        .when(col("temperature") > 38.5, "Critical")

        .when(col("heart_rate") > 120, "Warning")

        .when(col("systolic_bp") > 160, "Warning")

        .when(col("respiratory_rate") > 24, "Warning")

        .otherwise("Normal")

    )

    return df


# =====================================================
# Main
# =====================================================

if __name__ == "__main__":

    spark = create_spark_session()

    df = create_dataframe(spark)

    # ------------------------
    # Validation
    # ------------------------

    df = validate_heart_rate(df)
    df = validate_spo2(df)
    df = validate_temperature(df)
    df = validate_blood_pressure(df)
    df = validate_respiratory_rate(df)

    # ------------------------
    # Patient Status
    # ------------------------

    df = create_status(df)

    # ------------------------
    # Patient Data
    # ------------------------

    print("\n==============================")
    print("PATIENT DATA")
    print("==============================\n")

    df.show(truncate=False)

    # ------------------------
    # Schema
    # ------------------------

    print("\n==============================")
    print("SCHEMA")
    print("==============================\n")

    df.printSchema()

    # ------------------------
    # Columns
    # ------------------------

    print("\n==============================")
    print("COLUMNS")
    print("==============================\n")

    print(df.columns)

    # ------------------------
    # Total Patients
    # ------------------------

    print("\n==============================")
    print("TOTAL PATIENTS")
    print("==============================\n")

    print(df.count())

    # ------------------------
    # Validation Results
    # ------------------------

    print("\n==============================")
    print("VALIDATION RESULTS")
    print("==============================\n")

    df.select(
        "patient_id",

        "heart_rate",
        "hr_valid",

        "spo2",
        "spo2_valid",

        "temperature",
        "temperature_valid",

        "systolic_bp",
        "systolic_valid",

        "diastolic_bp",
        "diastolic_valid",

        "respiratory_rate",
        "respiratory_valid"
    ).show(truncate=False)

    # ------------------------
    # Patient Status
    # ------------------------

    print("\n==============================")
    print("PATIENT STATUS")
    print("==============================\n")

    df.select(
        "patient_id",
        "heart_rate",
        "spo2",
        "temperature",
        "systolic_bp",
        "diastolic_bp",
        "respiratory_rate",
        "status"
    ).show(truncate=False)

    spark.stop()
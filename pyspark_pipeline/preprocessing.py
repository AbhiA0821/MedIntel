import os
import sys

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from pyspark.sql import SparkSession
from database.save_processed_data import save_processed_data


from pyspark.sql.functions import (
    col,
    when,
    avg,
    max,
    min,
    count
)

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
# Read Patients
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
# Generate Records
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
# SPO2 Validation
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
            (col("temperature") >= 35) &
            (col("temperature") <= 42),
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
# Create Status
# =====================================================

def create_status(df):

    return df.withColumn(

        "status",

        when(col("spo2") < 90, "Critical")

        .when(col("temperature") > 38.5, "Critical")

        .when(col("heart_rate") > 120, "Warning")

        .when(col("systolic_bp") > 160, "Warning")

        .when(col("respiratory_rate") > 24, "Warning")

        .otherwise("Normal")
    )


# =====================================================
# Main
# =====================================================

if __name__ == "__main__":

    spark = create_spark_session()

    df = create_dataframe(spark)

    # =====================================================
    # Apply Validations
    # =====================================================

    df = validate_heart_rate(df)
    df = validate_spo2(df)
    df = validate_temperature(df)
    df = validate_blood_pressure(df)
    df = validate_respiratory_rate(df)

    # =====================================================
    # Create Patient Status
    # =====================================================

    df = create_status(df)

    # =====================================================
    # Patient Data
    # =====================================================

    print("\n==============================")
    print("PATIENT DATA")
    print("==============================\n")

    df.show(truncate=False)

    # =====================================================
    # Schema
    # =====================================================

    print("\n==============================")
    print("SCHEMA")
    print("==============================\n")

    df.printSchema()

    # =====================================================
    # Columns
    # =====================================================

    print("\n==============================")
    print("COLUMN NAMES")
    print("==============================\n")

    print(df.columns)

    # =====================================================
    # Total Patients
    # =====================================================

    print("\n==============================")
    print("TOTAL PATIENTS")
    print("==============================\n")

    print(df.count())

    # =====================================================
    # Validation Results
    # =====================================================

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

    # =====================================================
    # Patient Status
    # =====================================================

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

    # =====================================================
    # Count Patients by Status
    # =====================================================

    print("\n==============================")
    print("PATIENT COUNT BY STATUS")
    print("==============================\n")

    df.groupBy("status").count().show()

    # =====================================================
    # Critical Patients
    # =====================================================

    print("\n==============================")
    print("CRITICAL PATIENTS")
    print("==============================\n")

    critical_df = df.filter(col("status") == "Critical")

    critical_df.show(truncate=False)

    # =====================================================
    # Warning Patients
    # =====================================================

    print("\n==============================")
    print("WARNING PATIENTS")
    print("==============================\n")

    warning_df = df.filter(col("status") == "Warning")

    warning_df.show(truncate=False)

    # =====================================================
    # Normal Patients
    # =====================================================

    print("\n==============================")
    print("NORMAL PATIENTS")
    print("==============================\n")

    normal_df = df.filter(col("status") == "Normal")

    normal_df.show(truncate=False)

    # =====================================================
    # Average Heart Rate
    # =====================================================

    print("\n==============================")
    print("AVERAGE HEART RATE")
    print("==============================\n")

    df.select(
        avg("heart_rate").alias("Average Heart Rate")
    ).show()

    # =====================================================
    # Average Temperature
    # =====================================================

    print("\n==============================")
    print("AVERAGE TEMPERATURE")
    print("==============================\n")

    df.select(
        avg("temperature").alias("Average Temperature")
    ).show()

    # =====================================================
    # Average SpO2
    # =====================================================

    print("\n==============================")
    print("AVERAGE SPO2")
    print("==============================\n")

    df.select(
        avg("spo2").alias("Average SPO2")
    ).show()

    # =====================================================
    # Maximum Temperature
    # =====================================================

    print("\n==============================")
    print("MAXIMUM TEMPERATURE")
    print("==============================\n")

    df.select(
        max("temperature").alias("Maximum Temperature")
    ).show()

    # =====================================================
    # Minimum SpO2
    # =====================================================

    print("\n==============================")
    print("MINIMUM SPO2")
    print("==============================\n")

    df.select(
        min("spo2").alias("Minimum SPO2")
    ).show()

    # =====================================================
    # Top 10 Highest Heart Rate
    # =====================================================

    print("\n==============================")
    print("TOP 10 HEART RATE")
    print("==============================\n")

    df.orderBy(
        col("heart_rate").desc()
    ).show(10, truncate=False)

    # =====================================================
    # Lowest SPO2
    # =====================================================

    print("\n==============================")
    print("LOWEST SPO2")
    print("==============================\n")

    df.orderBy(
        col("spo2").asc()
    ).show(10, truncate=False)

    # =====================================================
    # Top 5 Critical Patients
    # =====================================================

    print("\n==============================")
    print("TOP 5 CRITICAL PATIENTS")
    print("==============================\n")

    df.filter(
        col("status") == "Critical"
    ).orderBy(
        col("heart_rate").desc()
    ).show(5, truncate=False)

    # =====================================================
    # High Heart Rate Count
    # =====================================================

    print("\n==============================")
    print("HIGH HEART RATE PATIENTS")
    print("==============================\n")

    high_hr = df.filter(col("heart_rate") > 120).count()

    print("Patients with Heart Rate > 120 :", high_hr)

    # =====================================================
    # Low SPO2 Count
    # =====================================================

    print("\n==============================")
    print("LOW SPO2 PATIENTS")
    print("==============================\n")

    low_spo2 = df.filter(col("spo2") < 90).count()

    print("Patients with SPO2 < 90 :", low_spo2)


    print("\n==============================")
    print("SAVING PROCESSED DATA")
    print("==============================\n")

    save_processed_data(df)

    # =====================================================
    # Stop Spark
    # =====================================================

    spark.stop()
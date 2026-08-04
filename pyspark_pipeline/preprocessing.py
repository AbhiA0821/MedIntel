import os
import sys

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when

from database.connection import get_connection
from database.save_processed_data import save_processed_data


# =====================================================
# Create Spark Session
# =====================================================

def create_spark_session():

    spark = (
        SparkSession.builder
        .appName("MedIntelETL")
        .master("local[2]")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("ERROR")

    return spark


# =====================================================
# Extract Data From DuckDB
# =====================================================

def get_patient_vital_records():

    con = get_connection()

    try:

        records = con.execute("""
            SELECT
                v.vital_id,
                p.patient_id,
                p.first_name,
                p.last_name,
                p.age,
                p.gender,
                p.blood_group,
                p.ward,
                p.admission_date,

                v.heart_rate,
                v.spo2,
                v.temperature,
                v.systolic_bp,
                v.diastolic_bp,
                v.respiratory_rate,
                v.recorded_at

            FROM VitalSigns v

            INNER JOIN Patients p
                ON v.patient_id = p.patient_id

            ORDER BY v.recorded_at DESC
        """).fetchall()

        columns = [
            description[0]
            for description in con.description
        ]

        return records, columns

    finally:
        con.close()


# =====================================================
# Create Spark DataFrame
# =====================================================

def create_dataframe(spark):

    records, columns = get_patient_vital_records()

    if not records:
        return None

    data = [
        dict(zip(columns, record))
        for record in records
    ]

    return spark.createDataFrame(data)


# =====================================================
# Validate Heart Rate
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
# Validate SpO2
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
# Validate Temperature
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
# Validate Blood Pressure
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
# Validate Respiratory Rate
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
# Temporary Baseline Status
# =====================================================
# NOTE:
# This is NOT the final ML prediction.
# It is retained only as a temporary baseline while
# the ML module is being developed.
# =====================================================

def create_status(df):

    return df.withColumn(
        "status",

        when(
            col("spo2") < 90,
            "Critical"
        )

        .when(
            col("temperature") > 38.5,
            "Critical"
        )

        .when(
            col("heart_rate") > 120,
            "Warning"
        )

        .when(
            col("systolic_bp") > 160,
            "Warning"
        )

        .when(
            col("respiratory_rate") > 24,
            "Warning"
        )

        .otherwise("Normal")
    )


# =====================================================
# Apply Transformations
# =====================================================

def preprocess_data(df):

    df = validate_heart_rate(df)

    df = validate_spo2(df)

    df = validate_temperature(df)

    df = validate_blood_pressure(df)

    df = validate_respiratory_rate(df)

    df = create_status(df)

    return df


# =====================================================
# Main ETL Pipeline
# =====================================================

def run_pipeline():

    print("\n" + "=" * 55)
    print("MEDINTEL PYSPARK ETL STARTED")
    print("=" * 55)

    spark = create_spark_session()

    try:

        # ---------------------------------------------
        # EXTRACT
        # ---------------------------------------------

        print("[1/4] Reading VitalSigns from DuckDB...")

        df = create_dataframe(spark)

        if df is None:

            print("No vital records available.")
            return

        # ---------------------------------------------
        # TRANSFORM
        # ---------------------------------------------

        print("[2/4] Running PySpark preprocessing...")

        df = preprocess_data(df)

        # ---------------------------------------------
        # LOAD
        # ---------------------------------------------

        print("[3/4] Saving processed records to DuckDB...")

        save_processed_data(df)

        # ---------------------------------------------
        # COMPLETE
        # ---------------------------------------------

        print("[4/4] ETL completed successfully.")

        print("=" * 55)
        print("MEDINTEL PYSPARK ETL COMPLETED")
        print("=" * 55)

    except Exception as e:

        print("\nMEDINTEL PYSPARK ETL FAILED")
        print(f"Error: {e}")

        raise

    finally:

        spark.stop()


# =====================================================
# Application Entry Point
# =====================================================

if __name__ == "__main__":

    run_pipeline()
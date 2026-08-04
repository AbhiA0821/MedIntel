import os
import sys

os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when

from database.connection import get_connection
from database.save_processed_data import save_processed_data


# =====================================================
# Spark Session
# =====================================================

def create_spark_session():

    spark = (
        SparkSession.builder
        .appName("MedIntelContinuousMonitoring")
        .master("local[2]")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("ERROR")

    return spark


# =====================================================
# Read ONLY Newly Generated Vital Records
# =====================================================

def get_patient_vital_records(vital_ids):

    if not vital_ids:
        return [], []

    con = get_connection()

    try:

        placeholders = ",".join(
            ["?"] * len(vital_ids)
        )

        query = f"""
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

            WHERE v.vital_id IN ({placeholders})

            ORDER BY v.vital_id
        """

        records = con.execute(
            query,
            vital_ids
        ).fetchall()

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

def create_dataframe(spark, vital_ids):

    records, columns = get_patient_vital_records(
        vital_ids
    )

    if not records:
        return None

    data = [
        dict(zip(columns, record))
        for record in records
    ]

    return spark.createDataFrame(data)


# =====================================================
# Validation
# =====================================================

def preprocess_data(df):

    df = df.withColumn(
        "hr_valid",
        when(
            (col("heart_rate") >= 40) &
            (col("heart_rate") <= 180),
            True
        ).otherwise(False)
    )

    df = df.withColumn(
        "spo2_valid",
        when(
            (col("spo2") >= 90) &
            (col("spo2") <= 100),
            True
        ).otherwise(False)
    )

    df = df.withColumn(
        "temperature_valid",
        when(
            (col("temperature") >= 35) &
            (col("temperature") <= 42),
            True
        ).otherwise(False)
    )

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

    df = df.withColumn(
        "respiratory_valid",
        when(
            (col("respiratory_rate") >= 8) &
            (col("respiratory_rate") <= 30),
            True
        ).otherwise(False)
    )

    # Temporary baseline only.
    # Final status will later come from ML.
    df = df.withColumn(
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

    return df


# =====================================================
# Process ONE New Batch
# =====================================================

def process_batch(spark, vital_ids):

    if not vital_ids:
        print("No new vital records to process.")
        return None

    print(
        f"Processing {len(vital_ids)} new vital readings..."
    )

    df = create_dataframe(
        spark,
        vital_ids
    )

    if df is None:
        print("No matching vital records found.")
        return None

    df = preprocess_data(df)

    save_processed_data(df)

    print(
        f"Successfully processed "
        f"{len(vital_ids)} vital readings."
    )

    return df


# =====================================================
# Standalone Test
# =====================================================

if __name__ == "__main__":

    print(
        "Run this module through "
        "services.monitoring_pipeline."
    )
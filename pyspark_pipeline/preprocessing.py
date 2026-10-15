from pyspark.sql.functions import col, when
from pyspark.sql.types import (
    StructType, StructField, IntegerType,
    DoubleType, TimestampType
)


def define_schema():
    """
    Define Schema for patient vitals dataset.
    """
    return StructType([
        StructField("vital_id", IntegerType(), True),
        StructField("patient_id", IntegerType(), True),
        StructField("heart_rate", IntegerType(), True),
        StructField("spo2", IntegerType(), True),
        StructField("temperature", DoubleType(), True),
        StructField("systolic_bp", IntegerType(), True),
        StructField("diastolic_bp", IntegerType(), True),
        StructField("respiratory_rate", IntegerType(), True),
        StructField("recorded_at", TimestampType(), True)
    ])


def preprocess_data(df):
    """
    Preprocess vitals dataframe: apply validation boundaries and status classification.
    """
    validated_df = df.filter(
        (col("heart_rate") >= 30) & (col("heart_rate") <= 250) &
        (col("spo2") >= 50) & (col("spo2") <= 100) &
        (col("temperature") >= 30.0) & (col("temperature") <= 45.0) &
        (col("systolic_bp") >= 50) & (col("systolic_bp") <= 250) &
        (col("diastolic_bp") >= 30) & (col("diastolic_bp") <= 150) &
        (col("respiratory_rate") >= 5) & (col("respiratory_rate") <= 60)
    )

    classified_df = validated_df.withColumn(
        "status",
        when(col("spo2") < 90, "CRITICAL")
        .when(col("temperature") > 38.5, "CRITICAL")
        .when(col("heart_rate") > 120, "MODERATE")
        .when(col("systolic_bp") > 160, "MODERATE")
        .when(col("respiratory_rate") > 24, "MODERATE")
        .otherwise("LOW")
    )

    return classified_df
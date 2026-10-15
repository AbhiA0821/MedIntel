import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, when
from pyspark.sql.types import (
    StructType, StructField, IntegerType,
    DoubleType, StringType, TimestampType
)

def create_spark_session(app_name="MedIntel-Kafka-Streaming"):
    """
    Instantiate SparkSession with PySpark Kafka connector dependencies.
    """
    spark = SparkSession.builder \
        .appName(app_name) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.sql.shuffle.partitions", "2") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    return spark


def define_vitals_schema():
    """
    Define Schema matching vital event JSON published to Kafka.
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
        StructField("recorded_at", StringType(), True)
    ])


def read_vitals_kafka_stream(spark, bootstrap_servers="localhost:9094", topic="medintel-vitals"):
    """
    Read structured streaming DataFrame from Kafka topic.
    """
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", bootstrap_servers) \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .load()


def process_vitals_stream(streaming_df):
    """
    Parse JSON payload, validate vitals, and classify patient severity status.
    """
    schema = define_vitals_schema()

    # 1. Deserialize JSON value
    parsed_df = streaming_df.selectExpr("CAST(value AS STRING) as json_payload") \
        .select(from_json(col("json_payload"), schema).alias("data")) \
        .select("data.*")

    # 2. Convert recorded_at to Timestamp
    timestamped_df = parsed_df.withColumn(
        "recorded_at",
        col("recorded_at").cast(TimestampType())
    )

    # 3. Data Validation Rules
    validated_df = timestamped_df.filter(
        (col("heart_rate") >= 30) & (col("heart_rate") <= 250) &
        (col("spo2") >= 50) & (col("spo2") <= 100) &
        (col("temperature") >= 30.0) & (col("temperature") <= 45.0) &
        (col("systolic_bp") >= 50) & (col("systolic_bp") <= 250) &
        (col("diastolic_bp") >= 30) & (col("diastolic_bp") <= 150) &
        (col("respiratory_rate") >= 5) & (col("respiratory_rate") <= 60)
    )

    # 4. Status Classification Rules
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


def write_stream_to_duckdb_batch(batch_df, batch_id):
    """
    Micro-batch writer persisting PySpark streaming output to DuckDB.
    """
    if batch_df.isEmpty():
        return

    import duckdb
    from database.connection import DB_PATH

    rows = batch_df.collect()
    print(f"[PYSPARK STREAMING] Processing micro-batch {batch_id} with {len(rows)} records...")

    con = duckdb.connect(str(DB_PATH))
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        if "ProcessedPatientVitals" not in tables:
            con.execute("""
                CREATE TABLE ProcessedPatientVitals (
                    vital_id INTEGER PRIMARY KEY,
                    patient_id INTEGER,
                    heart_rate INTEGER,
                    spo2 INTEGER,
                    temperature DOUBLE,
                    systolic_bp INTEGER,
                    diastolic_bp INTEGER,
                    respiratory_rate INTEGER,
                    status VARCHAR,
                    recorded_at TIMESTAMP,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

        records = [
            (
                row["vital_id"],
                row["patient_id"],
                row["heart_rate"],
                row["spo2"],
                row["temperature"],
                row["systolic_bp"],
                row["diastolic_bp"],
                row["respiratory_rate"],
                row["status"],
                row["recorded_at"]
            )
            for row in rows
        ]

        con.executemany("""
            INSERT OR REPLACE INTO ProcessedPatientVitals (
                vital_id, patient_id, heart_rate, spo2, temperature,
                systolic_bp, diastolic_bp, respiratory_rate, status, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, records)
        print(f"[PYSPARK STREAMING] Micro-batch {batch_id} successfully persisted {len(records)} records to DuckDB.")
    finally:
        con.close()


def run_kafka_streaming_pipeline(bootstrap_servers="localhost:9094", topic="medintel-vitals"):
    """
    Execute end-to-end Structured Streaming pipeline.
    """
    spark = create_spark_session()
    raw_stream = read_vitals_kafka_stream(spark, bootstrap_servers, topic)
    processed_stream = process_vitals_stream(raw_stream)

    query = processed_stream.writeStream \
        .foreachBatch(write_stream_to_duckdb_batch) \
        .outputMode("append") \
        .start()

    query.awaitTermination()


if __name__ == "__main__":
    print("Starting MedIntel PySpark Structured Streaming Pipeline...")
    run_kafka_streaming_pipeline()

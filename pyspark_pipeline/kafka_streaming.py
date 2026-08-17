import os
import sys
from pathlib import Path

# Configure PySpark executable environment
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

# Set HADOOP_HOME for Windows compatibility if winutils is located in project root
if sys.platform.startswith("win"):
    project_root = Path(__file__).resolve().parent.parent
    hadoop_dir = project_root / "hadoop"
    if hadoop_dir.exists():
        os.environ["HADOOP_HOME"] = str(hadoop_dir)

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, when
from pyspark.sql.types import (
    StructType,
    StructField,
    IntegerType,
    DoubleType,
    StringType
)


from database.save_streaming_processed_data import save_streaming_processed_data


# =====================================================
# Spark Session Creation
# =====================================================

def create_streaming_spark_session(bootstrap_servers=None):
    """
    Create a PySpark SparkSession configured with the Kafka Structured Streaming package.
    """
    if bootstrap_servers is None:
        bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")

    builder = (
        SparkSession.builder
        .appName("MedIntelKafkaStructuredStreaming")
        .master("local[1]")
        .config("spark.driver.host", "localhost")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0")
        .config("spark.hadoop.fs.permissions.umask-mode", "000")
    )

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


# =====================================================
# Schema Definition for medintel-vitals JSON Payload
# =====================================================

def get_vitals_schema():
    """
    Define the explicit PySpark schema for JSON events in medintel-vitals topic.
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


# =====================================================
# DataFrame Transformation & Validation
# =====================================================

def process_vitals_stream(streaming_df):
    """
    Parse Kafka JSON payloads, extract columns, apply validation flags and status classification rules.
    """
    schema = get_vitals_schema()

    # 1. Parse JSON value payload from Kafka byte stream
    parsed_df = (
        streaming_df
        .selectExpr("CAST(key AS STRING) as kafka_key", "CAST(value AS STRING) as json_value", "timestamp as kafka_timestamp")
        .select("kafka_key", "kafka_timestamp", from_json(col("json_value"), schema).alias("data"))
        .select("kafka_key", "kafka_timestamp", "data.*")
    )

    # 2. Range Validation Flags
    validated_df = parsed_df.withColumn(
        "hr_valid",
        when((col("heart_rate") >= 40) & (col("heart_rate") <= 180), True).otherwise(False)
    ).withColumn(
        "spo2_valid",
        when((col("spo2") >= 90) & (col("spo2") <= 100), True).otherwise(False)
    ).withColumn(
        "temperature_valid",
        when((col("temperature") >= 35.0) & (col("temperature") <= 42.0), True).otherwise(False)
    ).withColumn(
        "systolic_valid",
        when((col("systolic_bp") >= 90) & (col("systolic_bp") <= 180), True).otherwise(False)
    ).withColumn(
        "diastolic_valid",
        when((col("diastolic_bp") >= 60) & (col("diastolic_bp") <= 120), True).otherwise(False)
    ).withColumn(
        "respiratory_valid",
        when((col("respiratory_rate") >= 8) & (col("respiratory_rate") <= 30), True).otherwise(False)
    )

    # 3. Status Classification Rules
    classified_df = validated_df.withColumn(
        "status",
        when(col("spo2") < 90, "Critical")
        .when(col("temperature") > 38.5, "Critical")
        .when(col("heart_rate") > 120, "Warning")
        .when(col("systolic_bp") > 160, "Warning")
        .when(col("respiratory_rate") > 24, "Warning")
        .otherwise("Normal")
    )

    return classified_df


# =====================================================
# Micro-Batch Handler (Display + DuckDB Persistence)
# =====================================================

def handle_micro_batch(batch_df, epoch_id):
    count = batch_df.count()
    if count == 0:
        return

    print(f"\n" + "=" * 70, flush=True)
    print(f"STREAMING MICRO-BATCH {epoch_id} | Received {count} vital events", flush=True)
    print("=" * 70, flush=True)

    batch_df.select(
        "vital_id",
        "patient_id",
        "heart_rate",
        "spo2",
        "temperature",
        "systolic_bp",
        "diastolic_bp",
        "respiratory_rate",
        "hr_valid",
        "spo2_valid",
        "status",
        "recorded_at"
    ).show(10, truncate=False)

    save_streaming_processed_data(batch_df, epoch_id)


# =====================================================
# Streaming Verification Execution
# =====================================================

def run_streaming_verification(bootstrap_servers=None, topic_name="medintel-vitals"):
    """
    Connect to Kafka as a Structured Stream, process available batches, and persist to DuckDB.
    """
    if bootstrap_servers is None:
        if len(sys.argv) > 1:
            bootstrap_servers = sys.argv[1]
        else:
            bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")

    project_root = Path(__file__).resolve().parent.parent
    checkpoint_dir = os.environ.get(
        "SPARK_CHECKPOINT_DIR",
        str(project_root / "checkpoints" / "medintel-vitals")
    )
    os.makedirs(checkpoint_dir, exist_ok=True)

    print("=" * 70, flush=True)
    print("MEDINTEL PYSPARK STRUCTURED STREAMING PIPELINE (KAFKA -> PYSPARK -> DUCKDB)", flush=True)
    print(f"Broker: {bootstrap_servers} | Topic: {topic_name}", flush=True)
    print(f"Checkpoint: {checkpoint_dir}", flush=True)
    print("=" * 70, flush=True)

    spark = create_streaming_spark_session(bootstrap_servers=bootstrap_servers)

    try:
        raw_stream_df = (
            spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", bootstrap_servers)
            .option("subscribe", topic_name)
            .option("startingOffsets", "earliest")
            .load()
        )

        processed_stream_df = process_vitals_stream(raw_stream_df)

        query = (
            processed_stream_df.writeStream
            .trigger(availableNow=True)
            .option("checkpointLocation", checkpoint_dir)
            .foreachBatch(handle_micro_batch)
            .start()
        )

        print("[Processing available Kafka stream batches...]", flush=True)
        query.awaitTermination()
        print("[Streaming verification complete. Query stopped cleanly.]", flush=True)

    finally:
        spark.stop()


if __name__ == "__main__":
    run_streaming_verification()


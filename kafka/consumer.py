import json
import warnings
from kafka import KafkaConsumer

# Suppress kafka-python deserializer/serializer interface deprecation warnings for clean output
warnings.filterwarnings("ignore", category=DeprecationWarning, module="kafka")

# ==============================================================================
# MedIntel Kafka Consumer (Learning / Basic Implementation)
# ==============================================================================
# Key Kafka Concepts Covered:
# 1. Consumer: Application that subscribes to topics and processes stream messages.
# 2. Consumer Group: Group of consumers sharing topic subscriptions. Kafka balances
#    partitions among consumers in the group ('medintel-learning-group').
# 3. Deserializer: Converts byte arrays back into Python keys and JSON objects.
# 4. Auto Offset Reset: Controls starting position when reading a partition without
#    a committed offset ('earliest' reads from beginning of available records).
# 5. Partition Offset: Unique sequential integer assigned to each record in a partition.
# ==============================================================================

def run_consumer():
    topic_name = 'patient-vitals'
    group_id = 'medintel-learning-group'

    print(f"[Consumer] Starting Kafka Consumer...", flush=True)
    print(f"  - Broker:         localhost:9094", flush=True)
    print(f"  - Topic:          {topic_name}", flush=True)
    print(f"  - Consumer Group: {group_id}", flush=True)
    print("[Consumer] Waiting for incoming messages (Press Ctrl+C to exit)...\n", flush=True)

    # Instantiate KafkaConsumer with JSON deserializers and consumer group
    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers=['localhost:9094'],
        group_id=group_id,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        # Deserializers decode UTF-8 byte streams to string keys and dict values
        key_deserializer=lambda k: k.decode('utf-8') if k else None,
        value_deserializer=lambda v: json.loads(v.decode('utf-8')) if v else None
    )

    try:
        # Poll and consume messages sequentially
        for message in consumer:
            print("=" * 60, flush=True)
            print(f"[Received Event] Topic: {message.topic} | Partition: {message.partition} | Offset: {message.offset}", flush=True)
            print(f"Key (patient_id): {message.key}", flush=True)
            print(f"Timestamp:        {message.timestamp}", flush=True)
            print("Decoded Message Payload:", flush=True)
            print(json.dumps(message.value, indent=2), flush=True)
            print("=" * 60 + "\n", flush=True)

    except KeyboardInterrupt:
        print("\n[Consumer] Stopping consumer on user interrupt...", flush=True)
    finally:
        consumer.close()
        print("[Consumer] Consumer closed cleanly.", flush=True)

if __name__ == "__main__":
    run_consumer()

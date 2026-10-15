import os
import json
import warnings
import socket
from kafka import KafkaConsumer

# Suppress kafka-python deserializer/serializer interface deprecation warnings for clean output
warnings.filterwarnings("ignore", category=DeprecationWarning, module="kafka")

# ==============================================================================
# MedIntel Kafka Consumer
# Subscribes to vital sign telemetry stream from MedIntel producer.
# ==============================================================================

def _is_kafka_broker_reachable(host='localhost', port=9094, timeout=0.2):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def run_consumer():
    topic_name = os.environ.get('KAFKA_TOPIC_VITALS', 'medintel-vitals')
    bootstrap_server_str = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9094')
    bootstrap_servers = [s.strip() for s in bootstrap_server_str.split(',') if s.strip()]
    group_id = os.environ.get('KAFKA_CONSUMER_GROUP', 'medintel-learning-group')

    first_server = bootstrap_servers[0] if bootstrap_servers else 'localhost:9094'
    host, _, port = first_server.partition(':')
    port = int(port) if port else 9094

    print(f"[Consumer] Starting Kafka Consumer...", flush=True)
    print(f"  - Broker:         {bootstrap_server_str}", flush=True)
    print(f"  - Topic:          {topic_name}", flush=True)
    print(f"  - Consumer Group: {group_id}", flush=True)

    if not _is_kafka_broker_reachable(host, port):
        print(f"[Consumer NOTICE] Kafka broker at {first_server} is not reachable.", flush=True)
        print("  - Running in direct DuckDB ingestion mode. Start Kafka broker to consume real-time stream.", flush=True)
        return

    print("[Consumer] Waiting for incoming messages (Press Ctrl+C to exit)...\n", flush=True)

    # Instantiate KafkaConsumer with JSON deserializers and consumer group
    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers=bootstrap_servers,
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

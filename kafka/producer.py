import json
import warnings
from datetime import datetime, timezone
from kafka import KafkaProducer

# Suppress kafka-python deserializer/serializer interface deprecation warnings for clean output
warnings.filterwarnings("ignore", category=DeprecationWarning, module="kafka")

# ==============================================================================
# MedIntel Kafka Producer
# ==============================================================================

def get_kafka_producer(bootstrap_servers=['localhost:9094']):
    """
    Instantiate and return a configured KafkaProducer instance.
    """
    return KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        key_serializer=lambda k: str(k).encode('utf-8'),
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )


def publish_vitals_batch_to_kafka(batch, topic_name='medintel-vitals', bootstrap_servers=['localhost:9094']):
    """
    Publish a batch of vital sign tuples to Kafka.

    Batch format expected:
    List of tuples: (vital_id, patient_id, heart_rate, spo2, temperature,
                    systolic_bp, diastolic_bp, respiratory_rate, recorded_at)
    """
    if not batch:
        return 0

    sent_count = 0
    try:
        producer = get_kafka_producer(bootstrap_servers=bootstrap_servers)

        for item in batch:
            vital_id, patient_id, hr, spo2, temp, sys_bp, dia_bp, resp, recorded_at = item

            recorded_at_str = recorded_at.isoformat() if hasattr(recorded_at, 'isoformat') else str(recorded_at)

            payload = {
                "vital_id": int(vital_id),
                "patient_id": int(patient_id) if str(patient_id).isdigit() else str(patient_id),
                "heart_rate": int(hr),
                "spo2": int(spo2),
                "temperature": float(temp),
                "systolic_bp": int(sys_bp),
                "diastolic_bp": int(dia_bp),
                "respiratory_rate": int(resp),
                "recorded_at": recorded_at_str
            }

            key = str(patient_id)
            producer.send(topic_name, key=key, value=payload)
            sent_count += 1

        producer.flush()
        producer.close()
        print(f"[Kafka Producer] Successfully published {sent_count} vital records to topic '{topic_name}'.", flush=True)
        return sent_count

    except Exception as e:
        print(f"[Kafka Producer Warning] Failed to publish batch to Kafka: {e}", flush=True)
        return 0


def run_producer():
    """
    Standalone test producer runner.
    """
    topic_name = 'medintel-vitals'
    sample_event = {
        "vital_id": 9999,
        "patient_id": 101,
        "heart_rate": 78,
        "spo2": 98,
        "temperature": 98.6,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "respiratory_rate": 16,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }

    patient_id = sample_event["patient_id"]
    key_str = str(patient_id)
    print(f"[Producer Test] Connecting to Kafka broker at localhost:9094...", flush=True)
    print(f"[Producer Test] Sending event for Patient ID '{patient_id}' to topic '{topic_name}'...", flush=True)

    try:
        producer = get_kafka_producer(bootstrap_servers=['localhost:9094'])
        future = producer.send(topic=topic_name, key=key_str, value=sample_event)
        record_metadata = future.get(timeout=10)

        print(f"[Producer Test] Successfully sent message!", flush=True)
        print(f"  - Topic:     {record_metadata.topic}", flush=True)
        print(f"  - Partition: {record_metadata.partition}", flush=True)
        print(f"  - Offset:    {record_metadata.offset}", flush=True)
        print(f"  - Key:       {patient_id}", flush=True)
        print(f"  - Value:     {sample_event}", flush=True)

        producer.flush()
        producer.close()

    except Exception as e:
        print(f"[Producer Test] Error sending message: {e}", flush=True)


if __name__ == "__main__":
    run_producer()

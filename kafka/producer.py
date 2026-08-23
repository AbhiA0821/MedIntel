import json
import warnings
import socket

# Suppress kafka-python deserializer/serializer interface deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from kafka import KafkaProducer
except ImportError:
    KafkaProducer = None


def _is_kafka_broker_reachable(host='localhost', port=9094, timeout=0.1):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_kafka_producer(bootstrap_servers=['localhost:9094']):
    """
    Instantiate and return a configured KafkaProducer instance.
    Returns None immediately if Kafka broker is unreachable or kafka-python library is not installed.
    """
    if KafkaProducer is None or not _is_kafka_broker_reachable():
        return None

    try:
        return KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            max_block_ms=500,
            request_timeout_ms=500,
            key_serializer=lambda k: str(k).encode('utf-8'),
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    except Exception:
        return None


def publish_vitals_batch_to_kafka(batch, topic_name='medintel-vitals', bootstrap_servers=['localhost:9094']):
    """
    Publish a batch of vital sign tuples to Kafka.
    batch: List of tuples (vital_id, patient_id, hr, spo2, temp, sys_bp, dia_bp, resp, recorded_at)
    """
    if not batch:
        return 0

    sent_count = 0
    try:
        producer = get_kafka_producer(bootstrap_servers=bootstrap_servers)
        if not producer:
            return 0

        for item in batch:
            vital_id, patient_id, hr, spo2, temp, sys_bp, dia_bp, resp, recorded_at = item
            payload = {
                "vital_id": vital_id,
                "patient_id": patient_id,
                "heart_rate": hr,
                "spo2": spo2,
                "temperature": float(temp),
                "systolic_bp": sys_bp,
                "diastolic_bp": dia_bp,
                "respiratory_rate": resp,
                "recorded_at": recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else str(recorded_at)
            }
            producer.send(topic_name, key=str(patient_id), value=payload)
            sent_count += 1

        producer.flush(timeout=1.0)
        print(f"[KAFKA PRODUCER] Successfully published {sent_count} vital events to '{topic_name}'.")
        return sent_count
    except Exception as e:
        print(f"[KAFKA PRODUCER WARNING] Kafka publication skipped: {e}")
        return sent_count

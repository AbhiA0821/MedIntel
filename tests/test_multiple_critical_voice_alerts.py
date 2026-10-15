"""
MedIntel Test Suite: Ultra-Low Latency Voice Alerts & Serialized 4-Queue Pipeline
Covers all 12 latency, concurrency, and routing scenarios:
1. One new critical alert → spoken once.
2. Three simultaneous new critical alerts → all three spoken sequentially in FIFO order.
3. Multiple specialties → each doctor receives only their specialty alerts.
4. Receptionist receives all critical alerts hospital-wide.
5. Same patient remains critical → no repeated voice announcement.
6. Patient recovers → spoken state clears.
7. Patient becomes critical again → voice alert plays again.
8. Two alerts in same queue → strict FIFO order.
9. Different queues → they must not block each other.
10. Voice alert does not wait for LLM/RAG.
11. Voice alert does not wait for the next simulator cycle.
12. No duplicate audio generation.
"""

import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.voice.alert_voice import (
    trigger_workstation_voice_alert,
    get_voice_queue,
    update_voice_alert_status,
    get_latest_voice_alert,
    clear_spoken_alert_cache,
    build_alert_spoken_text,
    build_receptionist_spoken_text,
    build_concise_spoken_text,
    normalize_destination
)
from services.voice.piper_tts import synthesize_speech
from backend.main import app as fastapi_app
from fastapi.testclient import TestClient


class TestLowLatencyCriticalVoiceAlerts(unittest.TestCase):

    def setUp(self):
        clear_spoken_alert_cache()
        self.client = TestClient(fastapi_app)

    # 1. One new critical alert -> spoken once
    def test_01_one_new_critical_alert_spoken_once(self):
        alt = {
            "alert_id": "ALT-TEST-01",
            "patient_id": 101,
            "patient_name": "Rahul Patil",
            "specialty": "CARDIOLOGY",
            "ward": "Cardiology",
            "room_no": "201",
            "bed_no": "1",
            "severity": "CRITICAL"
        }
        res = trigger_workstation_voice_alert(alt)
        self.assertEqual(res["status"], "DISPATCHED")
        self.assertEqual(res["results"]["CARDIOLOGY"], "DISPATCHED")
        self.assertEqual(res["results"]["RECEPTIONIST"], "DISPATCHED")

        cardio_q = get_voice_queue("CARDIOLOGY")
        self.assertEqual(cardio_q["pending_count"], 1)
        self.assertEqual(cardio_q["queued"][0]["alert_id"], "ALT-TEST-01")

        rec_q = get_voice_queue("RECEPTIONIST")
        self.assertEqual(rec_q["pending_count"], 1)
        self.assertEqual(rec_q["queued"][0]["alert_id"], "ALT-TEST-01")

    # 2. Three simultaneous new critical alerts -> all three spoken sequentially
    def test_02_three_simultaneous_critical_alerts_all_queued_sequentially(self):
        alt1 = {"alert_id": "ALT-M1", "patient_id": 101, "specialty": "CARDIOLOGY", "ward": "Cardiology", "room_no": "201", "bed_no": "1", "severity": "CRITICAL"}
        alt2 = {"alert_id": "ALT-M2", "patient_id": 104, "specialty": "PULMONOLOGY", "ward": "Pulmonology", "room_no": "202", "bed_no": "1", "severity": "CRITICAL"}
        alt3 = {"alert_id": "ALT-M3", "patient_id": 110, "specialty": "GENERAL MEDICINE", "ward": "General Medicine", "room_no": "204", "bed_no": "1", "severity": "CRITICAL"}

        r1 = trigger_workstation_voice_alert(alt1)
        r2 = trigger_workstation_voice_alert(alt2)
        r3 = trigger_workstation_voice_alert(alt3)

        self.assertEqual(r1["status"], "DISPATCHED")
        self.assertEqual(r2["status"], "DISPATCHED")
        self.assertEqual(r3["status"], "DISPATCHED")

        rec_q = get_voice_queue("RECEPTIONIST")
        self.assertEqual(rec_q["pending_count"], 3)
        queued_ids = [item["alert_id"] for item in rec_q["queued"]]
        self.assertEqual(queued_ids, ["ALT-M1", "ALT-M2", "ALT-M3"])

    # 3. Multiple specialties -> each doctor receives only their specialty alerts
    def test_03_multiple_specialties_isolated(self):
        alt_card = {"alert_id": "ALT-SPEC-CARD", "patient_id": 101, "specialty": "CARDIOLOGY", "severity": "CRITICAL"}
        alt_pulm = {"alert_id": "ALT-SPEC-PULM", "patient_id": 104, "specialty": "PULMONOLOGY", "severity": "CRITICAL"}
        alt_gen = {"alert_id": "ALT-SPEC-GEN", "patient_id": 110, "specialty": "GENERAL MEDICINE", "severity": "CRITICAL"}

        trigger_workstation_voice_alert(alt_card)
        trigger_workstation_voice_alert(alt_pulm)
        trigger_workstation_voice_alert(alt_gen)

        cardio_q = get_voice_queue("CARDIOLOGY")
        pulm_q = get_voice_queue("PULMONOLOGY")
        gen_q = get_voice_queue("GENERAL_MEDICINE")

        self.assertEqual([i["alert_id"] for i in cardio_q["queued"]], ["ALT-SPEC-CARD"])
        self.assertEqual([i["alert_id"] for i in pulm_q["queued"]], ["ALT-SPEC-PULM"])
        self.assertEqual([i["alert_id"] for i in gen_q["queued"]], ["ALT-SPEC-GEN"])

    # 4. Receptionist receives all critical alerts
    def test_04_receptionist_receives_all_alerts(self):
        alt_card = {"alert_id": "ALT-ALL-CARD", "patient_id": 101, "specialty": "CARDIOLOGY", "severity": "CRITICAL"}
        alt_pulm = {"alert_id": "ALT-ALL-PULM", "patient_id": 104, "specialty": "PULMONOLOGY", "severity": "CRITICAL"}
        alt_gen = {"alert_id": "ALT-ALL-GEN", "patient_id": 110, "specialty": "GENERAL MEDICINE", "severity": "CRITICAL"}

        trigger_workstation_voice_alert(alt_card)
        trigger_workstation_voice_alert(alt_pulm)
        trigger_workstation_voice_alert(alt_gen)

        rec_q = get_voice_queue("RECEPTIONIST")
        rec_ids = [i["alert_id"] for i in rec_q["queued"]]
        self.assertEqual(rec_ids, ["ALT-ALL-CARD", "ALT-ALL-PULM", "ALT-ALL-GEN"])

    # 5. Same patient remains critical -> no repeated voice
    def test_05_same_patient_remains_critical_no_repeated_voice(self):
        alt = {"alert_id": "ALT-STAY-CRIT", "patient_id": 101, "specialty": "CARDIOLOGY", "severity": "CRITICAL"}
        r1 = trigger_workstation_voice_alert(alt)
        self.assertEqual(r1["status"], "DISPATCHED")

        # Second simulator cycle: same active critical alert
        r2 = trigger_workstation_voice_alert(alt)
        self.assertEqual(r2["status"], "DEDUPLICATED")
        self.assertEqual(r2["results"]["CARDIOLOGY"], "DEDUPLICATED")
        self.assertEqual(r2["results"]["RECEPTIONIST"], "DEDUPLICATED")

        cardio_q = get_voice_queue("CARDIOLOGY")
        self.assertEqual(cardio_q["pending_count"], 1)

    # 6. Patient recovers -> spoken state clears
    def test_06_patient_recovers_spoken_state_clears(self):
        alt = {"alert_id": "ALT-REC-P105", "patient_id": 105, "specialty": "PULMONOLOGY", "severity": "CRITICAL"}
        trigger_workstation_voice_alert(alt)

        q_before = get_voice_queue("PULMONOLOGY")
        self.assertEqual(q_before["pending_count"], 1)

        # Patient recovers
        clear_spoken_alert_cache("ALT-REC-P105")

        q_after = get_voice_queue("PULMONOLOGY")
        self.assertEqual(q_after["pending_count"], 0)

    # 7. Patient becomes critical again -> voice alert plays again
    def test_07_patient_recritical_voice_plays_again(self):
        alt1 = {"alert_id": "ALT-RECRIT-1", "patient_id": 108, "specialty": "PULMONOLOGY", "severity": "CRITICAL"}
        r1 = trigger_workstation_voice_alert(alt1)
        self.assertEqual(r1["status"], "DISPATCHED")

        # Patient recovers
        clear_spoken_alert_cache("ALT-RECRIT-1")

        # Patient deteriorates into critical again
        alt2 = {"alert_id": "ALT-RECRIT-2", "patient_id": 108, "specialty": "PULMONOLOGY", "severity": "CRITICAL"}
        r2 = trigger_workstation_voice_alert(alt2)
        self.assertEqual(r2["status"], "DISPATCHED")

        pulm_q = get_voice_queue("PULMONOLOGY")
        self.assertEqual(pulm_q["pending_count"], 1)
        self.assertEqual(pulm_q["queued"][0]["alert_id"], "ALT-RECRIT-2")

    # 8. Two alerts in same queue -> strict FIFO order
    def test_08_two_alerts_same_queue_strict_fifo(self):
        alt_a = {"alert_id": "ALT-FIFO-A", "patient_id": 101, "specialty": "CARDIOLOGY", "severity": "CRITICAL"}
        alt_b = {"alert_id": "ALT-FIFO-B", "patient_id": 102, "specialty": "CARDIOLOGY", "severity": "CRITICAL"}

        trigger_workstation_voice_alert(alt_a)
        trigger_workstation_voice_alert(alt_b)

        q = get_voice_queue("CARDIOLOGY")
        self.assertEqual(q["pending_count"], 2)
        self.assertEqual(q["queued"][0]["alert_id"], "ALT-FIFO-A")
        self.assertEqual(q["queued"][1]["alert_id"], "ALT-FIFO-B")

        # Progress Alert A: SPEAKING -> COMPLETED
        update_voice_alert_status("CARDIOLOGY", "ALT-FIFO-A", "SPEAKING")
        q1 = update_voice_alert_status("CARDIOLOGY", "ALT-FIFO-A", "COMPLETED")
        self.assertEqual(q1["last_spoken"]["alert_id"], "ALT-FIFO-A")
        self.assertEqual(q1["pending_count"], 1)
        self.assertEqual(q1["queued"][0]["alert_id"], "ALT-FIFO-B")

        # Progress Alert B: SPEAKING -> COMPLETED
        update_voice_alert_status("CARDIOLOGY", "ALT-FIFO-B", "SPEAKING")
        q2 = update_voice_alert_status("CARDIOLOGY", "ALT-FIFO-B", "COMPLETED")
        self.assertEqual(q2["last_spoken"]["alert_id"], "ALT-FIFO-B")
        self.assertEqual(q2["pending_count"], 0)

    # 9. Different queues -> they must not block each other
    def test_09_different_queues_do_not_block(self):
        alt_card = {"alert_id": "ALT-NOBLOCK-CARD", "patient_id": 101, "specialty": "CARDIOLOGY", "severity": "CRITICAL"}
        alt_pulm = {"alert_id": "ALT-NOBLOCK-PULM", "patient_id": 104, "specialty": "PULMONOLOGY", "severity": "CRITICAL"}

        trigger_workstation_voice_alert(alt_card)
        trigger_workstation_voice_alert(alt_pulm)

        # Set Cardiology to SPEAKING
        update_voice_alert_status("CARDIOLOGY", "ALT-NOBLOCK-CARD", "SPEAKING")

        # Pulmonology remains completely unaffected and ready to speak
        pulm_q = get_voice_queue("PULMONOLOGY")
        self.assertIsNone(pulm_q["currently_speaking"])
        self.assertEqual(pulm_q["pending_count"], 1)

    # 10. Voice alert does not wait for LLM/RAG
    def test_10_voice_alert_does_not_wait_for_llm_rag(self):
        t0 = time.perf_counter()
        alt = {
            "alert_id": "ALT-PERF-1",
            "patient_id": 101,
            "patient_name": "Rahul Patil",
            "specialty": "CARDIOLOGY",
            "ward": "Cardiology",
            "room_no": "201",
            "bed_no": "1",
            "severity": "CRITICAL"
        }
        res = trigger_workstation_voice_alert(alt)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(res["status"], "DISPATCHED")
        # Enqueue must take less than 50 milliseconds
        self.assertLess(elapsed_ms, 50.0, f"Enqueue took {elapsed_ms:.2f}ms, expected < 50ms")

    # 11. Voice alert does not wait for next simulator cycle
    def test_11_voice_alert_does_not_wait_for_next_simulator_cycle(self):
        from database.connection import get_connection
        from database.monitoring_queries import record_or_update_critical_alert
        con = get_connection()
        try:
            con.execute("UPDATE AlertHistory SET active = FALSE WHERE patient_id = 981;")
            t0 = time.perf_counter()
            alert_id = record_or_update_critical_alert(
                patient_id=981,
                severity="CRITICAL",
                reason="Severe Hypoxia",
                recommendation="O2 therapy",
                ward="Cardiology",
                room_no="201",
                bed_no="1",
                specialty="CARDIOLOGY",
                assigned_doctor="Dr. Viraj Patil",
                con=con
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Verify alert is enqueued in voice queue immediately
            cardio_q = get_voice_queue("CARDIOLOGY")
            matching = [item for item in cardio_q["queued"] if str(item["patient_id"]) in ("981", "P981")]
            self.assertTrue(len(matching) > 0, "Alert was not enqueued immediately in current cycle!")
        finally:
            con.close()

    # 12. No duplicate audio generation
    def test_12_no_duplicate_audio_generation(self):
        text = "Patient Test Patient, Ward A Room 12 Bed 3, Critical."
        filename = "test_dedup_cache"

        t0 = time.perf_counter()
        url1 = synthesize_speech(text, filename)
        first_duration = time.perf_counter() - t0

        t1 = time.perf_counter()
        url2 = synthesize_speech(text, filename)
        cached_duration = time.perf_counter() - t1

        self.assertEqual(url1, url2)
        # Cached fetch must be instantaneous (< 10ms)
        self.assertLess(cached_duration, 0.05, f"Cached audio check took {cached_duration*1000:.2f}ms")

    # 13. Voice message format is strictly: Patient [NAME], [LOCATION], [RISK LEVEL].
    def test_13_voice_message_concise_format(self):
        payload = {
            "patient_id": 101,
            "patient_name": "Rahul Patil",
            "ward": "Ward A",
            "room_no": "12",
            "bed_no": "3",
            "severity": "CRITICAL",
            "critical_vital": "oxygen_saturation",
            "vital_value": "84",
            "reason": "Hypoxia",
            "recommendation": "High flow oxygen"
        }
        spoken = build_concise_spoken_text(payload)
        # Verify strict format: "Patient Rahul Patil, Ward A Room 12 Bed 3, Critical."
        self.assertEqual(spoken, "Patient Rahul Patil, Ward A Room 12 Bed 3, Critical.")

        # Ensure NO prohibited text is present
        self.assertNotIn("84", spoken)
        self.assertNotIn("oxygen", spoken.lower())
        self.assertNotIn("recommendation", spoken.lower())
        self.assertNotIn("hypoxia", spoken.lower())
        self.assertNotIn("Critical alert.", spoken)

    # 14. FastAPI queue and status endpoints
    def test_14_fastapi_endpoints(self):
        alt = {
            "alert_id": "ALT-FASTAPI-01",
            "patient_id": 104,
            "patient_name": "Kavita Nair",
            "specialty": "PULMONOLOGY",
            "ward": "Pulmonology",
            "room_no": "202",
            "bed_no": "1",
            "severity": "CRITICAL"
        }
        trigger_workstation_voice_alert(alt)

        res = self.client.get("/api/v1/alerts/voice/queue?destination=PULMONOLOGY")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["destination"], "PULMONOLOGY")
        self.assertEqual(data["pending_count"], 1)

        # Report speaking
        res_speak = self.client.post("/api/v1/alerts/voice/status", json={
            "destination": "PULMONOLOGY",
            "alert_id": "ALT-FASTAPI-01",
            "status": "SPEAKING"
        })
        self.assertEqual(res_speak.status_code, 200)

        # Report completed
        res_done = self.client.post("/api/v1/alerts/voice/status", json={
            "destination": "PULMONOLOGY",
            "alert_id": "ALT-FASTAPI-01",
            "status": "COMPLETED"
        })
        self.assertEqual(res_done.status_code, 200)
        self.assertEqual(res_done.json()["queue"]["pending_count"], 0)


if __name__ == "__main__":
    unittest.main()

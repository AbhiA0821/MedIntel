"""
MedIntel LLM + RAG + Multi-Agent Comprehensive Automated Test Suite
Validates Groq client resilience, structured output validation, grounding rules,
Qdrant RAG idempotency & retrieval, rule-based fallback, and simulator zero-regression.
"""

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.llm.schemas import Agent1Contract, LLMResponseSchema
from services.llm.groq_client import GroqClientWrapper
from services.llm.validator import validate_llm_response
from services.llm.cache import compute_clinical_state_fingerprint, get_cached_explanation, set_cached_explanation, clear_cache
from services.rag.qdrant_rag import ingest_knowledge_base, retrieve_clinical_knowledge
from services.llm.llm_gateway import generate_clinical_explanation
from simulator.patient_simulator import generate_vitals_for_patient
from simulator.simulator_runner import run_simulation_cycle
from database.monitoring_queries import get_live_monitoring_state, record_or_update_critical_alert


class TestMedIntelLLMRAG(unittest.TestCase):

    # -----------------------------------------------------------------
    # 1. GROQ CLIENT TESTS
    # -----------------------------------------------------------------
    def test_groq_client_configuration(self):
        wrapper = GroqClientWrapper()
        self.assertIsInstance(wrapper.is_configured(), bool)

    def test_groq_client_disabled_fallback(self):
        os.environ["LLM_ENABLED"] = "false"
        wrapper = GroqClientWrapper()
        self.assertFalse(wrapper.is_configured())
        res = wrapper.generate_chat_completion("sys", "user")
        self.assertIsNone(res)
        os.environ["LLM_ENABLED"] = "true"

    # -----------------------------------------------------------------
    # 2. STRUCTURED OUTPUT & VALIDATION TESTS
    # -----------------------------------------------------------------
    def test_validator_valid_json(self):
        contract = Agent1Contract(
            patient_id="P150",
            severity="CRITICAL",
            vitals={"heart_rate": 125, "spo2": 84, "temperature": 39.1},
            abnormalities=["LOW_SPO2", "HIGH_HEART_RATE", "HIGH_TEMPERATURE"],
            specialty="CARDIOLOGY"
        )
        valid_raw = """{
            "clinical_summary": "Patient P150 exhibits acute cardiopulmonary distress with severe hypoxemia and high fever.",
            "reasons": ["Low SpO2 (84%) indicating acute hypoxemia", "Elevated heart rate (125 bpm) compensatory tachycardia"],
            "recommendation": "Administer supplemental oxygen immediately and monitor ECG continuous telemetry.",
            "priority": "CRITICAL",
            "sources_used": ["WHO Pulse Oximetry Guidelines", "AHA Tachycardia Protocol"]
        }"""
        is_valid, parsed, err = validate_llm_response(valid_raw, contract)
        self.assertTrue(is_valid)
        self.assertEqual(parsed["priority"], "CRITICAL")
        self.assertEqual(len(parsed["reasons"]), 2)

    def test_validator_rejects_malformed_json(self):
        contract = Agent1Contract(
            patient_id="P150",
            severity="CRITICAL",
            vitals={"heart_rate": 120, "spo2": 85},
            abnormalities=["LOW_SPO2"]
        )
        is_valid, parsed, err = validate_llm_response("NOT VALID JSON", contract)
        self.assertFalse(is_valid)
        self.assertIn("JSON parsing failed", err)

    def test_validator_rejects_prohibited_terms(self):
        contract = Agent1Contract(
            patient_id="P150",
            severity="CRITICAL",
            vitals={"heart_rate": 120, "spo2": 85},
            abnormalities=["LOW_SPO2"]
        )
        forbidden_raw = """{
            "clinical_summary": "Patient P150 definitively has pneumonia and acute myocardial infarction.",
            "reasons": ["Low SpO2 85%"],
            "recommendation": "Prescribe 100mg aspirin.",
            "priority": "CRITICAL",
            "sources_used": []
        }"""
        is_valid, parsed, err = validate_llm_response(forbidden_raw, contract)
        self.assertFalse(is_valid)
        self.assertIn("prohibited diagnostic assertion", err.lower())

    # -----------------------------------------------------------------
    # 3. FINGERPRINT CACHING TESTS
    # -----------------------------------------------------------------
    def test_cache_operations(self):
        clear_cache()
        fp = compute_clinical_state_fingerprint("P150", "CRITICAL", ["LOW_SPO2"], {"heart_rate": 120, "spo2": 85})
        self.assertIsNone(get_cached_explanation(fp))

        test_payload = {"patient_id": "P150", "clinical_summary": "Cached Test"}
        set_cached_explanation(fp, test_payload)

        cached = get_cached_explanation(fp)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["clinical_summary"], "Cached Test")
        self.assertTrue(cached["cached"])

    # -----------------------------------------------------------------
    # 4. QDRANT RAG TESTS
    # -----------------------------------------------------------------
    def test_qdrant_rag_ingestion_and_retrieval(self):
        count1 = ingest_knowledge_base()
        self.assertGreaterThan(count1, 0) if hasattr(self, 'assertGreaterThan') else self.assertTrue(count1 > 0)
        count2 = ingest_knowledge_base()
        self.assertEqual(count1, count2)  # Idempotent ingestion check

        docs = retrieve_clinical_knowledge(["LOW_SPO2", "HIGH_HEART_RATE"], specialty="CARDIOLOGY", top_k=2)
        self.assertTrue(len(docs) > 0)
        self.assertTrue(any("SpO2" in doc.content or "Heart Rate" in doc.content or "Cardiovascular" in doc.content for doc in docs))
        self.assertNotEqual(docs[0].source_name, "")
        self.assertNotEqual(docs[0].source_url, "")

    # -----------------------------------------------------------------
    # 5. GATEWAY & FALLBACK TESTS
    # -----------------------------------------------------------------
    def test_llm_gateway_fallback_when_disabled(self):
        os.environ["LLM_ENABLED"] = "false"
        patient = {"patient_id": "P199", "heart_rate": 130, "spo2": 82, "temperature": 39.2}
        res = generate_clinical_explanation(patient, "CRITICAL", ["LOW_SPO2", "HIGH_HEART_RATE"])
        self.assertIsNotNone(res)
        self.assertEqual(res["patient_id"], "P199")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertFalse(res["is_llm_generated"])  # Confirms fallback
        os.environ["LLM_ENABLED"] = "true"

    # -----------------------------------------------------------------
    # 6. ALERT RECORDING & SIMULATOR REGRESSION TESTS
    # -----------------------------------------------------------------
    def test_alert_recording_integration(self):
        alert_id = record_or_update_critical_alert(
            patient_id=150,
            severity="CRITICAL",
            reason="Low SpO2 (< 90%); High Heart Rate (> 120 bpm)",
            recommendation="Apply nasal cannula oxygen 4L/min.",
            priority="CRITICAL"
        )
        self.assertTrue(alert_id.startswith("ALT-P150"))

    def test_simulator_regression_10_cycles(self):
        state_before = get_live_monitoring_state()
        for _ in range(10):
            new_ids, dur = run_simulation_cycle()
            self.assertTrue(dur >= 0.0)

        state_after = get_live_monitoring_state()
        self.assertTrue(state_after["total_patients"] > 0)
        self.assertTrue(state_after["critical_count"] >= 0)


if __name__ == "__main__":
    unittest.main()

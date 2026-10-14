"""
MedIntel LLM Gateway Facade
Coordinates Agent 1 contract creation, fingerprint caching, Qdrant RAG context retrieval,
Groq LLM invocation, response validation, and fail-safe rule-based fallback.
"""

import logging
from typing import Dict, Any

from services.llm.schemas import Agent1Contract
from services.llm.groq_client import GroqClientWrapper
from services.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from services.llm.validator import validate_llm_response
from services.llm.cache import compute_clinical_state_fingerprint, get_cached_explanation, set_cached_explanation
from services.rag.qdrant_rag import retrieve_clinical_knowledge
from services.recommendation_engine import get_recommendations
from services.reason_detection import get_patient_reasons

logger = logging.getLogger(__name__)

# Singleton Groq client instance
_GROQ_CLIENT = GroqClientWrapper()


def _get_rule_based_fallback(
    patient: Dict[str, Any],
    severity: str,
    abnormalities: list
) -> Dict[str, Any]:
    """Generates rule-based fallback reasons and recommendations when LLM/RAG is disabled or unavailable."""
    pid = str(patient.get("patient_id", "P000"))
    reasons = get_patient_reasons(patient)
    rec = get_recommendations(patient)

    # Format clinical summary from reasons
    summary_text = f"Patient {pid} exhibits {severity} clinical deterioration: {'; '.join(reasons)}."

    return {
        "patient_id": pid,
        "severity": severity,
        "vitals": {
            "heart_rate": patient.get("heart_rate", 75),
            "spo2": patient.get("spo2", 98),
            "temperature": patient.get("temperature", 37.0),
            "systolic_bp": patient.get("systolic_bp", 120),
            "diastolic_bp": patient.get("diastolic_bp", 80),
            "respiratory_rate": patient.get("respiratory_rate", 16)
        },
        "abnormalities": abnormalities,
        "clinical_summary": summary_text,
        "reasons": reasons,
        "recommendation": rec,
        "priority": severity if severity in ("CRITICAL", "HIGH", "MODERATE", "LOW") else "HIGH",
        "sources_used": ["Deterministic Clinical Rule Engine (Fallback)"],
        "specialty": patient.get("specialty", "GENERAL MEDICINE"),
        "is_llm_generated": False,
        "cached": False
    }


def generate_clinical_explanation(
    patient: Dict[str, Any],
    verified_severity: str,
    abnormalities: list
) -> Dict[str, Any]:
    """
    Main entry point for generating clinical explanations.
    Combines Agent 1 facts -> Fingerprint Cache -> Qdrant RAG -> Groq LLM -> Validator -> Fallback.
    """
    pid = str(patient.get("patient_id", "P000"))
    specialty = patient.get("specialty", "GENERAL MEDICINE")

    vitals = {
        "heart_rate": patient.get("heart_rate", 75),
        "spo2": patient.get("spo2", 98),
        "temperature": patient.get("temperature", 37.0),
        "systolic_bp": patient.get("systolic_bp", 120),
        "diastolic_bp": patient.get("diastolic_bp", 80),
        "respiratory_rate": patient.get("respiratory_rate", 16)
    }

    # Step 1: Create immutable Agent 1 Contract
    contract = Agent1Contract(
        patient_id=pid,
        severity=verified_severity,
        vitals=vitals,
        abnormalities=abnormalities,
        specialty=specialty,
        ward=patient.get("ward", "ICU"),
        room_no=patient.get("room_no"),
        bed_no=patient.get("bed_no")
    )

    # Step 2: Check Fingerprint Cache
    fingerprint = compute_clinical_state_fingerprint(pid, verified_severity, abnormalities, vitals)
    cached_payload = get_cached_explanation(fingerprint)
    if cached_payload:
        logger.info(f"[LLM GATEWAY] Fingerprint cache HIT for patient {pid}.")
        return cached_payload

    # Step 3: Verify Groq Client configuration
    if not _GROQ_CLIENT.is_configured():
        logger.info(f"[LLM GATEWAY] Groq API key not set or LLM disabled. Using rule-based fallback.")
        return _get_rule_based_fallback(patient, verified_severity, abnormalities)

    # Step 4: Qdrant RAG Context Retrieval
    try:
        rag_docs = retrieve_clinical_knowledge(abnormalities, specialty=specialty, top_k=3)
    except Exception as e:
        logger.warning(f"[LLM GATEWAY] Qdrant RAG retrieval exception ({e}). Proceeding without RAG context.")
        rag_docs = []

    # Step 5: Groq LLM Inference
    try:
        user_prompt = build_user_prompt(pid, verified_severity, vitals, abnormalities, specialty, rag_docs)
        raw_output = _GROQ_CLIENT.generate_chat_completion(SYSTEM_PROMPT, user_prompt)
        if not raw_output:
            logger.warning(f"[LLM GATEWAY] Groq LLM returned null output. Falling back to rule engine.")
            return _get_rule_based_fallback(patient, verified_severity, abnormalities)
    except Exception as e:
        logger.error(f"[LLM GATEWAY] Exception invoking Groq LLM ({e}). Falling back to rule engine.")
        return _get_rule_based_fallback(patient, verified_severity, abnormalities)

    # Step 6: Validate LLM Response
    is_valid, parsed_dict, val_err = validate_llm_response(raw_output, contract)
    if not is_valid or not parsed_dict:
        logger.warning(f"[LLM GATEWAY] LLM Response failed validation: {val_err}. Falling back to rule engine.")
        return _get_rule_based_fallback(patient, verified_severity, abnormalities)

    # Format sources list
    sources = parsed_dict.get("sources_used", [])
    if not sources and rag_docs:
        sources = [f"{doc.source_name} - {doc.doc_title}" for doc in rag_docs]

    final_payload = {
        "patient_id": pid,
        "severity": verified_severity,
        "vitals": vitals,
        "abnormalities": abnormalities,
        "clinical_summary": parsed_dict["clinical_summary"],
        "reasons": parsed_dict["reasons"],
        "recommendation": parsed_dict["recommendation"],
        "priority": parsed_dict.get("priority", verified_severity),
        "sources_used": sources if sources else ["Clinical Knowledge Base"],
        "specialty": specialty,
        "is_llm_generated": True,
        "cached": False
    }

    # Step 7: Store in Cache
    set_cached_explanation(fingerprint, final_payload)
    logger.info(f"[LLM GATEWAY] Successfully generated and validated LLM explanation for patient {pid}.")
    return final_payload

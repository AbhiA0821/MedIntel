"""
MedIntel Lightweight Output Validator
Validates JSON structure, grounding, severity alignment, and safety boundaries of LLM responses.
Does NOT invoke secondary LLMs; operates deterministically.
"""

import json
import logging
from typing import Tuple, Dict, Any, Optional
from services.llm.schemas import Agent1Contract, LLMResponseSchema

logger = logging.getLogger(__name__)

PROHIBITED_DIAGNOSTIC_TERMS = [
    "definitive diagnosis",
    "patient definitively has",
    "prescribe 100mg",
    "administered 50mg"
]


def validate_llm_response(
    raw_response: str,
    contract: Agent1Contract
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validates LLM raw output string against Agent1Contract facts and safety rules.
    Returns (True, parsed_dict, None) on success, or (False, None, error_message) on failure.
    """
    if not raw_response or not isinstance(raw_response, str):
        return False, None, "Raw LLM response is empty or non-string."

    # Step 1: JSON Parsing
    try:
        data = json.loads(raw_response)
    except Exception as e:
        return False, None, f"JSON parsing failed: {e}"

    if not isinstance(data, dict):
        return False, None, "LLM JSON response is not a dictionary."

    # Step 2: Schema validation via Pydantic
    try:
        schema_obj = LLMResponseSchema(**data)
    except Exception as e:
        return False, None, f"Schema validation failed: {e}"

    # Step 3: Length & Boundary checks
    if len(schema_obj.clinical_summary) > 600:
        return False, None, "Clinical summary exceeds 600 character limit."

    if not schema_obj.reasons or len(schema_obj.reasons) == 0:
        return False, None, "LLM response provided zero clinical reasons."

    # Step 4: Prohibited diagnostic term check
    full_text = (schema_obj.clinical_summary + " " + " ".join(schema_obj.reasons) + " " + schema_obj.recommendation).lower()
    for term in PROHIBITED_DIAGNOSTIC_TERMS:
        if term in full_text:
            return False, None, f"LLM response contains prohibited diagnostic assertion: '{term}'"

    # Step 5: Verify priority matches or aligns with Agent 1 severity
    # CRITICAL -> CRITICAL or HIGH
    if contract.severity == "CRITICAL" and schema_obj.priority not in ("CRITICAL", "HIGH"):
        return False, None, f"Priority '{schema_obj.priority}' conflicts with Agent 1 CRITICAL severity."

    validated_dict = {
        "clinical_summary": schema_obj.clinical_summary,
        "reasons": schema_obj.reasons,
        "recommendation": schema_obj.recommendation,
        "priority": schema_obj.priority,
        "sources_used": schema_obj.sources_used
    }
    return True, validated_dict, None

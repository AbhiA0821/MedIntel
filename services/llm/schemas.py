"""
MedIntel LLM & RAG Data Schemas
Defines strict Pydantic models and contracts between Agent 1, RAG, Groq LLM, Validator, and Agent 3.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Agent1Contract(BaseModel):
    """Immutable contract passed from Agent 1 (Deterministic Safety Engine) to Agent 2."""
    patient_id: str
    severity: str = Field(..., description="Deterministic severity: CRITICAL, MODERATE, LOW")
    vitals: Dict[str, Any] = Field(..., description="Verified vital signs (heart_rate, spo2, temp, sys_bp, dia_bp, resp)")
    abnormalities: List[str] = Field(default_factory=list, description="Verified list of abnormality tokens")
    specialty: str = Field("GENERAL MEDICINE", description="Target medical specialty")
    ward: Optional[str] = "ICU"
    room_no: Optional[str] = None
    bed_no: Optional[str] = None


class RAGDocument(BaseModel):
    """Clinical knowledge passage retrieved from Qdrant vector database."""
    content: str
    source_name: str
    doc_title: str
    source_url: str
    publication_date: Optional[str] = None
    retrieval_date: Optional[str] = None
    topic: Optional[str] = None
    abnormality: Optional[str] = None
    specialty: Optional[str] = None


class LLMResponseSchema(BaseModel):
    """Structured JSON output produced by Groq LLM Agent 2."""
    clinical_summary: str = Field(..., description="Dashboard-friendly summary of verified clinical state")
    reasons: List[str] = Field(..., description="Bullet list of verified clinical reasons")
    recommendation: str = Field(..., description="Actionable clinical recommendation")
    priority: str = Field("HIGH", description="Priority level: CRITICAL, HIGH, MODERATE, LOW")
    sources_used: List[str] = Field(default_factory=list, description="List of knowledge base sources referenced")


class ValidatedAlertPayload(BaseModel):
    """Validated final payload ready for Agent 3 alert routing and DuckDB persistence."""
    patient_id: str
    severity: str
    vitals: Dict[str, Any]
    abnormalities: List[str]
    clinical_summary: str
    reasons: List[str]
    recommendation: str
    priority: str
    sources_used: List[str]
    specialty: str
    is_llm_generated: bool = False
    cached: bool = False

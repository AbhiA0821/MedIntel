"""
MedIntel LLM & RAG Integration Module
Provides safe, grounded LLM explanations and Qdrant RAG retrieval with deterministic safety fallbacks.
"""

from services.llm.llm_gateway import generate_clinical_explanation

__all__ = ["generate_clinical_explanation"]

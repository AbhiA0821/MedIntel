"""
MedIntel Qdrant RAG Package
Provides idempotent ingestion and similarity retrieval of official clinical guidelines.
"""

from services.rag.qdrant_rag import retrieve_clinical_knowledge, ingest_knowledge_base

__all__ = ["retrieve_clinical_knowledge", "ingest_knowledge_base"]

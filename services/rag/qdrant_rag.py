"""
MedIntel Qdrant Vector RAG Engine
Provides idempotent ingestion of knowledge base Markdown documents and
similarity retrieval based on clinical abnormality tokens and specialty.
"""

import os
import re
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from services.llm.schemas import RAGDocument

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"

# Global Qdrant In-Memory client instance / Storage
_QDRANT_CLIENT = None
_QDRANT_COLLECTION = "medintel_clinical_knowledge"
_KNOWLEDGE_STORE: List[Dict[str, Any]] = []


def _parse_markdown_frontmatter(file_path: Path) -> Tuple[Dict[str, Any], str]:
    """Parses YAML frontmatter metadata and body text from a Markdown file."""
    content = file_path.read_text(encoding="utf-8")
    metadata = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].strip()
            for line in fm_text.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    metadata[key.strip()] = val.strip().strip('"').strip("'")
    return metadata, body


def _compute_chunk_embedding(text: str) -> List[float]:
    """
    Computes a normalized 128-dimensional dense vector representation based on term frequency
    to provide fast, deterministic, zero-dependency vector similarity search in Qdrant.
    """
    vec = [0.0] * 128
    words = re.findall(r'\w+', text.lower())
    for w in words:
        h = int(hashlib.md5(w.encode('utf-8')).hexdigest(), 16) % 128
        vec[h] += 1.0

    # Normalize vector to unit length
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def ingest_knowledge_base(kb_dir: Path = KNOWLEDGE_BASE_DIR) -> int:
    """
    Idempotently ingests all Markdown files from knowledge_base/ into Qdrant vector database.
    Returns the total number of chunks ingested.
    """
    global _KNOWLEDGE_STORE, _QDRANT_CLIENT
    _KNOWLEDGE_STORE.clear()

    if not kb_dir.exists():
        logger.warning(f"[QDRANT RAG] Knowledge base directory {kb_dir} does not exist.")
        return 0

    md_files = list(kb_dir.glob("*.md"))
    total_chunks = 0

    for file_path in md_files:
        meta, body = _parse_markdown_frontmatter(file_path)
        # Split body into sections by ## headings
        raw_sections = body.split("\n## ")
        for idx, sec in enumerate(raw_sections):
            sec_text = sec if idx == 0 else f"## {sec}"
            sec_text = sec_text.strip()
            if not sec_text:
                continue

            # Deterministic SHA-256 ID for idempotency
            chunk_hash = hashlib.sha256(f"{file_path.name}_{idx}_{sec_text}".encode('utf-8')).hexdigest()

            doc_entry = {
                "chunk_id": chunk_hash,
                "content": sec_text,
                "source_name": meta.get("source_name", "Official Guideline"),
                "doc_title": meta.get("doc_title", file_path.stem.replace("_", " ").title()),
                "source_url": meta.get("source_url", "https://www.who.int"),
                "publication_date": meta.get("publication_date", "2023-01-01"),
                "retrieval_date": meta.get("retrieval_date", "2026-08-24"),
                "topic": meta.get("topic", "Clinical Guideline"),
                "abnormality": meta.get("abnormality", "GENERAL"),
                "specialty": meta.get("specialty", "GENERAL MEDICINE"),
                "embedding": _compute_chunk_embedding(sec_text)
            }
            _KNOWLEDGE_STORE.append(doc_entry)
            total_chunks += 1

    # Try connecting to Qdrant if qdrant-client package is present
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance, PointStruct

        host = os.getenv("QDRANT_HOST", "localhost")
        _QDRANT_CLIENT = QdrantClient(":memory:")
        if _QDRANT_CLIENT.collection_exists(_QDRANT_COLLECTION):
            _QDRANT_CLIENT.delete_collection(_QDRANT_COLLECTION)

        _QDRANT_CLIENT.create_collection(
            collection_name=_QDRANT_COLLECTION,
            vectors_config=VectorParams(size=128, distance=Distance.COSINE)
        )

        points = []
        for i, item in enumerate(_KNOWLEDGE_STORE):
            points.append(PointStruct(
                id=i + 1,
                vector=item["embedding"],
                payload={
                    "content": item["content"],
                    "source_name": item["source_name"],
                    "doc_title": item["doc_title"],
                    "source_url": item["source_url"],
                    "topic": item["topic"],
                    "abnormality": item["abnormality"],
                    "specialty": item["specialty"]
                }
            ))

        _QDRANT_CLIENT.upsert(collection_name=_QDRANT_COLLECTION, points=points)
        logger.info(f"[QDRANT RAG] Ingested {total_chunks} chunks into Qdrant collection '{_QDRANT_COLLECTION}'.")
    except Exception as e:
        logger.info(f"[QDRANT RAG] Qdrant client fallback active ({e}). Using in-memory store ({total_chunks} chunks).")

    return total_chunks


def retrieve_clinical_knowledge(
    abnormalities: List[str],
    specialty: str = "GENERAL MEDICINE",
    top_k: int = 3
) -> List[RAGDocument]:
    """
    Retrieves top_k relevant RAG documents based on patient abnormalities and specialty.
    """
    if not _KNOWLEDGE_STORE:
        ingest_knowledge_base()

    query_tokens = [ab.lower().replace("_", " ") for ab in abnormalities]
    query_tokens.append(specialty.lower())
    query_text = " ".join(query_tokens)
    query_vec = _compute_chunk_embedding(query_text)

    # Search in Qdrant if client active
    if _QDRANT_CLIENT:
        try:
            results = []
            if hasattr(_QDRANT_CLIENT, 'query_points'):
                res_obj = _QDRANT_CLIENT.query_points(collection_name=_QDRANT_COLLECTION, query=query_vec, limit=top_k)
                results = res_obj.points if hasattr(res_obj, 'points') else res_obj
            elif hasattr(_QDRANT_CLIENT, 'search'):
                results = _QDRANT_CLIENT.search(collection_name=_QDRANT_COLLECTION, query_vector=query_vec, limit=top_k)

            docs = []
            for hit in results:
                payload = getattr(hit, 'payload', hit)
                if isinstance(payload, dict):
                    docs.append(RAGDocument(
                        content=payload["content"],
                        source_name=payload["source_name"],
                        doc_title=payload["doc_title"],
                        source_url=payload["source_url"],
                        topic=payload.get("topic"),
                        abnormality=payload.get("abnormality"),
                        specialty=payload.get("specialty")
                    ))
            if docs:
                return docs
        except Exception as e:
            logger.warning(f"[QDRANT RAG] Qdrant search exception: {e}")

    # Fallback to in-memory cosine similarity search
    scored_items = []
    for item in _KNOWLEDGE_STORE:
        emb = item["embedding"]
        score = sum(q * e for q, e in zip(query_vec, emb))

        # Boost score if chunk abnormality matches patient abnormalities
        ab_match = item["abnormality"] in abnormalities or item["abnormality"] == "GENERAL"
        sp_match = item["specialty"] == specialty or item["specialty"] == "GENERAL MEDICINE"
        if ab_match:
            score += 0.5
        if sp_match:
            score += 0.2

        scored_items.append((score, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    top_items = scored_items[:top_k]

    return [
        RAGDocument(
            content=item["content"],
            source_name=item["source_name"],
            doc_title=item["doc_title"],
            source_url=item["source_url"],
            topic=item["topic"],
            abnormality=item["abnormality"],
            specialty=item["specialty"]
        ) for _, item in top_items
    ]

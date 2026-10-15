"""
MedIntel Grounded Prompts for Groq LLM Agent 2
Ensures strict compliance with Agent 1 verified facts, retrieved RAG context, and safety rules.
"""

SYSTEM_PROMPT = """You are MedIntel Clinical AI Agent 2, a specialized medical explanation and recommendation engine.

STRICT CLINICAL BOUNDARIES & SAFETY RULES:
1. You MUST use ONLY the verified patient vital signs provided in the prompt.
2. You MUST use ONLY the retrieved clinical knowledge passages provided in the prompt.
3. You MUST NEVER invent, modify, or hallucinate patient vital values.
4. You MUST NEVER modify or challenge the deterministic severity assigned by Agent 1.
5. You MUST NEVER invent patient medical history, prior medications, laboratory results, or unstated symptoms.
6. You MUST NEVER claim a definitive medical diagnosis. Keep recommendations distinct from diagnosis.
7. You MUST output strictly valid JSON in the requested format.

OUTPUT JSON FORMAT:
{
  "clinical_summary": "<Concise 1-2 sentence dashboard summary explaining the patient's acute vital sign state>",
  "reasons": ["<Detailed reason 1>", "<Detailed reason 2>"],
  "recommendation": "<Actionable immediate nursing/clinical care recommendation>",
  "priority": "<CRITICAL, HIGH, MODERATE, or LOW>",
  "sources_used": ["<Source Name / Document Title referenced from context>"]
}
"""


def build_user_prompt(
    patient_id: str,
    severity: str,
    vitals: dict,
    abnormalities: list,
    specialty: str,
    rag_passages: list
) -> str:
    """Builds a grounded user prompt containing verified facts and retrieved RAG context."""

    rag_text_lines = []
    if rag_passages:
        for idx, doc in enumerate(rag_passages, 1):
            src = getattr(doc, 'source_name', 'Official Clinical Guideline')
            title = getattr(doc, 'doc_title', 'Clinical Reference')
            content = getattr(doc, 'content', str(doc))
            rag_text_lines.append(f"Passage {idx} [Source: {src} - {title}]:\n{content}\n")
        rag_context = "\n".join(rag_text_lines)
    else:
        rag_context = "No specific RAG passages retrieved. Rely strictly on verified vital sign abnormalities."

    vitals_formatted = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in vitals.items()])
    abnormalities_formatted = ", ".join(abnormalities) if abnormalities else "None"

    return f"""VERIFIED PATIENT FACTS (Agent 1 Source of Truth):
- Patient ID: {patient_id}
- Deterministic Severity (Agent 1): {severity}
- Target Specialty: {specialty}
- Verified Vital Signs: {vitals_formatted}
- Detected Abnormalities: {abnormalities_formatted}

RETRIEVED CLINICAL KNOWLEDGE (RAG Passages):
{rag_context}

INSTRUCTIONS:
Synthesize the verified patient facts and retrieved clinical knowledge to generate a concise, grounded JSON response matching the system JSON format. Ensure all reported reasons match the detected abnormalities."""

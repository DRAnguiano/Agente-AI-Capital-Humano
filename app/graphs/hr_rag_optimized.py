from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


RAG_TOP_K = _env_int("RAG_TOP_K", 3)
RAG_MAX_CONTEXT_CHARS = _env_int("RAG_MAX_CONTEXT_CHARS", 2200)
RAG_MAX_CHARS_PER_DOC = _env_int("RAG_MAX_CHARS_PER_DOC", 850)
RAG_INCLUDE_SOURCE_HEADERS = os.getenv("RAG_INCLUDE_SOURCE_HEADERS", "true").strip().lower() in {"1", "true", "yes", "on"}


def _topic_keywords(question: str) -> list[str]:
    q = (question or "").lower()
    groups = {
        "payment": [
            "pago", "pagan", "sueldo", "salario", "kilómetro", "kilometro",
            "km", "viaje", "tramo", "vuelta", "prestaciones", "beneficio",
            "beneficios", "bono", "fondo", "imss", "infonavit", "aguinaldo",
            "vacaciones", "ptu", "seguro",
        ],
        "requirements": [
            "documento", "documentos", "requisito", "requisitos", "licencia",
            "federal", "tipo b", "tipo e", "apto", "médico", "medico", "sct",
            "r-control", "recurso confiable", "ine", "curp", "rfc", "nss",
            "comprobante", "experiencia",
        ],
        "safety": [
            "antidoping", "doping", "toxicológica", "toxicologica", "droga",
            "drogas", "alcohol", "cero tolerancia", "0 tolerancia", "prueba",
            "pruebas", "sustancias",
        ],
        "routes": [
            "ruta", "rutas", "base", "patio", "foránea", "foranea", "local",
            "descanso", "dormir", "pernoctar", "monterrey", "laredo", "silao",
        ],
        "training": [
            "escuelita", "curso", "capacitación", "capacitacion", "quinta rueda",
            "experiencia", "entrenamiento",
        ],
    }

    active: list[str] = []
    for words in groups.values():
        if any(word in q for word in words):
            active.extend(words)

    if active:
        return active

    return [
        "pago", "requisito", "documento", "licencia", "apto", "ruta",
        "base", "antidoping", "prestaciones", "quinta rueda",
    ]


def _pack_relevant_context(
    docs: list[dict[str, Any]],
    question: str,
    *,
    max_context_chars: int = RAG_MAX_CONTEXT_CHARS,
    max_chars_per_doc: int = RAG_MAX_CHARS_PER_DOC,
) -> str:
    """Compact retrieved chunks before sending them to the expensive generator.

    This keeps Llama 3.3 70B grounded while reducing prompt bloat, latency and cost.
    It never invents facts: it only selects lines already present in retrieved docs.
    """
    active = _topic_keywords(question)
    packed_blocks: list[str] = []
    seen: set[str] = set()

    for doc in docs:
        source = str(doc.get("source") or doc.get("metadata", {}).get("source") or "fuente_interna")
        text = str(doc.get("text") or doc.get("content") or "")
        lines: list[str] = []
        current_doc_chars = 0

        for raw_line in text.splitlines():
            line = " ".join((raw_line or "").strip().split())
            if len(line) < 8:
                continue

            lower = line.lower()
            if not any(keyword in lower for keyword in active):
                continue
            if lower in seen:
                continue

            seen.add(lower)
            lines.append(line)
            current_doc_chars += len(line)
            if current_doc_chars >= max_chars_per_doc:
                break

        if lines:
            if RAG_INCLUDE_SOURCE_HEADERS:
                block = f"[{source}]\n" + "\n".join(f"- {line}" for line in lines)
            else:
                block = "\n".join(f"- {line}" for line in lines)
            packed_blocks.append(block)

        joined = "\n\n".join(packed_blocks)
        if len(joined) >= max_context_chars:
            break

    packed = "\n\n".join(packed_blocks).strip()

    if not packed:
        fallback_blocks: list[str] = []
        for doc in docs[:2]:
            source = str(doc.get("source") or doc.get("metadata", {}).get("source") or "fuente_interna")
            text = " ".join(str(doc.get("text") or doc.get("content") or "").split())[:max_chars_per_doc]
            if text:
                fallback_blocks.append(f"[{source}]\n{text}" if RAG_INCLUDE_SOURCE_HEADERS else text)
        packed = "\n\n".join(fallback_blocks).strip()

    return packed[:max_context_chars]


def _estimate_tokens(chars: int) -> int:
    # Conservative enough for cost tracking without pulling tokenizer dependencies.
    return max(1, round(chars / 4))


def install_optimized_rag_patch() -> None:
    """Patch RAG nodes with a compact context path.

    This is a compatibility bridge for Phase 1: it avoids rewriting the whole graph
    while letting us test smaller context windows with Llama 3.3 70B.
    """
    from app.graphs import hr_nodes_rag as rag
    from app.indexer import call_llm, retrieve_context_for_guardrail

    if getattr(rag, "_optimized_rag_patch_installed", False):
        return

    def retrieve_documents_node(state: dict[str, Any]) -> dict[str, Any]:
        question = state.get("question") or state.get("message") or ""
        docs = retrieve_context_for_guardrail(question, top_k=RAG_TOP_K)
        return {
            "retrieved_docs": docs,
            "sources": [rag._source_payload(item) for item in docs],
            "events": [
                {
                    "type": "rag_retrieval_config",
                    "top_k": RAG_TOP_K,
                    "retrieved_count": len(docs),
                }
            ],
        }

    def generate_answer_node(state: dict[str, Any]) -> dict[str, Any]:
        question = state.get("question") or state.get("message") or ""
        relevant_docs = state.get("relevant_docs", [])
        context_text = _pack_relevant_context(relevant_docs, question)
        mandatory_facts = rag._mandatory_context_facts(context_text, question)
        ambiguous_cachimba_guidance = rag._ambiguous_cachimba_prompt_guidance(state, context_text, relevant_docs)
        current_stage = state.get("current_stage") or "START"
        side_question = rag._is_profile_side_question(state)
        memory_followup = rag._is_memory_followup_question(state)

        side_question_instruction = ""
        if side_question:
            side_question_instruction = f"""
IMPORTANTE SOBRE FLUJO DE FORMULARIO:
- La conversación está en etapa pendiente: {current_stage}.
- Responde la pregunta lateral sin avanzar el formulario ni repetir agresivamente el campo pendiente.
- Cierra suavemente con: "{rag.SIDE_QUESTION_SOFT_CLOSE}"
""".strip()

        prompt = f"""
{rag.SYSTEM_PROMPT}

PUBLIC_VOICE_RULES:
- Responde como Mundo, asistente de Capital Humano, no como lector de documentos.
- No digas: "según la información", "en los documentos", "se menciona" ni frases similares.
- El contexto ya viene filtrado. No intentes mencionar todo.
- Responde solo lo que el candidato preguntó.
- Máximo 2 párrafos o 5 bullets. Si la pregunta es corta, respuesta corta.
- No repitas "Hola, soy Mundo" si la conversación ya inició.
- No cierres con preguntas genéricas.

=== CONTEXTO INTERNO CONFIRMADO FILTRADO ===
{context_text}

=== INSTRUCCIÓN ESPECIAL DE JERGA AMBIGUA, SI APLICA ===
{ambiguous_cachimba_guidance}

=== HECHOS OBLIGATORIOS DEL CONTEXTO ===
{mandatory_facts or "N/D"}

=== MENSAJE DEL CANDIDATO ===
{question}

=== ESTADO CONVERSACIONAL ===
current_stage: {current_stage}
side_question_during_profile: {side_question}
memory_followup_question: {memory_followup}

{side_question_instruction}

INSTRUCCIONES:
1. Responde únicamente con base en el contexto interno confirmado.
2. No inventes sueldo, prestaciones, rutas, descansos, pago por kilómetro, contratación ni condiciones.
3. Si HECHOS OBLIGATORIOS DEL CONTEXTO no es N/D, incluye esos hechos sin convertir la respuesta en folleto.
4. Para preguntas de pago, responde solo los montos directamente relacionados. Incluye prestaciones solo si el candidato las pidió.
5. Para requisitos, incluye solo requisitos/documentos recuperados del contexto.
6. Para antidoping/seguridad, incluye tolerancia cero y pruebas aplicables solo si aparecen en el contexto; no des consejos para evadir controles.
7. Si falta información específica, di que Capital Humano confirma el detalle final.
8. Responde natural, breve y en español.

RESPUESTA:
""".strip()

        events: list[dict[str, Any]] = [
            {
                "type": "rag_context_packed",
                "retrieved_docs": len(state.get("retrieved_docs") or []),
                "relevant_docs": len(relevant_docs),
                "context_chars": len(context_text),
                "prompt_chars": len(prompt),
                "estimated_input_tokens": _estimate_tokens(len(prompt)),
                "max_context_chars": RAG_MAX_CONTEXT_CHARS,
                "max_chars_per_doc": RAG_MAX_CHARS_PER_DOC,
            }
        ]

        try:
            answer = call_llm(prompt).strip()
            events.append(
                {
                    "type": "rag_generation_usage_estimate",
                    "answer_chars": len(answer),
                    "estimated_output_tokens": _estimate_tokens(len(answer)),
                }
            )
        except Exception as exc:
            answer = ""
            events.append({"type": "rag_generation_exception", "error": f"{type(exc).__name__}: {exc}"})

        answer = rag._append_side_question_close(answer, state)
        return {"draft_answer": answer, "events": events}

    rag.retrieve_documents_node = retrieve_documents_node
    rag.generate_answer_node = generate_answer_node
    rag._pack_relevant_context = _pack_relevant_context
    rag._optimized_rag_patch_installed = True

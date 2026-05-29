from __future__ import annotations

from pathlib import Path

PATH = Path("app/orchestrators/knowledge_orchestrator.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"No encontré bloque para reemplazar: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    helper = r'''

def _is_profile_memory_complaint(message: str) -> bool:
    text = normalize_text(message)
    return any(
        term in text
        for term in (
            "ya te dije",
            "ya le dije",
            "ya te lo dije",
            "ya le habia dicho",
            "ya le había dicho",
            "ya te habia respondido",
            "ya te había respondido",
            "esas preguntas ya",
            "ya respondi",
            "ya respondí",
        )
    )


def _is_simple_yes(message: str) -> bool:
    text = normalize_text(message).strip()
    return text in {"si", "sí", "sii", "claro", "afirmativo", "correcto", "asi es", "así es"}


def _has_profile_viable_facts(memory: dict[str, Any] | None) -> bool:
    facts = _active_facts_map(memory)
    return (
        "candidate.city" in facts
        and "license.category" in facts
        and (
            "medical.apto_status" in facts
            or "medical.apto_expires_in" in facts
            or "medical.apto_expires_at" in facts
        )
        and (
            "experience.fifth_wheel" in facts
            or "experience.years" in facts
        )
    )


def _looks_like_docs_later_or_driving(message: str) -> bool:
    text = normalize_text(message)
    return any(
        term in text
        for term in (
            "vengo manejando",
            "voy manejando",
            "ando manejando",
            "manejando",
            "en unas horas",
            "yo le aviso",
            "al rato mando",
            "al rato los mando",
            "al rato mando todo",
            "deme oportunidad",
            "dame oportunidad",
            "conseguirlos",
            "conseguir los documentos",
            "luego se los mando",
            "luego los mando",
        )
    )


def _looks_like_infonavit_question(message: str) -> bool:
    text = normalize_text(message)
    return "infonavit" in text


def _demo_guardrail_reply(message: str, memory: dict[str, Any] | None, contract: dict[str, Any]) -> str | None:
    """Últimas guardas de conversación pública para la demo.

    Objetivo: evitar que RAG/LLM vuelva a pedir listas completas cuando la memoria ya tiene datos.
    """
    facts = _active_facts_map(memory)
    text = normalize_text(message)

    if _looks_like_infonavit_question(message):
        return "Sí, se manejan prestaciones de ley; los detalles específicos como Infonavit los confirma Capital Humano durante el proceso. Para orientarte mejor, ¿en qué ciudad resides actualmente?"

    if _is_brief_positive_close(message):
        return "Perfecto, gracias. Dejamos el proceso abierto; cuando tenga oportunidad de compartir la documentación, Capital Humano la revisa y seguimos adelante."

    if _looks_like_docs_later_or_driving(message):
        return "Claro, sin problema. Primero maneje con seguridad; cuando esté detenido y tenga oportunidad, nos comparte la documentación para que Capital Humano la revise. Dejamos su proceso abierto."

    if _is_profile_memory_complaint(message):
        if _has_profile_viable_facts(memory):
            return "Tiene razón, disculpe. Ya tengo registrado ciudad, tipo de licencia, apto vigente y experiencia. ¿Le agradó la vacante para continuar con el envío de documentos a Capital Humano?"
        if "candidate.city" in facts or "license.category" in facts:
            return "Tiene razón, disculpe. Ya tengo algunos datos registrados; vamos por partes. ¿Su licencia federal y apto médico están vigentes?"
        return "Tiene razón, disculpe. Para no repetirle preguntas, vamos por partes: ¿su licencia federal y apto médico están vigentes?"

    if _is_simple_yes(message):
        if _has_profile_viable_facts(memory):
            return "Perfecto. Entonces ya queda como candidato potencial; cuando tenga oportunidad, comparta su documentación para que Capital Humano la revise y continúe su proceso."
        if "candidate.city" in facts and "license.category" in facts:
            return "Perfecto, gracias. Entonces solo confirmo lo más importante: ¿su licencia federal y apto médico están vigentes?"

    if _has_profile_viable_facts(memory):
        # Si el candidato acaba de completar perfil, ya no pidas ciudad/licencia otra vez.
        if any(term in text for term in ("vigente", "todo vigente", "toda mi informacion", "3 anos", "3 años", "full", "quinta")):
            return "Excelente, con eso ya queda un perfil inicial fuerte: ciudad registrada, licencia tipo E, documentación vigente y experiencia en full. ¿Le agradó la vacante para continuar con el envío de documentos a Capital Humano?"

    if "candidate.city" in facts and "license.category" in facts and not (
        "medical.apto_status" in facts or "medical.apto_expires_in" in facts
    ):
        if any(term in text for term in ("resido", "vivo", "licencia", "tipo")):
            return "Perfecto, gracias. Entonces ya tengo ciudad y tipo de licencia. Para avanzar, solo confirmo lo más importante: ¿su licencia y apto médico están vigentes?"

    if "san luis" in text:
        return "Perfecto, gracias. Ya registro San Luis Potosí. Para avanzar, ¿qué tipo de licencia federal tiene?"

    return None
'''

    if "def _demo_guardrail_reply(" not in text:
        marker = "def _answer_rag_message(message: str, contract: dict[str, Any]) -> dict[str, Any]:\n"
        text = replace_once(text, marker, helper + "\n\n" + marker, "demo guardrail helper marker")

    # Let /start behave like greeting, not profile question.
    if '"/start"' not in text:
        old = """def _looks_like_greeting(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False
    greeting_terms = (
        "hola", "ola", "holaa", "buen dia", "buenos dias", "buenas", "buenas tardes",
        "buenas noches", "que tal", "q tal", "k tal", "hey"
    )
    return any(term in text for term in greeting_terms) and len(text) <= 120
"""
        new = """def _looks_like_greeting(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False
    if text.strip() in {"/start", "start", "inicio"}:
        return True
    greeting_terms = (
        "hola", "ola", "holaa", "buen dia", "buenos dias", "buenas", "buenas tardes",
        "buenas noches", "que tal", "q tal", "k tal", "hey"
    )
    return any(term in text for term in greeting_terms) and len(text) <= 120
"""
        if old in text:
            text = text.replace(old, new, 1)

    # Insert guardrail before RAG and friendly generation branches.
    if "guardrail_reply = _demo_guardrail_reply" not in text:
        old = """    if contract.get("route") == "rag" or contract.get("requires_rag"):
        rag_result = _answer_rag_message(message, contract)
        reply = rag_result["reply"]
    elif _should_use_friendly_llm(message, contract):
"""
        new = """    guardrail_reply = _demo_guardrail_reply(message, lead_memory_before, contract)
    if guardrail_reply:
        reply = guardrail_reply
        if _is_simple_yes(message) and _has_profile_viable_facts(lead_memory_before):
            upsert_lead_fact(
                lead_key=lead_key,
                fact_group="candidate",
                fact_key="vacancy_accepted",
                fact_value="sí",
                confidence=0.8,
                source_message_id=source_message_id,
                source_text=message,
            )
            facts_written.append("candidate.vacancy_accepted")
        if _looks_like_docs_later_or_driving(message):
            upsert_lead_fact(
                lead_key=lead_key,
                fact_group="documents",
                fact_key="submission_status",
                fact_value="pending_candidate_will_send",
                confidence=0.85,
                source_message_id=source_message_id,
                source_text=message,
            )
            facts_written.append("documents.submission_status")
        rag_result = {
            "reply": reply,
            "rag_used": False,
            "rag_skipped_reason": "demo_guardrail_static_reply",
            "preferred_sources": [],
            "retrieved_sources": [],
            "items_count": 0,
            "llm_cost_estimate": None,
            "timings": {"retrieve_context_ms": 0.0, "generate_answer_ms": 0.0},
        }
    elif contract.get("route") == "rag" or contract.get("requires_rag"):
        rag_result = _answer_rag_message(message, contract)
        reply = rag_result["reply"]
    elif _should_use_friendly_llm(message, contract):
"""
        text = replace_once(text, old, new, "guardrail before rag")

    PATH.write_text(text, encoding="utf-8")
    print("OK: guardas finales de demo aplicadas.")


if __name__ == "__main__":
    main()

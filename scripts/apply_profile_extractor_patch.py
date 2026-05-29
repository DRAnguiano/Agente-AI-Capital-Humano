from __future__ import annotations

from pathlib import Path

PATH = Path("app/orchestrators/knowledge_orchestrator.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"No encontré bloque para reemplazar: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    if "from app.lead_memory.profile_extractor import" not in text:
        text = replace_once(
            text,
            "from app.knowledge.text_normalizer import normalize_text\n",
            "from app.knowledge.text_normalizer import normalize_text\n"
            "from app.lead_memory.profile_extractor import extract_profile_facts, missing_profile_fields\n",
            "profile extractor import",
        )

    helper = '''

def _active_facts_map(memory: dict[str, Any] | None) -> dict[str, Any]:
    if not memory:
        return {}
    lead = memory.get("lead") or {}
    active_facts = lead.get("active_facts")
    if isinstance(active_facts, dict):
        return active_facts
    facts = memory.get("facts") or []
    out: dict[str, Any] = {}
    for row in facts:
        if isinstance(row, dict):
            key = f"{row.get('fact_group')}.{row.get('fact_key')}"
            out[key] = row.get("fact_value")
    return out


def _has_fact(memory: dict[str, Any] | None, key: str) -> bool:
    return key in _active_facts_map(memory)


def _reply_for_profile_capture(message: str, memory: dict[str, Any] | None) -> str | None:
    facts = _active_facts_map(memory)
    missing = missing_profile_fields(facts)
    text = normalize_text(message)

    has_city = "candidate.city" in facts
    has_license_category = "license.category" in facts
    has_license_status = "license.status" in facts or "license.expires_in" in facts
    has_apto = "medical.apto_status" in facts or "medical.apto_expires_in" in facts
    has_experience = "experience.fifth_wheel" in facts or "experience.years" in facts
    documents_pending_send = facts.get("documents.submission_status") == "pending_candidate_will_send"

    if documents_pending_send or any(term in text for term in ("vengo manejando", "voy manejando", "ando manejando", "en unas horas", "yo le aviso")):
        return "Claro, sin problema. Primero maneje con seguridad; cuando esté detenido y tenga oportunidad, nos comparte la documentación para que Capital Humano la revise. Dejamos su proceso abierto."

    if has_city and has_license_category and not (has_license_status and has_apto):
        return "Perfecto, gracias. Entonces ya tengo ciudad y tipo de licencia. Para avanzar, solo confirmo lo más importante: ¿su licencia y apto médico están vigentes?"

    if has_city and has_license_category and has_apto and has_experience:
        return "Excelente, con eso ya queda un perfil inicial fuerte. ¿Le agradó la vacante para continuar con el envío de documentos a Capital Humano?"

    if "son muchas preguntas" in text or "muchas preguntas" in text:
        return "Tiene razón, vamos por partes. No necesito todo de golpe; primero confirmemos lo básico: ¿su licencia federal y apto médico están vigentes?"

    if missing:
        first = missing[0]
        if first == "ciudad":
            return "Gracias. Para ubicar la vacante correcta, ¿en qué ciudad reside actualmente?"
        if first == "tipo de licencia":
            return "Gracias. Para avanzar, ¿qué tipo de licencia federal tiene?"
        if first in {"vigencia de licencia", "apto médico"}:
            return "Perfecto. Para revisar viabilidad, ¿su licencia federal y apto médico están vigentes?"
        if first == "experiencia quinta rueda/full":
            return "Bien. ¿Tiene experiencia manejando quinta rueda o full?"
        if first == "cartas laborales":
            return "Casi listo. ¿Cuenta con cartas laborales de sus empleos anteriores?"

    return None


def _is_brief_positive_close(message: str) -> bool:
    text = normalize_text(message)
    return bool(
        re.search(r"\b(no\s+)?todo bien\b", text)
        and any(term in text for term in ("grac", "gracias", "grax", "ok", "sale"))
    )
'''
    if "def _active_facts_map(" not in text:
        marker = "def _answer_rag_message(message: str, contract: dict[str, Any]) -> dict[str, Any]:\n"
        text = replace_once(text, marker, helper + "\n\n" + marker, "profile helper marker")

    # Add brief close override before farewell/time checks.
    if "deterministic_brief_positive_close" not in text:
        old = """def _apply_deterministic_overrides(message: str, contract: dict[str, Any]) -> dict[str, Any]:
"""
        new = """def _apply_deterministic_overrides(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    if _is_brief_positive_close(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["brief_positive_close"],
                "matched_aliases": ["todo_bien_gracias"],
                "intent": "farewell",
                "route": "profile",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reply_template": {"id": "brief_positive_close", "text": "Perfecto, gracias. Dejamos el proceso abierto; cuando tenga oportunidad de compartir la documentación, Capital Humano la revisa y seguimos adelante."},
                "reason": "deterministic_brief_positive_close",
            }
        )
        return updated

"""
        text = replace_once(text, old, new, "brief positive close override")

    # Store extracted facts after source_message_id.
    if "profile_facts = extract_profile_facts" not in text:
        old = """    source_message_id = source_msg.get("id") if source_msg else None

    save_lead_message(
"""
        new = """    source_message_id = source_msg.get("id") if source_msg else None

    profile_facts = extract_profile_facts(message, intent=intent)
    for fact in profile_facts:
        upsert_lead_fact(
            lead_key=lead_key,
            fact_group=fact["fact_group"],
            fact_key=fact["fact_key"],
            fact_value=fact["fact_value"],
            confidence=float(fact.get("confidence") or 0.75),
            source_message_id=source_message_id,
            source_text=message,
        )
        facts_written.append(f"{fact['fact_group']}.{fact['fact_key']}")

    save_lead_message(
"""
        text = replace_once(text, old, new, "store extracted profile facts")

    # Replace profile/status summary before update_lead_summary to include missing fields.
    if "profile_missing_fields" not in text:
        old = """    update_lead_summary(
        lead_key=lead_key,
        funnel_stage=stage_to,
        next_best_action=_next_action_for_stage(stage_to, contract),
        memory_summary=_memory_summary_for_stage(stage_to, message, contract),
        facts_summary={"last_intent": intent, "last_route": route, "last_stage": stage_to},
        risk_level=str(contract.get("risk_level") or "low"),
        requires_human=bool(contract.get("requires_human")),
    )

    memory = get_lead_memory(lead_key=lead_key)
"""
        new = """    interim_memory = get_lead_memory(lead_key=lead_key)
    active_facts = _active_facts_map(interim_memory)
    profile_missing = missing_profile_fields(active_facts)

    effective_stage = stage_to
    if active_facts.get("documents.submission_status") == "pending_candidate_will_send":
        effective_stage = "potential_candidate_documents_pending"
    elif {"candidate.city", "license.category", "medical.apto_status", "experience.fifth_wheel"}.issubset(active_facts.keys()):
        effective_stage = "profiled_viable"
    elif profile_facts and stage_to in {"new", "interested", "vacancy_info_shared", "documents_pending", "safety_review"}:
        effective_stage = "profile_in_progress"

    facts_summary = {"last_intent": intent, "last_route": route, "last_stage": effective_stage}
    if profile_missing:
        facts_summary["profile_missing_fields"] = profile_missing

    update_lead_summary(
        lead_key=lead_key,
        funnel_stage=effective_stage,
        next_best_action=_next_action_for_stage(effective_stage, contract),
        memory_summary=_memory_summary_for_stage(effective_stage, message, contract),
        facts_summary=facts_summary,
        risk_level=str(contract.get("risk_level") or "low"),
        requires_human=bool(contract.get("requires_human")),
    )

    memory = get_lead_memory(lead_key=lead_key)
"""
        text = replace_once(text, old, new, "profile summary update")

    # Add new stages in stage/action/summary funcs.
    text = text.replace('    "human_review": "Revisión humana",\n', '    "human_review": "Revisión humana",\n    "profile_in_progress": "Perfilamiento en progreso",\n    "profiled_viable": "Perfil viable inicial",\n    "potential_candidate_documents_pending": "Candidato potencial / documentación por enviar",\n    "potential_candidate_documents_sent": "Candidato potencial / documentos por validar",\n')

    if 'if stage == "potential_candidate_documents_pending":' not in text:
        text = text.replace(
            '    if stage == "documents_received":\n        return "Capital Humano debe validar documentos recibidos."\n',
            '    if stage == "documents_received":\n        return "Capital Humano debe validar documentos recibidos."\n'
            '    if stage == "profile_in_progress":\n        return "Continuar perfilamiento con una sola pregunta útil por turno."\n'
            '    if stage == "profiled_viable":\n        return "Confirmar si la vacante le agradó para avanzar a envío documental."\n'
            '    if stage == "potential_candidate_documents_pending":\n        return "Esperar documentación prometida y pasar a validación de Capital Humano cuando la comparta."\n'
            '    if stage == "potential_candidate_documents_sent":\n        return "Capital Humano debe validar documentación del candidato potencial."\n',
            1,
        )

    if 'if stage == "profile_in_progress":' not in text.split('def _memory_summary_for_stage', 1)[1]:
        text = text.replace(
            '    if intent == "requirements_documents":\n        return "El candidato preguntó por documentos o requisitos."\n',
            '    if stage == "profile_in_progress":\n        return "El candidato compartió datos iniciales para perfilamiento."\n'
            '    if stage == "profiled_viable":\n        return "El candidato parece viable por perfil inicial; falta confirmar aceptación y documentación."\n'
            '    if stage == "potential_candidate_documents_pending":\n        return "El candidato indica que puede compartir documentación después; queda pendiente de envío."\n'
            '    if intent == "requirements_documents":\n        return "El candidato preguntó por documentos o requisitos."\n',
            1,
        )

    # Use profile reply for friendly generation before LLM if useful.
    if "profile_reply = _reply_for_profile_capture" not in text:
        old = """    elif _should_use_friendly_llm(message, contract):
        if contract.get("route") == "fallback" and contract.get("intent") == "unknown":
            contract.update({"route": "friendly_smalltalk", "intent": "friendly_smalltalk", "reason": "safe_unknown_routed_to_friendly_llm"})
            lead_stage_to = _stage_for_contract(contract, message)
        friendly_result = _answer_friendly_message(message, contract, lead_memory_before)
        reply = friendly_result["reply"]
    else:
"""
        new = """    elif _should_use_friendly_llm(message, contract):
        if contract.get("route") == "fallback" and contract.get("intent") == "unknown":
            contract.update({"route": "friendly_smalltalk", "intent": "friendly_smalltalk", "reason": "safe_unknown_routed_to_friendly_llm"})
            lead_stage_to = _stage_for_contract(contract, message)
        profile_reply = _reply_for_profile_capture(message, lead_memory_before)
        if profile_reply:
            reply = profile_reply
            friendly_result = {
                "reply": reply,
                "llm_cost_estimate": None,
                "timings": {"friendly_total_ms": 0.0, "friendly_generate_ms": 0.0},
                "friendly_generation_used": False,
                "friendly_generation_skipped_reason": "profile_guard_static_reply",
            }
        else:
            friendly_result = _answer_friendly_message(message, contract, lead_memory_before)
            reply = friendly_result["reply"]
    else:
"""
        text = replace_once(text, old, new, "profile reply before friendly llm")

    PATH.write_text(text, encoding="utf-8")
    print("OK: profile extractor conectado al orquestador.")


if __name__ == "__main__":
    main()

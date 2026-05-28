from __future__ import annotations

from pathlib import Path
import re

APP_PATH = Path("app/app.py")


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    helper = r'''

def _human_route(value: str | None) -> str:
    mapping = {
        "rag": "Consulta documental",
        "profile": "Perfil / seguimiento",
        "friendly_smalltalk": "Conversación asistida",
        "candidate_dropoff_recovery": "Recuperación de candidato",
        "clarification": "Aclaración",
        "fallback": "Respuesta segura",
        "human_handoff": "Revisión humana",
        "policy_boundary": "Límite de política",
        "greeting": "Saludo",
    }
    return mapping.get((value or "").lower(), value or "N/D")


def _get_lead_memory_v2_for_note(result: dict, conversation_key: str | None = None) -> dict:
    """
    Lee la memoria RH v2 en español para notas internas.

    La vista v_rh_lead_memory_v2 ya expone:
    - funnel_stage_label
    - next_best_action
    - active_facts_text
    - active_facts_es
    """
    lead_key = result.get("lead_key")

    if not lead_key and conversation_key:
        lead_key = conversation_key

    if not lead_key:
        return {}

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        lead_key,
                        display_name,
                        phone,
                        lead_status,
                        funnel_stage,
                        funnel_stage_label,
                        next_best_action,
                        memory_summary,
                        active_facts_es,
                        active_facts_text,
                        risk_level,
                        requires_human
                    FROM v_rh_lead_memory_v2
                    WHERE lead_key = %(lead_key)s
                    LIMIT 1;
                    """,
                    {"lead_key": lead_key},
                )
                row = cur.fetchone()
        return dict(row) if row else {}
    except Exception as exc:
        print("[LEAD_MEMORY_V2_NOTE_ERROR]", str(exc)[:500], flush=True)
        return {}


def _lead_memory_text_for_note(lead_memory: dict) -> str:
    text = (lead_memory.get("active_facts_text") or "").strip()
    if text:
        return text

    facts = lead_memory.get("active_facts_es") or {}
    if isinstance(facts, dict) and facts:
        return "\n".join(f"• {key}: {value}" for key, value in facts.items())

    return "• Sin memoria operativa registrada todavía."
'''

    if "def _human_route(" not in text:
        marker = "def _human_city_group(value: str | None) -> str:\n"
        if marker not in text:
            raise RuntimeError("No encontré marcador def _human_city_group para insertar helpers.")
        text = text.replace(marker, helper + "\n\n" + marker, 1)

    # Amplía mapa de intenciones a español para el orquestador de conocimiento.
    additions = {
        '"payment_compensation": "Pago / compensación",': '"payment_compensation": "Pago / compensación",',
        '"requirements_documents": "Documentos / requisitos",': '"requirements_documents": "Documentos / requisitos",',
        '"drug_testing_urine": "Pruebas / política de seguridad",': '"drug_testing_urine": "Pruebas / política de seguridad",',
        '"bases_routes_rest": "Rutas / bases / descansos",': '"bases_routes_rest": "Rutas / bases / descansos",',
        '"driving_school": "Escuela de manejo / experiencia",': '"driving_school": "Escuela de manejo / experiencia",',
        '"candidate_dropoff_risk": "Riesgo de abandono",': '"candidate_dropoff_risk": "Riesgo de abandono",',
        '"document_submission_ack": "Documentos enviados por candidato",': '"document_submission_ack": "Documentos enviados por candidato",',
        '"on_route_safety": "Candidato en ruta / seguridad",': '"on_route_safety": "Candidato en ruta / seguridad",',
        '"friendly_smalltalk": "Conversación casual segura",': '"friendly_smalltalk": "Conversación casual segura",',
        '"local_time": "Hora local",': '"local_time": "Hora local",',
        '"farewell": "Despedida / seguimiento abierto",': '"farewell": "Despedida / seguimiento abierto",',
    }

    if '"payment_compensation": "Pago / compensación",' not in text:
        needle = '        "conditional_availability": "Disponibilidad condicionada",\n'
        if needle not in text:
            raise RuntimeError("No encontré marcador conditional_availability en _human_intent.")
        inject = "".join(f"        {line}\n" for line in additions.values())
        text = text.replace(needle, needle + inject, 1)

    new_note_function = r'''def _build_chatwoot_internal_note(
    result: dict,
    work_queue: dict,
    labels: list[str],
    username: str,
    content: str,
    channel_label: str | None = None,
) -> str:
    """
    Construye una nota interna breve, escaneable y humana para Capital Humano.
    Fase 2.10: prioriza Lead Memory v2 en español para RH.
    """
    conversation_key = result.get("conversation_key")
    if not conversation_key:
        # Compatibilidad con rutas de Chatwoot anteriores.
        channel_user_id = work_queue.get("channel_user_id")
        if channel_user_id:
            conversation_key = make_conversation_key("chatwoot", str(channel_user_id))

    lead_memory = result.get("lead_memory") or {}
    if not isinstance(lead_memory, dict) or not lead_memory.get("lead"):
        lead_memory = _get_lead_memory_v2_for_note(result, conversation_key=conversation_key)
    else:
        # Resultado directo del orquestador trae {lead, facts, messages, events}; usamos la vista si hay lead_key.
        lead_memory = _get_lead_memory_v2_for_note(result, conversation_key=conversation_key) or lead_memory

    current_stage_raw = result.get("current_stage") or work_queue.get("current_stage")
    intent_raw = result.get("intent") or work_queue.get("last_intent")
    risk_level_raw = result.get("risk_level") or lead_memory.get("risk_level") or work_queue.get("risk_level")
    route_raw = result.get("selected_route") or result.get("route")

    current_stage = _human_stage(current_stage_raw)
    intent = _human_intent(intent_raw)
    risk_level = _human_risk_level(risk_level_raw)
    route = _human_route(route_raw)

    title = _note_title_from_work_queue(work_queue, labels)
    queue_label = _short_queue_label(work_queue)

    lead_stage_label = lead_memory.get("funnel_stage_label") or current_stage
    lead_action = (
        lead_memory.get("next_best_action")
        or work_queue.get("recommended_action")
        or "Continuar seguimiento según etapa."
    )
    memory_summary = lead_memory.get("memory_summary") or "N/D"
    facts_text = _lead_memory_text_for_note(lead_memory)

    nombre_contacto = (
        lead_memory.get("display_name")
        or work_queue.get("nombre_completo")
        or username
        or "No disponible"
    )

    telefono_contacto = (
        lead_memory.get("phone")
        or work_queue.get("telefono")
        or "No disponible"
    )

    canal = channel_label or work_queue.get("channel") or "Chatwoot"

    ciudad = work_queue.get("ciudad") or "N/D"
    estado_region = work_queue.get("estado_region") or "N/D"
    pais_codigo = work_queue.get("pais_codigo") or "N/D"
    city_group = _human_city_group(work_queue.get("city_group"))

    location_requires_ch_validation = bool(work_queue.get("location_requires_ch_validation"))
    location_needs_travel_validation = bool(work_queue.get("location_needs_travel_validation"))

    labels_text = ", ".join(labels) if labels else "N/D"
    safe_content = (content or "").strip()[:500]

    return (
        f"{title}\n\n"
        f"Acción: {lead_action}\n"
        f"Último mensaje: “{safe_content}”\n\n"
        "👤 Contacto\n"
        f"Nombre: {nombre_contacto}\n"
        f"Teléfono: {telefono_contacto}\n"
        f"Canal: {canal}\n\n"
        "📋 Estado del lead\n"
        f"Etapa RH: {lead_stage_label}\n"
        f"Cola operativa: {queue_label}\n"
        f"Riesgo: {risk_level}\n"
        f"Resumen: {memory_summary}\n\n"
        "🧠 Memoria detectada\n"
        f"{facts_text}\n\n"
        "🧭 Decisión IA\n"
        f"Intención: {intent}\n"
        f"Ruta: {route}\n\n"
        "📍 Ubicación\n"
        f"Ciudad: {ciudad}, {estado_region} ({pais_codigo})\n"
        f"Clasificación: {city_group}\n"
        f"Requiere boleto/traslado: {_human_bool(location_needs_travel_validation)}\n"
        f"Validación CH por ubicación: {_human_required(location_requires_ch_validation)}\n\n"
        f"Labels: {labels_text}"
    )'''

    pattern = re.compile(
        r"def _build_chatwoot_internal_note\(.*?\n\s*\) -> str:\n.*?\n\s*\)\n\n\n@app\.post\(\"/chatwoot/webhook\"\)",
        flags=re.DOTALL,
    )
    replacement = new_note_function + '\n\n\n@app.post("/chatwoot/webhook")'
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("No pude reemplazar _build_chatwoot_internal_note. Revisa app/app.py manualmente.")

    APP_PATH.write_text(text, encoding="utf-8")
    print("OK: app/app.py actualizado con nota Chatwoot Lead Memory v2 en español.")


if __name__ == "__main__":
    main()

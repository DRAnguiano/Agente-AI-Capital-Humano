"""Shadow business route classifier — LLM propone, policy valida.

Shadow-only: NO escribe a DB, Chatwoot, labels ni profile_ready.
Observable: devuelve BusinessRouteOutput; el caller puede logear a CSV.
"""
from __future__ import annotations

import json
import os

from app.indexer import call_groq_json
from app.knowledge.business_route_policy import validate_business_output
from app.knowledge.business_route_schema import (
    AmbiguityFlag,
    BusinessRouteOutput,
    BusinessSignal,
    ExplicitFact,
    RequestedInfoItem,
)

SHADOW_MODEL = os.getenv("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")

_SYSTEM_PROMPT = """\
Eres el analizador de negocio shadow para un agente de reclutamiento de operadores de
camión (sencillo / full) que opera por WhatsApp. Analiza el mensaje y devuelve un JSON.
NO conversas. NO decides elegibilidad. NO marcas perfil listo.

DEVUELVE EXACTAMENTE este JSON (sin texto extra):
{
  "requested_info": [{"category": "<cat>", "evidence": "<texto literal>"}],
  "explicit_facts": [{"field": "<campo>", "value": "<valor>", "evidence": "<texto literal>", "confidence": 0.0-1.0}],
  "business_signals": [{"name": "<señal>", "evidence": "<texto literal>", "confidence": 0.0-1.0}],
  "ambiguity_flags": [{"name": "<flag>", "evidence": "<texto literal>"}],
  "requires_human": false,
  "profile_context_action": "<acción>",
  "policy_answer_keys": []
}

REGLA CRÍTICA:
"evidence" SIEMPRE debe ser texto que aparece LITERAL en el mensaje. Nunca lo inventes.
Si no hay evidencia literal, no emitas el fact ni la señal.

CAMPOS PARA explicit_facts:
- experience.vehicle_type: SOLO "full" o "sencillo" cuando es EXPLÍCITO.
  Correcto: "manejo full"→full | "para sencillo"→sencillo | "soy fullero"→full
  NUNCA desde: quinta rueda, 5ta rueda, tráiler, trailero, tractocamión, operador.
  NUNCA inventar desde contexto.
- candidate.city: ciudad explícita ("soy de Torreón"→"Torreón")
- license.type: B|E|A|C
- license.status: vigente|vencida|tramite
- medical.apto_status: vigente|vencido|tramite
- experience.years: número
- documents.proof: cartas|semanas_imss|ninguno

SEÑALES (business_signals.name):
- objetivo_full_sencillo: full/sencillo CONFIRMADO en el texto
- jerga_ambigua_falta_unidad: quinta rueda/5ta rueda/tráiler/trailero/tractocamión SIN full/sencillo
- considerar_escuelita_transmontes: torton/rabón/reparto local/interurbano
- cecati_sugerido: sin experiencia / quiero aprender a manejar
- considerar_operador_b1: B1/Estados Unidos/USA/EEUU
- reingreso_verificar: ya trabajé ahí / reingreso / quiero volver
- pago_condiciones: km/sueldo/prestaciones/IMSS/pago
- ubicacion_base_traslado: ubicación/base/ruta/circuito/donde se ubican
- documentos_requisitos: documentos/requisitos/qué necesito
- vacante_info_general: info general de vacante / saludo inicial
- complaint_with_candidate_interest: queja/frustración PERO candidato sigue interesado
- referral_candidate_contact: refiere a un tercero como candidato posible

CATEGORÍAS requested_info:
payment_per_km, salary, benefits, rest, route_availability, location_base, route_details,
documents_required, hiring_practice, vacancy_availability, vacancy_information,
visit_availability, travel_logistics, city_info, general_info

POLICY_ANSWER_KEYS (solo si aplica):
- no_pagares_en_blanco: si pregunta "firman pagarés en blanco" o similar

AMBIGUITY_FLAGS:
- vehicle_type_ambiguous: SOLO para términos vehiculares del catálogo:
  quinta rueda, 5ta rueda, tráiler, trailer, trailero, tractocamión, tractocamion.
  NUNCA para texto genérico que no sea terminología de vehículos.
- multimedia_no_ocr: hay "<Multimedia omitido>" o imagen/archivo en el mensaje
- multi_intent_unclear: múltiples preguntas sin intención dominante clara
- context_missing: la pregunta requiere contexto previo para resolverse (ej. "ya se fueron?")

PROFILE_CONTEXT_ACTION:
- continue_profiling: continuar con el siguiente campo faltante del perfil
- answer_or_clarify_current_question_first: el candidato hizo una pregunta o petición
  que debe responderse o aclararse ANTES de continuar el perfilamiento
- acknowledge_complaint_then_profile: queja → empatía, luego continuar
- escalate_to_human: B1 / reingreso / dato sensible
- await_document_update: candidato espera completar un trámite
- handle_referral: refiere a un tercero

REGLAS:
1. Múltiples señales en un mismo mensaje: PERMITIDO.
2. requires_human=true SOLO para: considerar_operador_b1, reingreso_verificar.
3. No inferir vehicle_type desde contexto; solo desde texto literal.
4. No inventar montos, rutas ni datos ausentes del mensaje.
5. Si hay "<Multimedia omitido>": emitir multimedia_no_ocr. Si el texto hace pregunta, clasificarla.
6. Responde SOLO el JSON, sin texto antes ni después.

EJEMPLOS:

Mensaje: "Me interesa para sencillo"
{"requested_info":[],"explicit_facts":[{"field":"experience.vehicle_type","value":"sencillo","evidence":"para sencillo","confidence":0.95}],"business_signals":[{"name":"objetivo_full_sencillo","evidence":"para sencillo","confidence":0.95}],"ambiguity_flags":[],"requires_human":false,"profile_context_action":"continue_profiling","policy_answer_keys":[]}

Mensaje: "Buenas tardes, información para operador 5ta rueda"
{"requested_info":[{"category":"vacancy_availability","evidence":"información para operador 5ta rueda"}],"explicit_facts":[],"business_signals":[{"name":"jerga_ambigua_falta_unidad","evidence":"5ta rueda","confidence":0.9}],"ambiguity_flags":[{"name":"vehicle_type_ambiguous","evidence":"5ta rueda"}],"requires_human":false,"profile_context_action":"continue_profiling","policy_answer_keys":[]}

Mensaje: "manejé torton varios años"
{"requested_info":[],"explicit_facts":[],"business_signals":[{"name":"considerar_escuelita_transmontes","evidence":"torton","confidence":0.9}],"ambiguity_flags":[],"requires_human":false,"profile_context_action":"continue_profiling","policy_answer_keys":[]}

Mensaje: "busco vacante B1 para Estados Unidos"
{"requested_info":[{"category":"vacancy_availability","evidence":"vacante B1"}],"explicit_facts":[],"business_signals":[{"name":"considerar_operador_b1","evidence":"B1 para Estados Unidos","confidence":0.95}],"ambiguity_flags":[],"requires_human":true,"profile_context_action":"escalate_to_human","policy_answer_keys":[]}

Mensaje: "sería como reingreso si se puede"
{"requested_info":[],"explicit_facts":[],"business_signals":[{"name":"reingreso_verificar","evidence":"reingreso","confidence":0.9}],"ambiguity_flags":[],"requires_human":true,"profile_context_action":"escalate_to_human","policy_answer_keys":[]}

Mensaje: "A como el km cargado y vacío? firman pagarés en blanco? Las rutas de Coahuila para donde son?"
{"requested_info":[{"category":"payment_per_km","evidence":"km cargado y vacío"},{"category":"hiring_practice","evidence":"firman pagarés en blanco"},{"category":"route_details","evidence":"rutas de Coahuila"}],"explicit_facts":[],"business_signals":[{"name":"pago_condiciones","evidence":"km cargado y vacío","confidence":0.95},{"name":"ubicacion_base_traslado","evidence":"rutas de Coahuila","confidence":0.9}],"ambiguity_flags":[],"requires_human":false,"profile_context_action":"continue_profiling","policy_answer_keys":["no_pagares_en_blanco"]}

Mensaje: "La verdad entré a laborar la semana pasada y aún no me dan viaje, estoy buscando en otro lado"
{"requested_info":[],"explicit_facts":[],"business_signals":[{"name":"complaint_with_candidate_interest","evidence":"buscando en otro lado","confidence":0.85}],"ambiguity_flags":[],"requires_human":false,"profile_context_action":"acknowledge_complaint_then_profile","policy_answer_keys":[]}

Mensaje: "<Multimedia omitido> Necesitas fotos por los dos lados?"
{"requested_info":[{"category":"documents_required","evidence":"fotos por los dos lados"}],"explicit_facts":[],"business_signals":[{"name":"documentos_requisitos","evidence":"fotos por los dos lados","confidence":0.85}],"ambiguity_flags":[{"name":"multimedia_no_ocr","evidence":"<Multimedia omitido>"}],"requires_human":false,"profile_context_action":"continue_profiling","policy_answer_keys":[]}

Mensaje: "Donde se ubican ustedes?"
{"requested_info":[{"category":"location_base","evidence":"Donde se ubican"}],"explicit_facts":[],"business_signals":[{"name":"ubicacion_base_traslado","evidence":"Donde se ubican","confidence":0.9}],"ambiguity_flags":[],"requires_human":false,"profile_context_action":"continue_profiling","policy_answer_keys":[]}

Mensaje: "Quisiera más información sobre la vacante de operador, gracias."
{"requested_info":[{"category":"vacancy_information","evidence":"más información sobre la vacante de operador"}],"explicit_facts":[],"business_signals":[{"name":"vacante_info_general","evidence":"más información sobre la vacante de operador","confidence":0.9}],"ambiguity_flags":[],"requires_human":false,"profile_context_action":"answer_or_clarify_current_question_first","policy_answer_keys":[]}

Mensaje: "¿Cómo me traslado a la base de Monterrey?\n<Multimedia omitido>"
{"requested_info":[{"category":"travel_logistics","evidence":"trasladarme a la base de Monterrey"}],"explicit_facts":[],"business_signals":[{"name":"ubicacion_base_traslado","evidence":"base de Monterrey","confidence":0.85}],"ambiguity_flags":[{"name":"multimedia_no_ocr","evidence":"<Multimedia omitido>"}],"requires_human":false,"profile_context_action":"answer_or_clarify_current_question_first","policy_answer_keys":[]}

Mensaje: "¿Siguen ahí? Quiero ir mañana."
{"requested_info":[{"category":"visit_availability","evidence":"ir mañana"}],"explicit_facts":[],"business_signals":[],"ambiguity_flags":[{"name":"context_missing","evidence":"siguen ahí"}],"requires_human":false,"profile_context_action":"answer_or_clarify_current_question_first","policy_answer_keys":[]}
"""


def _parse_llm_output(
    raw: dict,
    text: str,
    conv_classification: dict | None,
) -> BusinessRouteOutput:
    """Convert raw LLM JSON dict to BusinessRouteOutput (no validation yet)."""
    out = BusinessRouteOutput()

    # Pass through intents from existing classifier if provided
    if conv_classification:
        primary = conv_classification.get("primary_intent") or ""
        secondary = list(conv_classification.get("secondary_intents") or [])
        out.conversational_intents = [i for i in [primary, *secondary] if i]

    for item in raw.get("requested_info") or []:
        if isinstance(item, dict) and item.get("category"):
            out.requested_info.append(
                RequestedInfoItem(
                    category=str(item["category"]),
                    evidence=str(item.get("evidence") or ""),
                )
            )

    for item in raw.get("explicit_facts") or []:
        if not isinstance(item, dict):
            continue
        f_field = item.get("field")
        f_value = item.get("value")
        if f_field and f_value is not None:
            out.explicit_facts[str(f_field)] = ExplicitFact(
                field=str(f_field),
                value=str(f_value),
                evidence=str(item.get("evidence") or ""),
                confidence=float(item.get("confidence") or 0.9),
            )

    for item in raw.get("business_signals") or []:
        if isinstance(item, dict) and item.get("name"):
            out.business_signals.append(
                BusinessSignal(
                    name=str(item["name"]),
                    evidence=str(item.get("evidence") or ""),
                    confidence=float(item.get("confidence") or 0.9),
                )
            )

    for item in raw.get("ambiguity_flags") or []:
        if isinstance(item, dict) and item.get("name"):
            out.ambiguity_flags.append(
                AmbiguityFlag(
                    name=str(item["name"]),
                    evidence=str(item.get("evidence") or ""),
                )
            )

    out.requires_human = bool(raw.get("requires_human", False))
    out.profile_context_action = str(
        raw.get("profile_context_action") or "continue_profiling"
    )
    out.policy_answer_keys = [
        str(k) for k in (raw.get("policy_answer_keys") or []) if k
    ]

    return out


def classify_business_route_shadow(
    text: str,
    canonical_profile: dict | None = None,
    asked_field_keys: list[str] | None = None,
    missing_fields: list[str] | None = None,
    conversational_classification: dict | None = None,
) -> BusinessRouteOutput:
    """Shadow business route classifier.

    Shadow-only: no escribe a DB, Chatwoot, labels ni profile_ready.

    Args:
        text: mensaje crudo del candidato.
        canonical_profile: perfil canónico (read-only, solo para detección de conflictos).
        asked_field_keys: campos ya preguntados (contexto para el LLM).
        missing_fields: campos de perfil aún necesarios.
        conversational_classification: output de classify_message() si ya fue llamado.

    Returns:
        BusinessRouteOutput. Never raises; devuelve safe_empty() en error.
    """
    msg = (text or "").strip()
    if not msg:
        return BusinessRouteOutput.safe_empty("empty_message")

    # Build user content with optional context
    user_parts: list[str] = [f'Mensaje: "{msg}"']
    if missing_fields:
        user_parts.append(f"Campos faltantes en perfil: {', '.join(missing_fields)}")
    if canonical_profile:
        relevant = {
            k: v
            for k, v in canonical_profile.items()
            if v and not k.startswith("_")
        }
        if relevant:
            user_parts.append(
                f"Perfil actual (read-only): {json.dumps(relevant, ensure_ascii=False)[:300]}"
            )

    user_content = "\n".join(user_parts)

    raw_json = call_groq_json(user_content, _SYSTEM_PROMPT, temperature=0.0, model=SHADOW_MODEL)

    try:
        raw = json.loads(raw_json)
    except Exception as exc:
        return BusinessRouteOutput.safe_empty(
            f"json_parse_error: {type(exc).__name__}: {raw_json[:120]}"
        )

    if not isinstance(raw, dict) or raw.get("error"):
        err = raw.get("error") if isinstance(raw, dict) else "not_dict"
        return BusinessRouteOutput.safe_empty(f"llm_error: {err}")

    output = _parse_llm_output(raw, msg, conversational_classification)
    output = validate_business_output(output, msg, canonical_profile)
    return output

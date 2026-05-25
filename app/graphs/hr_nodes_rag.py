import re
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm, retrieve_context_for_guardrail
from app.orchestrator import orchestrate_message
from app.persona_config import SYSTEM_PROMPT


MIN_RELEVANCE_SCORE = 0.30
PROFILE_PENDING_STAGES = {"ASK_CITY", "ASK_LICENSE", "ASK_EXPERIENCE", "ASK_APTO", "ASK_AVAILABILITY"}
SIDE_QUESTION_SOFT_CLOSE = "Si le interesa, con gusto podemos continuar con su proceso."
GENERATION_ERROR_MARKERS = {
    "tuve un problema al generar la respuesta",
    "por favor intenta de nuevo",
    "error al generar",
    "internal_error",
    "exception",
}


def _source_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": item.get("source"),
        "score": round(item.get("score") or 0, 4),
    }
    if item.get("rerank_score") is not None:
        payload["rerank_score"] = round(item.get("rerank_score") or 0, 4)
    if item.get("chroma_score") is not None:
        payload["chroma_score"] = round(item.get("chroma_score") or 0, 4)
    if item.get("id"):
        payload["id"] = item.get("id")
    return payload


def _is_profile_side_question(state: HRState) -> bool:
    current_stage = state.get("current_stage") or "START"
    route = state.get("route")
    classifier = state.get("classifier") or {}
    intent = state.get("intent") or classifier.get("classifier_intent")

    if current_stage not in PROFILE_PENDING_STAGES:
        return False
    if route != "rag":
        return False
    return intent not in {"profile_answer", "candidate_interest"}


def _append_side_question_close(answer: str, state: HRState) -> str:
    if not _is_profile_side_question(state):
        return answer

    cleaned = (answer or "").strip()
    if not cleaned:
        return SIDE_QUESTION_SOFT_CLOSE
    if SIDE_QUESTION_SOFT_CLOSE.lower() in cleaned.lower():
        return cleaned
    return f"{cleaned}\n\n{SIDE_QUESTION_SOFT_CLOSE}"


def _append_missing_benefits_from_context(
    answer: str,
    context_text: str,
    question: str,
    relevant_docs: list[dict[str, Any]] | None = None,
) -> str:
    """
    If the candidate explicitly asks for prestaciones/beneficios and the
    retrieved payment document is present, make sure legal/superior benefits
    are mentioned briefly.

    This is a guardrail against omission, not a replacement for RAG:
    it only fires when the question asks for benefits and the payment document
    was part of the retrieved context/sources.
    """
    q = (question or "").lower()
    ctx = (context_text or "").lower()
    ans = (answer or "").strip()
    ans_lower = ans.lower()
    docs = relevant_docs or []

    asks_benefits = any(
        term in q
        for term in (
            "prestaciones",
            "beneficios",
            "imss",
            "infonavit",
            "aguinaldo",
            "vacaciones",
            "seguro",
            "ptu",
            "qué más dan",
            "que mas dan",
            "qué incluye",
            "que incluye",
        )
    )

    if not asks_benefits:
        return ans

    # If the answer already mentions core benefits, do nothing.
    if "imss" in ans_lower and "infonavit" in ans_lower:
        return ans

    sources = []
    for doc in docs:
        if isinstance(doc, dict):
            source = doc.get("source") or doc.get("metadata", {}).get("source")
            if source:
                sources.append(str(source).lower())

    payment_doc_retrieved = any("01_pago_prestaciones.md" in src for src in sources)

    context_has_benefits = any(
        term in ctx
        for term in (
            "imss",
            "infonavit",
            "aguinaldo",
            "vacaciones",
            "prima vacacional",
            "ptu",
            "seguro de vida",
        )
    )

    if not payment_doc_retrieved and not context_has_benefits:
        return ans

    benefits_sentence = (
        "En prestaciones, el esquema contempla IMSS e INFONAVIT, aguinaldo de 30 días, "
        "vacaciones, prima vacacional del 25%, PTU y seguro de vida."
    )

    if benefits_sentence.lower() in ans_lower:
        return ans

    return f"{ans}\n\n{benefits_sentence}"

def _rag_lead_update_ack(state: HRState) -> str:
    """
    If a RAG answer also came with profile updates in the same turn,
    acknowledge the captured data and any CH review flag.
    """
    lead = state.get("lead_ingestion") or {}
    updated_fields = set(lead.get("updated_fields") or [])
    extracted = lead.get("extracted") or {}

    if not lead.get("updated") and not updated_fields:
        return ""

    profile_fields = {
        "nombre_completo",
        "edad",
        "telefono",
        "ciudad",
        "ciudad_raw",
        "city_catalog_alias",
        "city_catalog_id",
        "city_group",
        "licencia_federal",
        "tipo_licencia",
        "apto_medico",
        "experiencia_quinta_rueda",
        "disponibilidad_viajar",
    }

    has_profile_update = bool(updated_fields & profile_fields)
    has_expiring_documents = bool(
        extracted.get("license_expiry_text")
        or extracted.get("license_needs_review")
        or extracted.get("medical_expiry_text")
        or {"requires_human", "risk_level"} & updated_fields
    )

    if not has_profile_update and not has_expiring_documents:
        return ""

    parts = []

    if has_profile_update:
        parts.append("Además, ya registré tus datos principales para el proceso.")

    if has_expiring_documents:
        parts.append(
            "También queda señalado que Capital Humano debe revisar la vigencia de tu licencia y apto médico antes de avanzar."
        )

    return "\n\n" + " ".join(parts)



def _is_ambiguous_cachimba_case(state: HRState) -> bool:
    """
    Detect the specific ambiguous slang case:
    cachimba/cachimbear may mean normal road stops, but can also imply a
    sensitive substance/alcohol context depending on the candidate's wording.
    """
    analysis = state.get("substance_disclosure_analysis") or {}
    raw = str(analysis.get("raw_mention") or state.get("message") or "").lower()
    message = str(state.get("message") or "").lower()
    rewritten = str((state.get("contextual_rewrite") or {}).get("rewritten") or "").lower()

    has_cachimba_term = any(
        term in f"{raw} {message} {rewritten}"
        for term in ("cachimba", "cachimbear", "cachimbr", "cachimb")
    )

    return bool(
        has_cachimba_term
        and analysis.get("detected") is True
        and str(analysis.get("status") or "").upper() == "AMBIGUOUS"
    )


def _context_supports_zero_tolerance(context_text: str, docs: list[dict[str, Any]] | None = None) -> bool:
    """
    Only force the zero-tolerance branch when retrieved internal context supports it.
    This keeps the bot grounded in Chroma instead of inventing policy.
    """
    ctx = (context_text or "").lower()

    if any(term in ctx for term in (
        "cero tolerancia",
        "0 tolerancia",
        "toxicológica",
        "toxicologica",
        "antidoping",
        "anti doping",
        "sustancias",
        "alcohol",
        "prueba de orina",
        "pruebas toxicológicas",
        "pruebas toxicologicas",
    )):
        return True

    for doc in docs or []:
        source = str(doc.get("source") or doc.get("metadata", {}).get("source") or "").lower()
        if any(name in source for name in (
            "03_seguridad_antidoping",
            "00_politicas_generales",
            "seguridad_antidoping",
            "politicas_generales",
        )):
            return True

    return False


def _answer_has_zero_tolerance_branch(answer: str) -> bool:
    text = (answer or "").lower()
    return any(term in text for term in (
        "cero tolerancia",
        "0 tolerancia",
        "toxicológica",
        "toxicologica",
        "antidoping",
        "sustancias",
        "alcohol",
    ))


def _apply_ambiguous_cachimba_dual_guard(
    answer: str,
    state: HRState,
    context_text: str,
    relevant_docs: list[dict[str, Any]] | None = None,
) -> str:
    """
    If the candidate uses ambiguous cachimba/cachimbear slang, make sure the
    final answer covers both safe meanings:
    - stops/paradores for food/rest, if that is what they meant;
    - zero-tolerance substance/alcohol policy and toxicology validation, if that
      is what they meant.

    This is a response guard. It does not accuse the candidate and it does not
    decide eligibility.
    """
    clean = (answer or "").strip()

    if not _is_ambiguous_cachimba_case(state):
        return clean

    if not _context_supports_zero_tolerance(context_text, relevant_docs):
        return clean

    if _answer_has_zero_tolerance_branch(clean):
        return clean

    addendum = (
        "También, si te refieres a consumo de sustancias o alcohol, "
        "la empresa maneja política de cero tolerancia en operación y puede realizar "
        "pruebas toxicológicas. En ese caso, la continuidad del proceso y la contratación "
        "dependen de cumplir esa política y de la validación de Capital Humano."
    )

    if not clean:
        return addendum

    return f"{clean}\n\n{addendum}".strip()


def _looks_like_generation_error(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    return any(marker in normalized for marker in GENERATION_ERROR_MARKERS)



def _ambiguous_cachimba_prompt_guidance(state: HRState, context_text: str, relevant_docs: list[dict[str, Any]] | None = None) -> str:
    if not _is_ambiguous_cachimba_case(state):
        return ""

    if not _context_supports_zero_tolerance(context_text, relevant_docs):
        return ""

    return """
AMBIGUOUS_CACHIMBA_DUAL_GUIDANCE:
El candidato usó jerga ambigua. No repitas la jerga en la respuesta pública.
Debes responder ambas posibilidades sin acusar:
1. Si se refiere a paradas breves para café, alimentos, baño o descanso, explica que solo deben hacerse en puntos autorizados por seguridad y operación. Aclara que la lista de puntos permitidos la valida Monitoreo o Control Operativo según la ruta.
2. Si se refiere a consumo de sustancias o alcohol, menciona política de cero tolerancia, posibles pruebas toxicológicas y que la continuidad/contratación depende de cumplir la política y de la validación de Capital Humano.
No afirmes que el candidato consume sustancias. No prometas elegibilidad ni rechazo. No cierres con pregunta de perfilamiento.
""".strip()


def _mandatory_context_facts(context_text: str, question: str) -> str:
    """
    Extracts the minimum facts that should not be omitted for the user's
    current question.

    Core idea:
    - For a narrow question, answer narrow but complete.
    - For "payment per km", include the payment essentials only.
    - For "benefits/bonuses/viatics/what else", include extended compensation.
    - Never hardcode company facts here; only promote lines already retrieved
      from Chroma context.
    """
    context = context_text or ""
    q = (question or "").lower()

    payment_terms = (
        "pago", "pagan", "kilómetro", "kilometro", "sueldo",
        "salario", "cuánto", "cuanto", "viaje", "compensación",
        "compensacion", "kilometraje",
    )

    extended_payment_terms = (
        "prestaciones", "beneficios", "bono", "bonos", "viáticos",
        "viaticos", "estadía", "estadias", "estadías", "maniobra",
        "maniobras", "qué más", "que mas", "qué incluye", "que incluye",
        "todo lo que dan", "paquete", "imss", "infonavit", "aguinaldo",
        "vacaciones", "ptu", "seguro",
    )

    requirements_terms = (
        "requisito", "documento", "licencia", "apto", "médico",
        "medico", "sct", "tipo b", "tipo e", "experiencia",
        "r-control", "recurso confiable",
    )

    safety_terms = (
        "doping", "antidoping", "droga", "toxicológico", "toxicologico",
        "fatiga", "alcohol", "seguridad", "paradas", "nocturna",
        "pastillas", "perico", "pericos", "aguantar",
    )

    routes_terms = (
        "ruta", "rutas", "base", "patio", "local", "foránea",
        "foranea", "dormir", "casa", "pernoctar",
    )

    jargon_terms = (
        "r-control", "recurso confiable", "boletinado", "quinta rueda",
        "full", "rabón", "rabon", "torton", "cachimba", "10-20",
    )

    is_payment = any(term in q for term in payment_terms)
    wants_extended_payment = any(term in q for term in extended_payment_terms)
    is_requirements = any(term in q for term in requirements_terms)
    is_safety = any(term in q for term in safety_terms)
    is_routes = any(term in q for term in routes_terms)
    is_jargon = any(term in q for term in jargon_terms)

    active_keywords = []

    if is_payment:
        # Core payment facts: enough to answer "a cómo dan el kilómetro"
        # without turning the answer into a full compensation brochure.
        active_keywords.extend((
            "sueldo base", "$12,000", "12000", "12,000", "mxn fijos",
            "pago por kilómetro", "pago por kilometro", "pago variable",
            "kilómetro recorrido", "kilometro recorrido", "viaje local",
            "foráneo", "foraneo", "quinta rueda promedio", "$6,000",
            "$9,000", "6,000", "9,000", "semanales netos",
            "full", "30% más", "30% mas",
        ))

        if wants_extended_payment:
            active_keywords.extend((
                "bono", "diésel", "diesel", "siniestralidad",
                "estadías", "estadias", "maniobras", "viáticos",
                "viaticos", "iave", "edenred", "efectivale",
                "imss", "infonavit", "aguinaldo", "vacaciones",
                "prima vacacional", "ptu", "seguro de vida",
            ))

    if is_requirements:
        active_keywords.extend((
            "licencia federal", "vigente", "tipo b", "tipo e",
            "apto médico", "apto medico", "sct", "r-control",
            "original", "copia", "ine", "curp", "rfc", "nss",
            "comprobante", "cartas", "recomendación", "recomendacion",
            "quinta rueda sencillo", "doble articulado", "mínimo",
            "minimo", "años comprobables",
        ))

    if is_safety:
        active_keywords.extend((
            "tolerancia cero", "doping", "toxicológica", "toxicologica",
            "5 paneles", "marihuana", "cocaína", "cocaina",
            "anfetaminas", "metanfetaminas", "opiáceos", "opiaceos",
            "aleatorias", "alcoholimetría", "alcoholimetria",
            "botón de pánico", "boton de panico", "paradas autorizadas",
            "conducción nocturna", "conduccion nocturna", "14 horas",
            "30 minutos", "5 horas", "8 horas",
        ))

    if is_routes:
        active_keywords.extend((
            "base central", "base norte", "base bajío", "base bajio",
            "tepotzotlán", "tepotzotlan", "nuevo laredo", "silao",
            "ruta local", "ruta foránea", "ruta foranea", "100 km",
            "dormir en casa", "pernoctar", "epp", "10 km/h",
            "enganche", "desenganche",
        ))

    if is_jargon:
        active_keywords.extend((
            "r-control", "recurso confiable", "boletinado",
            "aprobado", "10-4", "10-8", "10-20", "10-23",
            "10-28", "10-33", "10-74", "10-100", "10-200",
            "10-300", "quinta rueda", "full", "rabón", "rabon",
            "torton", "cachimba", "maruchero", "ordeñar", "patines",
            "perno rey", "kingpin", "tirado",
        ))

    if not active_keywords:
        return ""

    facts = []
    seen = set()

    for raw_line in context.splitlines():
        line = " ".join((raw_line or "").strip().split())
        if not line:
            continue

        cleaned = line.lstrip("- ").strip()
        lower = cleaned.lower()

        if not any(keyword in lower for keyword in active_keywords):
            continue

        if len(cleaned) < 8:
            continue

        if lower in seen:
            continue

        seen.add(lower)
        facts.append(cleaned)

        # Narrow payment questions should stay concise.
        if is_payment and not wants_extended_payment and len(facts) >= 5:
            break

        # Broader questions can include more facts.
        if len(facts) >= 12:
            break

    if not facts:
        return ""

    return "\n".join(f"- {fact}" for fact in facts)

def _is_memory_followup_question(state: HRState) -> bool:
    """
    Detects when the current question was made standalone using conversation
    memory. This lets the answer sound natural, e.g. "Como le comentaba...",
    without changing routing or retrieval behavior.
    """
    rewrite = state.get("contextual_rewrite") or {}
    memory = state.get("conversation_memory") or {}

    if not rewrite.get("should_use_rewrite"):
        return False

    original = str(rewrite.get("original") or state.get("message") or "").strip()
    rewritten = str(rewrite.get("rewritten") or state.get("question") or "").strip()

    if not original or not rewritten or original == rewritten:
        return False

    if memory.get("current_may_reference_previous") is True:
        return True

    # Short candidate follow-ups expanded into a fuller searchable question.
    return len(original.split()) <= 5 and len(rewritten.split()) > len(original.split())


def normalize_input_node(state: HRState) -> dict[str, Any]:
    message = (state.get("message") or "").strip()
    channel = (state.get("channel") or "chatwoot").strip().lower()
    channel_user_id = str(
        state.get("channel_user_id")
        or state.get("phone")
        or state.get("chatwoot_contact_id")
        or state.get("chatwoot_conversation_id")
        or "unknown"
    ).strip()
    return {
        "message": message,
        "question": message,
        "channel": channel,
        "channel_user_id": channel_user_id,
    }


def legacy_orchestrator_node(state: HRState) -> dict[str, Any]:
    result = orchestrate_message(
        channel=state["channel"],
        channel_user_id=state["channel_user_id"],
        username=state.get("username"),
        phone=state.get("phone"),
        message=state["message"],
        external_message_id=state.get("external_message_id"),
    )
    reply = (result.get("reply") or result.get("text") or "").strip()
    return {
        "legacy_result": result,
        "status": result.get("status", "ok"),
        "conversation_key": result.get("conversation_key"),
        "reply": reply,
        "text": reply,
        "current_stage": result.get("current_stage"),
        "next_stage": result.get("current_stage"),
        "requires_human": bool(result.get("requires_human", False)),
        "risk_level": result.get("risk_level", "low"),
        "intent": result.get("intent"),
        "sources": result.get("sources", []),
        "route": "legacy_orchestrator",
    }


def retrieve_documents_node(state: HRState) -> dict[str, Any]:
    question = state.get("question") or state.get("message") or ""
    docs = retrieve_context_for_guardrail(question, top_k=5)
    return {
        "retrieved_docs": docs,
        "sources": [_source_payload(item) for item in docs],
    }


def grade_documents_node(state: HRState) -> dict[str, Any]:
    docs = state.get("retrieved_docs", [])
    relevant_docs = [item for item in docs if (item.get("score") or 0) >= MIN_RELEVANCE_SCORE]
    return {
        "relevant_docs": relevant_docs,
        "docs_are_relevant": bool(relevant_docs),
        "sources": [_source_payload(item) for item in relevant_docs],
    }


def fallback_no_context_node(state: HRState) -> dict[str, Any]:
    reply = (
        "No tengo información confirmada en los documentos internos para responder eso con seguridad. "
        "Capital Humano debe validarlo directamente antes de darte una respuesta final."
    )
    reply = _append_side_question_close(reply, state)
    return {
        "reply": reply,
        "text": reply,
        "requires_human": True,
        "risk_level": state.get("risk_level", "medium"),
        "next_stage": state.get("current_stage") or "HUMAN_REVIEW_REQUIRED",
        "labels": ["requiere_humano", "sin_contexto_confirmado"],
        "events": [
            {
                "type": "rag_side_question_preserved_stage",
                "current_stage": state.get("current_stage"),
                "side_question": _is_profile_side_question(state),
            }
        ],
    }



def _is_public_ambiguous_cachimba_case(state: HRState) -> bool:
    substance = state.get("substance_disclosure_analysis") or {}
    contextual = state.get("contextual_rewrite") or {}
    question_rewrite = state.get("question_rewrite") or {}

    haystack = " ".join(
        str(x or "")
        for x in (
            state.get("message"),
            contextual.get("original"),
            contextual.get("rewritten"),
            substance.get("raw_mention"),
            question_rewrite.get("rewritten_question"),
        )
    ).lower()

    return bool(
        any(term in haystack for term in ("cachimba", "cachimbear", "cachimbr", "cachimb"))
        and substance.get("detected") is True
        and str(substance.get("status") or "").upper() == "AMBIGUOUS"
    )


def _public_language_guard_for_ambiguous_cachimba(reply: str, state: HRState) -> str:
    """
    Public wording guard.

    Internal retrieval can use cachimba/cachimbear as search terms, but the
    candidate-facing response should avoid repeating that slang. Use operational
    language instead: authorized stops, brief stops, coffee/food/restroom/rest,
    and Monitoring/Control Operativo validation.
    """
    clean = (reply or "").strip()
    if not clean or not _is_public_ambiguous_cachimba_case(state):
        return clean

    lower = clean.lower()

    # If the model produced a definition-style answer, replace it with the
    # operationally safe version. This is intentional: the candidate asked if
    # they can continue, not for a slang dictionary entry.
    if (
        "cachimba" in lower
        or "cachimbear" in lower
        or "puede referirse" in lower
        or "dos significados" in lower
        or "dos situaciones" in lower
    ):
        return (
            "Hola, soy Mundo, asistente de Capital Humano.\n\n"
            "Si te refieres a hacer paradas breves para tomar café, comer, ir al baño "
            "o descansar, eso debe hacerse únicamente en puntos autorizados por seguridad "
            "y operación. La lista de puntos permitidos la valida Monitoreo o Control Operativo "
            "según la ruta.\n\n"
            "Si te refieres a consumo de sustancias o alcohol, la empresa maneja política de "
            "cero tolerancia y puede realizar pruebas toxicológicas. La continuidad del proceso "
            "depende de cumplir esa política y de la validación de Capital Humano."
        )

    # Fallback cleanup if the answer is otherwise good but used the slang once.
    replacements = {
        "cachimbear": "hacer ese tipo de paradas",
        "Cachimbear": "Hacer ese tipo de paradas",
        "cachimbas": "puntos autorizados",
        "Cachimbas": "Puntos autorizados",
        "cachimba": "punto autorizado",
        "Cachimba": "Punto autorizado",
    }

    for old, new in replacements.items():
        clean = clean.replace(old, new)

    # Remove generic endings/questions that RAG answers should not append.
    clean = re.sub(
        r"\n*\s*¿Deseas continuar con información sobre la vacante.*?\?\s*$",
        "",
        clean,
        flags=re.IGNORECASE | re.DOTALL,
    )
    clean = re.sub(
        r"\n*\s*Si tienes.*?(duda|dudas).*?$",
        "",
        clean,
        flags=re.IGNORECASE | re.DOTALL,
    )
    clean = re.sub(
        r"\n*\s*Estoy aquí.*?$",
        "",
        clean,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return clean.strip()


def generate_answer_node(state: HRState) -> dict[str, Any]:
    question = state.get("question") or state.get("message") or ""
    relevant_docs = state.get("relevant_docs", [])
    context_text = "\n\n---\n\n".join(item.get("text", "") for item in relevant_docs)
    mandatory_facts = _mandatory_context_facts(context_text, question)
    ambiguous_cachimba_guidance = _ambiguous_cachimba_prompt_guidance(state, context_text, relevant_docs)
    current_stage = state.get("current_stage") or "START"
    side_question = _is_profile_side_question(state)
    memory_followup = _is_memory_followup_question(state)

    side_question_instruction = ""
    if side_question:
        side_question_instruction = f"""
IMPORTANTE SOBRE FLUJO DE FORMULARIO:
- La conversación está en etapa pendiente: {current_stage}.
- El candidato hizo una pregunta lateral, no respondió el campo pendiente.
- Responde su pregunta con naturalidad.
- No avances el formulario.
- No hagas la siguiente pregunta del formulario.
- No repitas agresivamente la pregunta pendiente.
- Cierra suavemente con: "{SIDE_QUESTION_SOFT_CLOSE}"
""".strip()

    prompt = f"""
{SYSTEM_PROMPT}

=== CONTEXTO INTERNO CONFIRMADO ===
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

{side_question_instruction}

=== SEGUIMIENTO CON MEMORIA ===
memory_followup_question: {memory_followup}

INSTRUCCIONES:
1. Responde únicamente con base en el contexto interno recuperado.
2. No inventes sueldo, prestaciones, rutas, descansos, pago por kilómetro, contratación ni condiciones.
3. Si HECHOS OBLIGATORIOS DEL CONTEXTO no es N/D, debes incluir esos hechos en la respuesta.
4. Responde exactamente lo que preguntó el candidato: completo, pero sin convertir una pregunta corta en folleto.
5. Para preguntas de pago por kilómetro o viaje, incluye los mínimos del contexto: sueldo base si aparece, pago variable por kilómetro/viaje, rango semanal de quinta rueda, diferencia de Full y confirmación final por Capital Humano.
6. No incluyas bonos, viáticos, estadías, maniobras o prestaciones completas salvo que el candidato pregunte por beneficios, bonos, viáticos, prestaciones o "qué más incluye".
7. Si el candidato pregunta por prestaciones o beneficios, incluye explícitamente las prestaciones legales/superiores presentes en el contexto: IMSS, INFONAVIT, aguinaldo, vacaciones, prima vacacional, PTU y seguro de vida.
8. No reemplaces montos concretos por frases genéricas como "varía según el viaje" si el contexto sí trae cifras.
9. Para preguntas de requisitos, si aparecen en el contexto, incluye licencia vigente, tipo B/E, apto médico SCT, R-Control, documentos y experiencia mínima.
10. Para preguntas de seguridad o antidoping, si aparecen en el contexto, incluye tolerancia cero y pruebas aplicables con tono neutral; no des consejos para evadir controles.
11. Si falta información específica, indica que Capital Humano puede confirmar el detalle final.
12. Responde breve, natural y en español.
13. No cierres con frases genéricas como "si tienes otra duda", "puedo ayudarte", "¿quieres continuar?" o similares.
14. Si es una pregunta lateral durante formulario, no empujes el proceso ni hagas preguntas del formulario.
15. Si memory_followup_question=true, responde como seguimiento natural de una pregunta ya contestada. Puedes iniciar con "Como le comentaba," o "Sí, como le comentaba," y repetir la información confirmada sin sonar molesto.

RESPUESTA:
"""

    events = []
    try:
        answer = call_llm(prompt).strip()
    except Exception as exc:
        answer = ""
        events.append({"type": "rag_generation_exception", "error": f"{type(exc).__name__}: {exc}"})

    answer = _append_side_question_close(answer, state)
    return {"draft_answer": answer, "events": events}


def hallucination_check_node(state: HRState) -> dict[str, Any]:
    draft = (state.get("draft_answer") or "").strip()
    relevant_docs = state.get("relevant_docs", [])

    if not draft or not relevant_docs:
        return {"hallucination_check": "FAIL"}
    if _looks_like_generation_error(draft):
        return {"hallucination_check": "FAIL"}
    return {"hallucination_check": "PASS"}


def answer_check_node(state: HRState) -> dict[str, Any]:
    draft = (state.get("draft_answer") or "").strip()

    if state.get("hallucination_check") != "PASS" or len(draft) < 10 or _looks_like_generation_error(draft):
        reply = (
            "No tengo información confirmada suficiente para responder eso con seguridad. "
            "Capital Humano debe validarlo directamente."
        )
        reply = _append_side_question_close(reply, state)
        return {
            "answer_check": "FAIL",
            "reply": reply,
            "text": reply,
            "requires_human": True,
            "next_stage": state.get("current_stage"),
            "labels": ["requiere_humano", "respuesta_no_validada"],
            "events": [
                {
                    "type": "rag_answer_rejected",
                    "reason": "generation_error_or_invalid_answer",
                    "draft_preview": draft[:120],
                }
            ],
        }

    question = state.get("question") or state.get("message") or ""
    relevant_docs = state.get("relevant_docs", [])
    context_text = "\n\n---\n\n".join(item.get("text", "") for item in relevant_docs)

    final_reply = _append_missing_benefits_from_context(
        draft,
        context_text,
        question,
        relevant_docs,
    )

    final_reply = _apply_ambiguous_cachimba_dual_guard(
        final_reply,
        state,
        context_text,
        relevant_docs,
    )
    final_reply = _public_language_guard_for_ambiguous_cachimba(final_reply, state)

    benefits_appended = final_reply != draft

    lead_ack = _rag_lead_update_ack(state)
    if lead_ack and lead_ack.strip() not in final_reply:
        final_reply = f"{final_reply}{lead_ack}"

    final_reply = _public_language_guard_for_ambiguous_cachimba(final_reply, state)

    return {
        "answer_check": "PASS",
        "reply": final_reply,
        "text": final_reply,
        "next_stage": state.get("current_stage") if _is_profile_side_question(state) else state.get("next_stage"),
        "events": [
            {
                "type": "rag_answered_side_question" if _is_profile_side_question(state) else "rag_answered",
                "current_stage": state.get("current_stage"),
                "stage_preserved": _is_profile_side_question(state),
                "memory_followup_question": _is_memory_followup_question(state),                "lead_ack_appended": bool(lead_ack),
                "benefits_appended": benefits_appended,
            }
        ],
    }



def _last_mile_clean_reply(reply: str, state: HRState) -> str:
    """
    Last-mile public reply cleanup.

    Removes:
    - generic closings;
    - premature profile questions from RAG answers;
    - weak lead acknowledgements caused by speculative extraction.

    Also adds zero-tolerance branch for ambiguous cachimba/cachimbear cases when
    internal sources support it.
    """
    clean = (reply or "").strip()
    if not clean:
        return clean

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
    kept = []

    for p in paragraphs:
        low = p.lower()

        generic_close = (
            "si tienes más dudas" in low
            or "si tienes mas dudas" in low
            or "estoy aquí" in low
            or "estoy aqui" in low
            or "puedo ayudarte" in low
            or "resolver cualquier duda" in low
        )

        profile_push = (
            ("si quieres aplicar" in low or "podemos continuar con el proceso" in low)
            and (
                "nombre completo" in low
                or "cuál es tu nombre" in low
                or "cual es tu nombre" in low
                or "me confirmas tu nombre" in low
            )
        )

        weak_ack = (
            "ya registré tus datos principales" in low
            or "ya registre tus datos principales" in low
            or "ya registré tus datos" in low
            or "ya registre tus datos" in low
        )

        if generic_close or profile_push or weak_ack:
            continue

        kept.append(p)

    clean = "\n\n".join(kept).strip()

    analysis = state.get("substance_disclosure_analysis") or {}
    raw = str(analysis.get("raw_mention") or "")
    msg = str(state.get("message") or "")
    rewrite = str((state.get("contextual_rewrite") or {}).get("rewritten") or "")
    haystack = f"{raw} {msg} {rewrite}".lower()

    ambiguous_cachimba = (
        analysis.get("detected") is True
        and str(analysis.get("status") or "").upper() == "AMBIGUOUS"
        and any(term in haystack for term in ("cachimba", "cachimbear", "cachimbr", "cachimb"))
    )

    sources = state.get("sources") or []
    docs = state.get("relevant_docs") or state.get("retrieved_docs") or []
    source_text = ""

    for item in list(sources) + list(docs):
        if isinstance(item, dict):
            source_text += " " + str(item.get("source") or item.get("id") or item.get("metadata", {}).get("source") or "")
            source_text += " " + str(item.get("text") or item.get("content") or "")

    source_text = source_text.lower()

    supports_zero_tolerance = any(term in source_text for term in (
        "03_seguridad_antidoping",
        "00_politicas_generales",
        "cero tolerancia",
        "0 tolerancia",
        "toxicológica",
        "toxicologica",
        "antidoping",
        "sustancias",
        "alcohol",
    ))

    already_mentions_zero_tolerance = any(term in clean.lower() for term in (
        "cero tolerancia",
        "0 tolerancia",
        "toxicológica",
        "toxicologica",
        "antidoping",
        "sustancias",
        "alcohol",
    ))

    if ambiguous_cachimba and supports_zero_tolerance and not already_mentions_zero_tolerance:
        addendum = (
            "Si con “cachimbear” te refieres a consumo de sustancias o alcohol, "
            "la empresa maneja política de cero tolerancia en operación y puede realizar "
            "pruebas toxicológicas. La continuidad del proceso y una posible contratación "
            "dependen de cumplir esa política y de la validación de Capital Humano."
        )
        clean = f"{clean}\n\n{addendum}".strip() if clean else addendum

    return clean.strip()


def save_output_node(state: HRState) -> dict[str, Any]:
    reply = (state.get("reply") or state.get("text") or "").strip()
    reply = _last_mile_clean_reply(reply, state)
    return {"reply": reply, "text": reply, "status": state.get("status", "ok")}

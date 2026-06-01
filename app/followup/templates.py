"""Plantillas de mensajes de seguimiento por etapa e intento."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Etiquetas en español para Chatwoot
# ---------------------------------------------------------------------------

TEMPERATURA_DISPLAY: dict[str, str] = {
    "caliente":  "🔥 Caliente",
    "tibio":     "😊 Tibio",
    "enfriando": "🌤 Enfriando",
    "frio":      "❄️ Frío",
    "perdido":   "💤 Perdido",
}

ETAPA_DISPLAY: dict[str, str] = {
    "new":                    "Nuevo lead",
    "interested":             "Interesado",
    "vacancy_info_shared":    "Info de vacante compartida",
    "profile_hint_collected": "Perfil en captura",
    "documents_pending":      "Documentos pendientes",
    "documents_received":     "Documentos recibidos",
    "apto_pending_update":    "Apto médico por actualizar",
    "safety_review":          "Revisión de seguridad",
    "followup_pending":       "Seguimiento pendiente",
    "human_review":           "Revisión humana",
    "profile_ready":          "Perfil listo",
    "lost":                   "Perdido",
    "closed":                 "Cerrado",
}

ESTADO_TAREA_DISPLAY: dict[str, str] = {
    "pendiente":  "⏳ Pendiente",
    "enviado":    "✅ Enviado",
    "omitido":    "⏭ Omitido",
    "cancelado":  "🚫 Cancelado",
}

# Campos faltantes de perfil → texto natural para el candidato
_CAMPO_DISPLAY: dict[str, str] = {
    "ciudad":                    "ciudad o estado de residencia",
    "tipo de licencia":          "tipo de licencia federal (A, B o E)",
    "vigencia de licencia":      "vigencia de su licencia federal",
    "apto médico":               "apto médico vigente",
    "experiencia quinta rueda/full": "experiencia en quinta rueda o full",
    "cartas laborales":          "cartas laborales",
}

# ---------------------------------------------------------------------------
# Plantillas por etapa (lista indexada por intento, 0-based internamente)
# Placeholders: {nombre}, {campo_faltante}
# ---------------------------------------------------------------------------

_PLANTILLAS: dict[str, list[str]] = {
    "new": [
        "Hola {nombre}, ¿tuvo oportunidad de revisar la vacante de operador de quinta rueda? "
        "Con gusto le cuento más sobre el proceso.",

        "Hola {nombre}, seguimos con la vacante disponible. "
        "¿Le interesa que continuemos con su registro?",

        "Hola {nombre}, este es nuestro último mensaje automático. "
        "Cuando guste retomar el proceso, aquí seguimos con gusto.",
    ],
    "interested": [
        "Hola {nombre}, ¿tuvo oportunidad de revisar la información que le compartimos? "
        "Para avanzar solo necesitamos unos datos.",

        "Hola {nombre}, para continuar su proceso de reclutamiento, "
        "¿me puede compartir un momento para terminar su perfil?",

        "Hola {nombre}, es nuestra última consulta automática. "
        "Si desea retomar su proceso, aquí le atendemos.",
    ],
    "vacancy_info_shared": [
        "Hola {nombre}, para avanzar su proceso solo necesito un par de datos. "
        "¿Me puede decir desde qué ciudad o estado nos escribe?",

        "Hola {nombre}, seguimos disponibles para continuar con su perfil. "
        "¿Tiene un momento para compartir sus datos?",

        "Hola {nombre}, último mensaje automático. "
        "Cuando guste retomar, aquí seguimos.",
    ],
    "profile_hint_collected": [
        "Hola {nombre}, quedamos pendientes de su {campo_faltante}. "
        "¿Le es posible compartirlo cuando tenga un momento?",

        "Hola {nombre}, para completar su perfil aún necesitamos su {campo_faltante}. "
        "¿Puede ayudarnos con ese dato?",

        "Hola {nombre}, último recordatorio automático sobre su {campo_faltante}. "
        "Cuando pueda, aquí le esperamos.",
    ],
    "documents_pending": [
        "Hola {nombre}, cuando tenga oportunidad, ¿puede compartir sus documentos "
        "para continuar con su proceso?",

        "Hola {nombre}, su perfil está casi listo. "
        "Solo necesitamos sus documentos para avanzar a la siguiente etapa.",

        "Hola {nombre}, último recordatorio automático sobre sus documentos. "
        "Cuando pueda, aquí le esperamos.",
    ],
    "apto_pending_update": [
        "Hola {nombre}, ¿ya pudo renovar su apto médico? "
        "Con eso podemos avanzar su proceso.",

        "Hola {nombre}, ¿hay alguna novedad con su apto médico? "
        "Estamos listos para continuar cuando lo tenga.",

        "Hola {nombre}, último aviso sobre el apto médico. "
        "Cuando lo renueve, con gusto retomamos.",
    ],
    "followup_pending": [
        "Hola {nombre}, aquí seguimos cuando guste retomar el proceso. Sin prisa.",

        "Hola {nombre}, solo pasamos a saludar. "
        "Si desea continuar su proceso, con gusto le atendemos.",

        "Hola {nombre}, este es nuestro último mensaje automático. "
        "Cuando quiera retomar, aquí seguimos.",
    ],
    # Flujo especial: profile_ready / human_review → coordinar llamada
    "profile_ready": [
        "Hola {nombre}, su información ya está lista para revisión de Capital Humano. "
        "Para que puedan hablar con usted, ¿le parece si le hacemos una llamada? "
        "Si es así, ¿en qué horario de lunes a sábado le viene mejor contestar?",
    ],
    "human_review": [
        "Hola {nombre}, Capital Humano tiene su perfil para revisión. "
        "Para coordinar, ¿le parece si le hacemos una llamada? "
        "¿En qué horario de lunes a sábado está disponible para contestar?",
    ],
}


def get_template(etapa: str, intento: int) -> str | None:
    """Devuelve el texto de plantilla para la etapa e intento dados (intento 1-based)."""
    variantes = _PLANTILLAS.get(etapa) or _PLANTILLAS.get("followup_pending", [])
    if not variantes:
        return None
    idx = min(intento - 1, len(variantes) - 1)
    return variantes[idx]


def render_template(
    plantilla: str,
    nombre: str | None,
    campo_faltante: str | None = None,
) -> str:
    """Interpola los placeholders de la plantilla."""
    nombre_display = nombre or "candidato"
    campo_display = _CAMPO_DISPLAY.get(campo_faltante or "", campo_faltante or "dato pendiente")
    return (
        plantilla
        .replace("{nombre}", nombre_display)
        .replace("{campo_faltante}", campo_display)
    )


def nota_horario_llamada(nombre: str | None, mensaje_candidato: str, etapa: str, telefono: str | None) -> str:
    """Nota interna para Chatwoot cuando el candidato indica su horario de disponibilidad."""
    etapa_label = ETAPA_DISPLAY.get(etapa, etapa)
    nombre_display = nombre or "Candidato"
    telefono_display = telefono or "No disponible"
    mensaje_seguro = (mensaje_candidato or "").strip()[:400]

    return (
        "📞 Disponibilidad para llamada\n\n"
        f"Candidato: {nombre_display}\n"
        f"Teléfono: {telefono_display}\n"
        f"Disponibilidad indicada: \"{mensaje_seguro}\"\n"
        f"Etapa: {etapa_label}\n\n"
        "Por favor coordinar llamada de Capital Humano en el horario indicado."
    )

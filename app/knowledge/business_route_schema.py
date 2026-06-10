"""Shadow classifier output schema — dataclasses puros, sin DB ni Chatwoot.

Contrato de salida del business route shadow classifier. Importable desde
cualquier capa sin efectos secundarios: no importa DB, Chatwoot, LLM, ni Redis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Catálogos de valores permitidos ──────────────────────────────────────────

BUSINESS_SIGNALS = frozenset({
    "objetivo_full_sencillo",
    "jerga_ambigua_falta_unidad",
    "considerar_escuelita_transmontes",
    "cecati_sugerido",
    "considerar_operador_b1",
    "reingreso_verificar",
    "seguimiento_llamada",
    "pago_condiciones",
    "ubicacion_base_traslado",
    "documentos_requisitos",
    "vacante_info_general",
    "complaint_with_candidate_interest",
    "referral_candidate_contact",
})

EXPLICIT_FACT_FIELDS = frozenset({
    "experience.vehicle_type",
    "candidate.city",
    "license.type",
    "license.status",
    "medical.apto_status",
    "experience.years",
    "documents.proof",
})

VALID_VEHICLE_TYPES = frozenset({"full", "sencillo"})

PROFILE_CONTEXT_ACTIONS = frozenset({
    "continue_profiling",
    "acknowledge_complaint_then_profile",
    "escalate_to_human",
    "await_document_update",
    "handle_referral",
})

POLICY_ANSWER_KEYS = frozenset({
    "no_pagares_en_blanco",
})

AMBIGUITY_FLAG_NAMES = frozenset({
    "vehicle_type_ambiguous",
    "multi_intent_unclear",
    "city_needs_confirmation",
    "multimedia_no_ocr",
})

HUMAN_REQUIRED_SIGNALS = frozenset({"considerar_operador_b1", "reingreso_verificar"})


# ── Tipos del output ──────────────────────────────────────────────────────────

@dataclass
class RequestedInfoItem:
    """Una categoría de información solicitada por el candidato."""
    category: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "evidence": self.evidence}


@dataclass
class ExplicitFact:
    """Hecho de perfil con evidencia literal del mensaje."""
    field: str
    value: str
    evidence: str           # substring literal del mensaje candidato
    confidence: float = 1.0
    needs_confirmation: bool = False   # True si contradice perfil canónico

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "needs_confirmation": self.needs_confirmation,
        }


@dataclass
class BusinessSignal:
    """Señal de ruta de negocio detectada en el mensaje."""
    name: str
    evidence: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "evidence": self.evidence, "confidence": self.confidence}


@dataclass
class AmbiguityFlag:
    """Flag de ambigüedad: el mensaje no puede resolverse sin más contexto."""
    name: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "evidence": self.evidence}


@dataclass
class BusinessRouteOutput:
    """Output completo del shadow classifier de ruta de negocio.

    Shadow-only: nunca muta DB, Chatwoot, labels ni profile_ready.
    """
    conversational_intents: list[str] = field(default_factory=list)
    requested_info: list[RequestedInfoItem] = field(default_factory=list)
    explicit_facts: dict[str, ExplicitFact] = field(default_factory=dict)
    business_signals: list[BusinessSignal] = field(default_factory=list)
    ambiguity_flags: list[AmbiguityFlag] = field(default_factory=list)
    requires_human: bool = False
    profile_context_action: str = "continue_profiling"
    policy_answer_keys: list[str] = field(default_factory=list)
    rag_needed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    shadow_error: str = ""      # error técnico interno (no exponer al candidato)

    # ── Helpers de consulta ───────────────────────────────────────────────────

    @classmethod
    def safe_empty(cls, error: str = "") -> "BusinessRouteOutput":
        """Fallback seguro ante error del LLM o input vacío."""
        out = cls()
        out.shadow_error = error
        return out

    def has_signal(self, name: str) -> bool:
        return any(s.name == name for s in self.business_signals)

    def signal_names(self) -> list[str]:
        return [s.name for s in self.business_signals]

    def flag_names(self) -> list[str]:
        return [f.name for f in self.ambiguity_flags]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversational_intents": self.conversational_intents,
            "requested_info": [r.to_dict() for r in self.requested_info],
            "explicit_facts": {k: v.to_dict() for k, v in self.explicit_facts.items()},
            "business_signals": [s.to_dict() for s in self.business_signals],
            "ambiguity_flags": [f.to_dict() for f in self.ambiguity_flags],
            "requires_human": self.requires_human,
            "profile_context_action": self.profile_context_action,
            "policy_answer_keys": self.policy_answer_keys,
            "rag_needed": self.rag_needed,
            "validation_errors": self.validation_errors,
            "shadow_error": self.shadow_error,
        }

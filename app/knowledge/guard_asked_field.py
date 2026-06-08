"""Captura pasiva del campo preguntado por el current_turn guard (Fase B).

Espejo EXACTO de la cascada de ``current_turn.next_question_from_missing_facts``:
decide el campo canónico activo por los **mismos facts faltantes y los mismos
predicados** que el guard usa para elegir su pregunta. NO parsea el texto de la
pregunta. Si el guard pregunta algo mixto (tipo+vigencia de licencia) o advisory
(apto), devuelve ``[]`` (criterio conservador, igual que el funnel nudge).

IMPORTANTE: este módulo duplica los predicados del guard a propósito (espejo
literal). Si ``next_question_from_missing_facts`` cambia su lógica, este helper
DEBE actualizarse en sincronía (lo blinda ``test_guard_asked_field`` con un test
de alineación). Refactor futuro a single source of truth queda documentado y
fuera de este bloque.

Puro: sin BD, sin writes, sin mutar la entrada.
"""
from __future__ import annotations

from typing import Any


def asked_field_keys_for_guard(facts: dict[str, Any]) -> list[str]:
    """Devuelve las asked_field_keys canónicas del campo que el guard preguntaría.

    Mismo orden y predicados que ``next_question_from_missing_facts``:
    - ``candidate.city`` faltante                         → ``["candidate.city"]``
    - licencia (``not category and not status``, MIXTA)   → ``[]``
    - ``experience.years`` faltante                       → ``["experience.years"]``
    - ``experience.vehicle_type`` faltante                → ``["experience.vehicle_type"]``
    - ``medical.apto_status`` faltante (advisory)         → ``[]``
    - ``documents.labor_letters`` faltante                → ``["documents.proof"]``
    - perfil completo (cierre)                            → ``[]``
    """
    if not facts.get("candidate.city"):
        return ["candidate.city"]
    # Pregunta MIXTA tipo+vigencia: predicado literal del guard (and). Conservador → [].
    if not facts.get("license.category") and not facts.get("license.status"):
        return []
    if not facts.get("experience.years"):
        return ["experience.years"]
    if not facts.get("experience.vehicle_type"):
        return ["experience.vehicle_type"]
    # Apto/vigencia advisory: diferido (igual que el funnel) → [].
    if not facts.get("medical.apto_status"):
        return []
    if not facts.get("documents.labor_letters"):
        return ["documents.proof"]
    return []

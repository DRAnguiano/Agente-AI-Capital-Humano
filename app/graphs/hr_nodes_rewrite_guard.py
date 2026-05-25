from __future__ import annotations

from typing import Any

from app.graphs.hr_state import HRState


AMBIGUOUS_TERMS = (
    "cachimba",
    "cachimbear",
    "cachimbr",
    "cachimb",
)

EXPLICIT_SUBSTANCE_TERMS = (
    "marihuana",
    "mariguana",
    "mota",
    "droga",
    "drogas",
    "cocaína",
    "cocaina",
    "cristal",
    "perico",
    "metanfetamina",
    "anfetamina",
    "opiáceos",
    "opiaceos",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    text_l = (text or "").lower()
    return any(term in text_l for term in terms)


def rewrite_safety_guard_node(state: HRState) -> dict[str, Any]:
    rewrite = dict(state.get("contextual_rewrite") or {})

    original = str(rewrite.get("original") or state.get("message") or "")
    rewritten = str(rewrite.get("rewritten") or "")

    original_has_ambiguous = _contains_any(original, AMBIGUOUS_TERMS)
    rewritten_has_explicit = _contains_any(rewritten, EXPLICIT_SUBSTANCE_TERMS)
    original_has_explicit = _contains_any(original, EXPLICIT_SUBSTANCE_TERMS)

    if original_has_ambiguous and rewritten_has_explicit and not original_has_explicit:
        unsafe_rewritten = rewritten

        rewrite["rewritten"] = (
            "¿Sabe si puedo continuar el proceso si antes me gustaba cachimbear, "
            "pero ya cambié?"
        )
        rewrite["should_use_rewrite"] = True
        rewrite["confidence"] = min(float(rewrite.get("confidence") or 0.7), 0.74)
        rewrite["reason"] = (
            "Rewrite corregido por seguridad: el mensaje original usa jerga ambigua "
            "y no debe convertirse en una sustancia específica no mencionada."
        )
        rewrite["safety_guard_applied"] = True
        rewrite["unsafe_rewritten"] = unsafe_rewritten

        corrections = rewrite.get("corrections")
        if isinstance(corrections, list):
            fixed = []
            for item in corrections:
                if not isinstance(item, dict):
                    fixed.append(item)
                    continue

                src = str(item.get("from") or "")
                dst = str(item.get("to") or "")

                if _contains_any(src, AMBIGUOUS_TERMS) and _contains_any(dst, EXPLICIT_SUBSTANCE_TERMS):
                    fixed.append({
                        "from": item.get("from"),
                        "to": "cachimbear",
                        "reason": "Jerga ambigua preservada; no se infiere sustancia específica.",
                    })
                else:
                    fixed.append(item)

            rewrite["corrections"] = fixed

        return {
            "contextual_rewrite": rewrite,
            "events": [{
                "type": "rewrite_safety_guard_applied",
                "unsafe_rewritten": unsafe_rewritten,
                "safe_rewritten": rewrite["rewritten"],
            }],
        }

    return {
        "contextual_rewrite": rewrite,
        "events": [{
            "type": "rewrite_safety_guard_checked",
            "applied": False,
        }],
    }

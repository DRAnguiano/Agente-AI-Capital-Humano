from __future__ import annotations

from pathlib import Path
import re

PATH = Path("app/orchestrators/knowledge_orchestrator.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"No encontré bloque para reemplazar: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    if "GREETING_REPLY =" not in text:
        text = replace_once(
            text,
            "FAREWELL_REPLY = (\n"
            "    \"Gracias a usted. Que tenga buen día y maneje con cuidado. Dejamos su seguimiento abierto; \"\n"
            "    \"cuando guste retomar el proceso, por aquí lo apoyamos.\"\n"
            ")\n",
            "FAREWELL_REPLY = (\n"
            "    \"Gracias a usted. Que tenga buen día y maneje con cuidado. Dejamos su seguimiento abierto; \"\n"
            "    \"cuando guste retomar el proceso, por aquí lo apoyamos.\"\n"
            ")\n\n"
            "GREETING_REPLY = (\n"
            "    \"Hola, buen día. Soy Mundo de Capital Humano de Transmontes. \"\n"
            "    \"Tenemos vacante para operador de quinta rueda; si gusta, primero le comparto detalles \"\n"
            "    \"y después revisamos si cuenta con licencia, apto médico y cartas laborales. \"\n"
            "    \"¿Actualmente maneja quinta rueda?\"\n"
            ")\n\n"
            "HIRING_REQUIREMENTS_REPLY = (\n"
            "    \"Para avanzar con contratación normalmente se revisa licencia federal vigente, \"\n"
            "    \"apto médico vigente, INE, CURP, comprobante de domicilio y cartas laborales. \"\n"
            "    \"No es necesario que me mande todo ahorita; primero solo necesito confirmar si cuenta con ello. \"\n"
            "    \"¿Su licencia federal y apto médico están vigentes?\"\n"
            ")\n",
            "reply constants",
        )

    old_controlled = """def _controlled_reply_from_contract(contract: dict[str, Any]) -> str:
    template = contract.get("reply_template")
    if isinstance(template, dict) and template.get("text"):
        return str(template["text"])
    if contract.get("requires_clarification"):
        return CONTROLLED_CLARIFICATION_REPLY
    if contract.get("requires_human"):
        return "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento."
    return CONTROLLED_FALLBACK_REPLY
"""
    new_controlled = """def _controlled_reply_from_contract(contract: dict[str, Any]) -> str:
    template = contract.get("reply_template")
    if isinstance(template, dict) and template.get("text"):
        return str(template["text"])

    intent = str(contract.get("intent") or "")
    if intent == "greeting":
        return GREETING_REPLY
    if intent == "requirements_documents" and contract.get("reason") == "deterministic_hiring_requirements_override":
        return HIRING_REQUIREMENTS_REPLY

    if contract.get("requires_clarification"):
        return CONTROLLED_CLARIFICATION_REPLY
    if contract.get("requires_human"):
        return "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento."
    return CONTROLLED_FALLBACK_REPLY
"""
    if old_controlled in text:
        text = text.replace(old_controlled, new_controlled, 1)

    old_farewell_fn = """def _looks_like_farewell(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False
    if not any(normalize_text(hint) in text for hint in FAREWELL_HINTS):
        return False
    if "?" in message or "¿" in message:
        return False
    if _message_has_any(message, BUSINESS_QUESTION_TERMS) and len(text) > 80:
        return False
    return True
"""
    new_farewell_block = """def _looks_like_greeting(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False
    greeting_terms = (
        "hola", "ola", "holaa", "buen dia", "buenos dias", "buenas", "buenas tardes",
        "buenas noches", "que tal", "q tal", "k tal", "hey"
    )
    return any(term in text for term in greeting_terms) and len(text) <= 120


def _looks_like_hiring_requirements(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False

    hiring_terms = (
        "contraten", "contratar", "contrate", "contratacion", "contratación", "kontraten",
        "kontrate", "k me contraten", "que me contraten", "me ocupen", "k me ocupen",
        "para ingresar", "para entrar", "ingresar", "entrar", "seguir proceso", "continuar proceso"
    )
    requirement_terms = (
        "que ocupa", "que ocupo", "que ocupan", "k ocupa", "k ocupo", "okupa", "okupo",
        "ocupa usted", "que se ocupa", "que se requiere", "que necesito", "que nesecito",
        "que piden", "que pido", "que suba", "k suba", "que mando", "que mande",
        "documentos", "documento", "papeles", "papel", "requisitos", "datos"
    )
    has_hiring = any(term in text for term in hiring_terms)
    has_requirement = any(term in text for term in requirement_terms)
    return has_requirement and (has_hiring or any(term in text for term in ("documento", "documentos", "papeles", "requisitos", "que suba", "k suba")))


def _looks_like_farewell(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False

    # Saludos como "Hola buen día" no son despedida.
    if _looks_like_greeting(message) and not any(term in text for term in ("gracias", "pase", "hasta luego", "nos vemos", "que este bien", "que esté bien")):
        return False

    if "?" in message or "¿" in message:
        return False

    strong_closing_terms = (
        "gracias senor", "gracias señor", "gracias muy amable", "muchas gracias",
        "pase buen dia", "pase buen día", "hasta luego", "nos vemos", "saludos",
        "que este bien", "que esté bien", "luego le escribo", "luego le marco", "lo retomo luego"
    )
    if not any(normalize_text(hint) in text for hint in strong_closing_terms):
        return False

    if _message_has_any(message, BUSINESS_QUESTION_TERMS) and len(text) > 80:
        return False
    return True
"""
    if old_farewell_fn in text:
        text = text.replace(old_farewell_fn, new_farewell_block, 1)

    old_apply = """def _apply_deterministic_overrides(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    if _looks_like_farewell(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["farewell"],
                "matched_aliases": ["farewell"],
                "intent": "farewell",
                "route": "profile",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reply_template": {"id": "farewell", "text": FAREWELL_REPLY},
                "reason": "deterministic_farewell_reply",
            }
        )
        return updated

    if _is_time_question(message):
"""
    new_apply = """def _apply_deterministic_overrides(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    # 1) La intención actual manda. Si pregunta qué se ocupa/sube para que lo contraten,
    # no permitas que smalltalk o memoria previa de pago gobiernen la respuesta.
    if _looks_like_hiring_requirements(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["requirements_documents"],
                "matched_aliases": ["hiring_requirements_override"],
                "intent": "requirements_documents",
                "route": "rag",
                "risk_level": "low",
                "requires_rag": True,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": ["02_documentos_requisitos.md"],
                "reply_template": None,
                "reason": "deterministic_hiring_requirements_override",
            }
        )
        return updated

    # 2) Saludo puro: respuesta de bienvenida, nunca fallback.
    if _looks_like_greeting(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["greeting"],
                "matched_aliases": ["greeting_override"],
                "intent": "greeting",
                "route": "greeting",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reply_template": {"id": "static_greeting", "text": GREETING_REPLY},
                "reason": "deterministic_greeting_reply",
            }
        )
        return updated

    # 3) Despedida real: solo señales fuertes de cierre.
    if _looks_like_farewell(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["farewell"],
                "matched_aliases": ["farewell"],
                "intent": "farewell",
                "route": "profile",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reply_template": {"id": "farewell", "text": FAREWELL_REPLY},
                "reason": "deterministic_farewell_reply",
            }
        )
        return updated

    if _is_time_question(message):
"""
    if old_apply in text:
        text = text.replace(old_apply, new_apply, 1)

    old_prompt_line = """Usa la memoria del lead solo como recordatorio; no la conviertas en interrogatorio.
Después de responder, regresa suavemente al proceso de reclutamiento si aplica.
"""
    new_prompt_line = """Usa la memoria del lead solo como recordatorio; no la conviertas en interrogatorio.
La intención del mensaje actual manda. No sigas hablando de pago/ruta solo porque la memoria diga que antes preguntó por eso.
Si el mensaje actual pide documentos, contratación o qué se ocupa/sube, responde eso y no regreses al tema anterior.
Haz máximo una pregunta útil para perfilar, no una lista de preguntas.
Después de responder, regresa suavemente al proceso de reclutamiento si aplica.
"""
    if old_prompt_line in text:
        text = text.replace(old_prompt_line, new_prompt_line, 1)

    PATH.write_text(text, encoding="utf-8")
    print("OK: guards de saludo/intención actual aplicados.")


if __name__ == "__main__":
    main()

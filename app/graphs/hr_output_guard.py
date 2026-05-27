from __future__ import annotations

import re
from typing import Any

from app.graphs.hr_state import HRState


def _sources_text(state: HRState) -> str:
    sources = state.get("sources") or []
    docs = state.get("relevant_docs") or state.get("retrieved_docs") or []
    chunks: list[str] = []

    for item in list(sources) + list(docs):
        if isinstance(item, dict):
            chunks.append(str(item.get("source") or item.get("id") or ""))
            chunks.append(str(item.get("text") or item.get("content") or ""))
            meta = item.get("metadata")
            if isinstance(meta, dict):
                chunks.append(str(meta.get("source") or ""))

    return " ".join(chunks).lower()


def _strip_think_blocks(reply: str) -> str:
    clean = (reply or "").strip()
    if not clean:
        return clean
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"</?think>", "", clean, flags=re.IGNORECASE)
    return clean.strip()


def _strip_public_noise(reply: str) -> str:
    clean = _strip_think_blocks(reply)

    # Remove repeated greeting in downstream RAG/profile outputs.
    clean = re.sub(
        r"^\s*(¡?Hola!?[,\s]*)?soy Mundo,?\s*asistente de Capital Humano\.?\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
    kept: list[str] = []

    generic_patterns = (
        r"^¿?deseas saber más.*\?$",
        r"^¿?desea saber más.*\?$",
        r"^¿?quieres saber más.*\?$",
        r"^¿?te gustaría continuar.*\?$",
        r"^¿?deseas continuar.*\?$",
        r"^¡?estamos aquí para guiarte.*!$",
        r"^si estás interesado.*podemos continuar.*$",
    )

    for p in paragraphs:
        low = p.lower().strip()
        if any(re.search(pattern, low, flags=re.IGNORECASE | re.DOTALL) for pattern in generic_patterns):
            continue
        kept.append(p)

    return "\n\n".join(kept).strip()


def _is_ambiguous_cachimba_case(state: HRState) -> bool:
    analysis = state.get("substance_disclosure_analysis") or {}
    raw = str(analysis.get("raw_mention") or "")
    msg = str(state.get("message") or "")
    rewrite = str((state.get("contextual_rewrite") or {}).get("rewritten") or "")
    haystack = f"{raw} {msg} {rewrite}".lower()

    return (
        analysis.get("detected") is True
        and str(analysis.get("status") or "").upper() == "AMBIGUOUS"
        and any(term in haystack for term in ("cachimba", "cachimbear", "cachimbr", "cachimb"))
    )


def _supports_zero_tolerance(state: HRState) -> bool:
    source_text = _sources_text(state)
    return any(
        term in source_text
        for term in (
            "03_seguridad_antidoping",
            "00_politicas_generales",
            "cero tolerancia",
            "0 tolerancia",
            "toxicológica",
            "toxicologica",
            "antidoping",
            "sustancias",
            "alcohol",
        )
    )


def _already_has_zero_tolerance_branch(reply: str) -> bool:
    low = (reply or "").lower()
    return (
        ("cero tolerancia" in low or "0 tolerancia" in low)
        and ("toxicológica" in low or "toxicologica" in low or "pruebas" in low)
    )


def apply_output_guard(reply: str, state: HRState) -> str:
    """
    Single canonical last-mile response guard.

    Both persistence and final API output call this same function so the
    zero-tolerance addendum and cleanup are idempotent.
    """
    clean = _strip_public_noise(reply)

    if (
        _is_ambiguous_cachimba_case(state)
        and _supports_zero_tolerance(state)
        and not _already_has_zero_tolerance_branch(clean)
    ):
        addendum = (
            "Si te refieres a consumo de sustancias o alcohol, la empresa maneja "
            "política de cero tolerancia y puede realizar pruebas toxicológicas. "
            "La continuidad del proceso depende de cumplir esa política y de la "
            "validación de Capital Humano."
        )
        clean = f"{clean}\n\n{addendum}".strip() if clean else addendum

    return clean.strip()

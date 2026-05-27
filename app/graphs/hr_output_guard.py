from __future__ import annotations

from typing import Any

from app.graphs.hr_hybrid_rules import output_guard
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
    Final deterministic cleanup.

    Phase 1 keeps the current graph intact, but routes all public cleanup through
    the single centralized hybrid output guard. The existing zero-tolerance
    addendum remains as a compatibility rule until the production hybrid graph
    moves this policy into the generate node contract.
    """
    clean = output_guard(reply)

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

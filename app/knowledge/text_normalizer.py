from __future__ import annotations

import re
import unicodedata
from typing import Iterable

_WORD_RE = re.compile(r"[^a-z0-9ñáéíóúü\s\-\.]", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")

# ── Canonicalización de jerga/typos (decisión 2026-06-12) ─────────────────────
# Los operadores escriben con faltas documentadas en data/05; el LLM las
# entiende pero los extractores deterministas no. Este es el punto único donde
# el sistema "documenta" lo que el candidato dijo en forma canónica. Solo
# entradas inequívocas: nada que pueda cambiar el sentido de negocio.
#
# Token → token (palabras completas, tras normalizar):
_TYPO_CANON: dict[str, str] = {
    "licensia": "licencia",
    "lisencia": "licencia",
    "lisensia": "licencia",
    "vijente": "vigente",
    "vijentes": "vigentes",
    "bijente": "vigente",
    "palasio": "palacio",
    "sensillo": "sencillo",
    "censillo": "sencillo",
    "voleto": "boleto",
    "boletos": "boleto",
    "vancate": "vacante",
    "bacante": "vacante",
    "bakante": "vacante",
}

# Frase → frase (bigramas seguros; NO se sustituye "d" suelta porque "tipo d"
# es una categoría de licencia válida):
_PHRASE_CANON: tuple[tuple[str, str], ...] = (
    ("soy d ", "soy de "),
    ("soi de ", "soy de "),
    ("soi d ", "soy de "),
    ("vivo n ", "vivo en "),
)


def strip_accents(value: str) -> str:
    """Return a lowercase accent-free string for robust dictionary matching."""
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_text(value: str) -> str:
    """Normalize human chat text without changing business meaning.

    This intentionally does not rewrite or infer intent. It only makes matching
    deterministic: lowercase, accent-insensitive, punctuation-light, whitespace
    compacted, and canonicaliza typos/jerga inequívocos del gremio
    (licensia→licencia, vijente→vigente, "soy d"→"soy de").
    """
    text = strip_accents(value or "").lower().strip()
    text = text.replace("/", " ").replace("_", " ")
    text = _WORD_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    if text:
        text = " ".join(_TYPO_CANON.get(tok, tok) for tok in text.split())
        padded = f"{text} "
        for src, dst in _PHRASE_CANON:
            padded = padded.replace(src, dst)
        text = padded.strip()
    return text


def normalize_aliases(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values or []:
        normalized = normalize_text(str(value))
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def contains_alias(normalized_message: str, normalized_alias: str) -> bool:
    """Check alias presence while avoiding most accidental substring matches."""
    if not normalized_message or not normalized_alias:
        return False

    # Multi-word aliases can be matched as phrases.
    if " " in normalized_alias or "-" in normalized_alias or "." in normalized_alias:
        return normalized_alias in normalized_message

    # Single-word aliases should match token boundaries.
    return re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_message) is not None


def matched_aliases(message: str, aliases: Iterable[str]) -> list[str]:
    normalized_message = normalize_text(message)
    hits: list[str] = []
    for alias in normalize_aliases(aliases):
        if contains_alias(normalized_message, alias):
            hits.append(alias)
    return hits

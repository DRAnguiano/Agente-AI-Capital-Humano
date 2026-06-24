"""rag-corpus — bug latente: los ids `InternalSource` del seed (`payment_policy`…) no
matcheaban el `source` (= nombre de archivo) que Chroma usa para filtrar (`_source_where`).
Funcionaba solo por nodos legacy en el grafo vivo; un grafo reconstruido desde el seed
dejaría los filtros RAG vacíos → fail-closed → sin contexto.

Fix: cada `InternalSource` de tipo `rag_document` declara `filename` = un `data/*.md` real,
y `neo4j_client` devuelve el filename como `preferred_source`. Tests estáticos sobre los
archivos (sin Neo4j ni Chroma), verificables sin re-seed.
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SEED = (_ROOT / "app/knowledge/neo4j_seed_hr_rules.cypher").read_text(encoding="utf-8")
_CLIENT = (_ROOT / "app/knowledge/neo4j_client.py").read_text(encoding="utf-8")
_DATA = {p.name for p in (_ROOT / "data").glob("*.md")}


def _rag_document_sources() -> list[tuple[str | None, str | None]]:
    out: list[tuple[str | None, str | None]] = []
    for block in re.findall(r"\{[^}]*kind:'rag_document'[^}]*\}", _SEED):
        sid = re.search(r"id:'([^']+)'", block)
        fname = re.search(r"filename:'([^']+)'", block)
        out.append((sid.group(1) if sid else None, fname.group(1) if fname else None))
    return out


def test_seed_has_rag_document_sources():
    assert _rag_document_sources(), "no se hallaron InternalSource rag_document en el seed"


def test_each_rag_source_declares_real_filename():
    for sid, fname in _rag_document_sources():
        assert fname, (
            f"InternalSource '{sid}' (rag_document) no declara filename → preferred_sources "
            f"devolvería el id de política y no matchea el source de Chroma"
        )
        assert fname in _DATA, f"filename '{fname}' del source '{sid}' no existe en data/"


def test_neo4j_client_returns_source_filename():
    # preferred_sources debe derivar del filename (no del id de política) para casar con
    # `_source_where`, que filtra Chroma por `source` = nombre de archivo.
    assert re.search(r"collect\(DISTINCT[^)]*s\.filename", _CLIENT), (
        "neo4j_client debe devolver s.filename en preferred_sources, no s.id"
    )

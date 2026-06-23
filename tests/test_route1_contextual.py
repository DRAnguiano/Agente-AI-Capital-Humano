"""Route-1 contextual resolver — Fase A shadow (G2).

Cubre:
  1. resolve_route1 (puro): allowlist, negación, multi-field, out-of-domain, etc.
  2. read_current_asked_field_keys: freshness strict (sin reach-back).
  3. Invariante de pureza: el resolver no persiste (sin BD/writes en su namespace).

Nota Fase B: en debounce ON existe la ruta `guard_context` en tasks_chatwoot.py que
puede persistir facts y reemplazar el reply después de handle_message. En Fase A no hay
conflicto (route-1 solo loguea); el cutover futuro deberá reconciliar ambas.
"""
from __future__ import annotations

import contextlib

import pytest

import app.knowledge.route1_contextual as R1
import app.lead_memory.last_asked_field as LAF


# ---------------------------------------------------------------------------
# 1) resolve_route1 — puro, log-only
# ---------------------------------------------------------------------------

# --- experience.years (cantidad numérica) ---

def test_years_confirmed():
    r = R1.resolve_route1("tengo 5 años", ["experience.years"])
    assert r["status"] == "confirmed"
    assert r["field"] == "experience.years"
    assert r["value"] == 5


def test_years_no_number():
    r = R1.resolve_route1("pues bastante", ["experience.years"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "no_number"


# --- experience.vehicle_type (unidad) ---

@pytest.mark.parametrize("text,value", [("full", "full"), ("sencillo", "sencillo")])
def test_vehicle_type_confirmed(text, value):
    r = R1.resolve_route1(text, ["experience.vehicle_type"])
    assert r["status"] == "confirmed"
    assert r["field"] == "experience.vehicle_type"
    assert r["value"] == value


def test_vehicle_type_camion_ambiguous():
    r = R1.resolve_route1("camión", ["experience.vehicle_type"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "ambiguous"


def test_vehicle_type_out_of_domain():
    # Texto fuera del dominio del campo activo (una ciudad) → no_persist.
    r = R1.resolve_route1("Torreón", ["experience.vehicle_type"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "ambiguous"


# --- documents.proof (sí/no) ---

def test_documents_proof_affirmative_confirmed():
    r = R1.resolve_route1("sí", ["documents.proof"])
    assert r["status"] == "confirmed"
    assert r["field"] == "documents.proof"
    assert r["value"] == "cartas"


def test_documents_proof_negation_no_persist():
    r = R1.resolve_route1("no", ["documents.proof"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "negation"


def test_documents_proof_ambiguous_no_persist():
    r = R1.resolve_route1("tal vez", ["documents.proof"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "ambiguous"


# --- guards transversales ---

def test_no_asked_field():
    assert R1.resolve_route1("full", None)["reason"] == "no_asked_field"
    assert R1.resolve_route1("full", [])["reason"] == "no_asked_field"


def test_multi_field_no_persist():
    r = R1.resolve_route1("full", ["experience.years", "experience.vehicle_type"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "multi_field"


@pytest.mark.parametrize("field", ["license.status", "medical.apto_status", "candidate.city", "license.type"])
def test_field_not_allowed(field):
    # vigencia / apto / campos diferidos quedan fuera del allowlist v1.
    r = R1.resolve_route1("sí", [field])
    assert r["status"] == "no_persist"
    assert r["reason"] == "field_not_allowed"


def test_negation_blocks_even_with_number():
    # "no tengo experiencia" → negación gana sobre cualquier número/valor.
    r = R1.resolve_route1("no tengo experiencia", ["experience.years"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "negation"


def test_allowlist_exact():
    assert R1.ROUTE1_ALLOWED == frozenset({
        "experience.years", "experience.vehicle_type", "documents.proof",
    })


# ---------------------------------------------------------------------------
# 2) read_current_asked_field_keys — freshness strict (sin reach-back)
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, row, sql_sink):
        self._row = row
        self._sql_sink = sql_sink

    def execute(self, sql, params=None):
        self._sql_sink.append(sql)

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, row, sql_sink):
        self._row = row
        self._sql_sink = sql_sink

    def cursor(self):
        return _FakeCursor(self._row, self._sql_sink)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_conn(monkeypatch, row):
    sql_sink: list[str] = []

    @contextlib.contextmanager
    def _get_conn():
        yield _FakeConn(row, sql_sink)

    monkeypatch.setattr(LAF, "get_conn", _get_conn)
    return sql_sink


def test_current_reads_keys_when_latest_has_metadata(monkeypatch):
    sql_sink = _patch_conn(monkeypatch, {"external_metadata": {
        "asked_field_keys": ["experience.vehicle_type"],
        "asked_field_source": "funnel_nudge",
        "asked_field_key_space": "canonical",
    }})
    assert LAF.read_current_asked_field_keys("L1") == ["experience.vehicle_type"]
    # Invariante de frescura: SIN filtro de metadata en el WHERE (no reach-back),
    # y orden estable por created_at + id.
    sql = sql_sink[0]
    assert "external_metadata ? 'asked_field_keys'" not in sql
    assert "ORDER BY created_at DESC, id DESC" in sql


def test_current_returns_none_when_latest_lacks_metadata(monkeypatch):
    # El último assistant real NO tiene asked_field_keys (p. ej. guard reply) → None.
    _patch_conn(monkeypatch, {"external_metadata": {"other": "x"}})
    assert LAF.read_current_asked_field_keys("L1") is None


def test_current_no_row_returns_none(monkeypatch):
    _patch_conn(monkeypatch, None)
    assert LAF.read_current_asked_field_keys("L1") is None


def test_current_empty_lead_key_returns_none(monkeypatch):
    def _boom():
        raise AssertionError("no debe abrir conexión con lead_key vacío")

    monkeypatch.setattr(LAF, "get_conn", _boom)
    assert LAF.read_current_asked_field_keys("") is None


def test_current_db_error_returns_none(monkeypatch):
    @contextlib.contextmanager
    def _get_conn():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(LAF, "get_conn", _get_conn)
    assert LAF.read_current_asked_field_keys("L1") is None


# ---------------------------------------------------------------------------
# 3) Invariante de pureza: el resolver no persiste
# ---------------------------------------------------------------------------

def test_resolver_is_pure_no_db_no_writes():
    # El módulo no debe importar acceso a BD ni funciones de escritura: garantiza
    # que en Fase A route-1 sólo loguea y nunca persiste.
    forbidden = {"get_conn", "upsert_lead_fact", "save_lead_message"}
    assert forbidden.isdisjoint(vars(R1).keys())


# ---------------------------------------------------------------------------
# 4) Matriz de QA shadow (casos controlados antes de pensar en persistencia)
#    Cada fila: (texto, asked_field_keys) -> (status, value, reason)
#    value se ignora cuando es None (no aplica).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,keys,status,value,reason", [
    # experience.years — cantidad/unidad (X/U/F)
    ("5",                  ["experience.years"],         "confirmed",  5,    "ok"),
    ("5 años",             ["experience.years"],         "confirmed",  5,    "ok"),
    ("tengo 10 años",      ["experience.years"],         "confirmed",  10,   "ok"),
    ("ahorita le digo",    ["experience.years"],         "no_persist", None, "no_number"),
    # unidad subanual/fraccional → needs_clarification (no confirmar como años)
    ("5 meses",            ["experience.years"],         "no_persist", None, "needs_clarification"),
    ("6 meses",            ["experience.years"],         "no_persist", None, "needs_clarification"),
    ("medio año",          ["experience.years"],         "no_persist", None, "needs_clarification"),
    ("año y medio",        ["experience.years"],         "no_persist", None, "needs_clarification"),
    ("5 años y 6 meses",   ["experience.years"],         "no_persist", None, "needs_clarification"),
    # experience.vehicle_type — negación + valor explícito → conservador (negación gana)
    ("no, sencillo",       ["experience.vehicle_type"],  "no_persist", None, "negation"),
    # documents.proof
    ("sí tengo cartas",    ["documents.proof"],          "confirmed",  "cartas", "ok"),
    ("no tengo",           ["documents.proof"],          "no_persist", None, "negation"),
    ("las subo luego",     ["documents.proof"],          "no_persist", None, "ambiguous"),
])
def test_shadow_qa_matrix(text, keys, status, value, reason):
    r = R1.resolve_route1(text, keys)
    assert r["status"] == status
    assert r["reason"] == reason
    if value is not None:
        assert r["value"] == value


# ---------------------------------------------------------------------------
# Deuda de cutover RESUELTA (G2 numeric unit hardening): unidad subanual no confirma.
# "5 meses" con F=experience.years ya NO se confirma como 5 años; ahora devuelve
# no_persist / needs_clarification. Antes era xfail; ahora es test normal.
# ---------------------------------------------------------------------------

def test_years_subannual_unit_does_not_confirm():
    r = R1.resolve_route1("5 meses", ["experience.years"])
    assert r["status"] == "no_persist"
    assert r["reason"] == "needs_clarification"



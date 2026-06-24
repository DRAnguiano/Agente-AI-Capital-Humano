from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from neo4j import GraphDatabase

from app.knowledge.text_normalizer import contains_alias, normalize_aliases, normalize_text

log = logging.getLogger(__name__)


RISK_RANK = {"low": 1, "medium": 2, "high": 3}
ROUTES_REQUIRING_RAG = {"rag"}
ROUTES_REQUIRING_HUMAN = {"human_handoff", "policy_boundary"}
ROUTES_REQUIRING_CLARIFICATION = {"clarification"}


@dataclass(slots=True)
class KnowledgeMatch:
    term_id: str
    canonical: str
    category: str
    aliases: list[str]
    matched_aliases: list[str]
    action: str | None
    meanings: list[str]
    intent: str | None
    risk_level: str
    route: str
    preferred_sources: list[str]
    reply_template: dict[str, Any] | None
    policies: list[dict[str, Any]]


class Neo4jKnowledgeClient:
    """Small read-only client for the HR operational knowledge graph.

    This is intentionally not an LLM/reranker/router. It only reads the typed
    graph and returns a clean decision contract for the FastAPI orchestrator.
    """

    # TTL de caché en segundos. Configurable via NEO4J_TERMS_CACHE_TTL en .env.
    # Default 300s (5 min) — los Term/GeoArea nodes cambian solo cuando el equipo
    # actualiza el grafo manualmente, no por actividad de candidatos.
    _CACHE_TTL: float = float(os.getenv("NEO4J_TERMS_CACHE_TTL", "300"))

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "")
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        # Caché en memoria por instancia (un proceso = una instancia vía _DEFAULT_CLIENT).
        self._terms_cache: list[dict[str, Any]] | None = None
        self._terms_cache_ts: float = 0.0
        self._profile_nodes_cache: list[dict[str, Any]] | None = None
        self._profile_nodes_cache_ts: float = 0.0

    @cached_property
    def driver(self):
        return GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        if "driver" in self.__dict__:
            self.driver.close()

    def healthcheck(self) -> dict[str, Any]:
        with self.driver.session(database=self.database) as session:
            value = session.run("RETURN 1 AS ok").single()["ok"]
        return {"ok": value == 1, "uri": self.uri, "database": self.database}

    def fetch_terms(self) -> list[dict[str, Any]]:
        now = time.time()
        if self._terms_cache is not None and (now - self._terms_cache_ts) < self._CACHE_TTL:
            log.debug("[NEO4J_CACHE] terms cache hit (age %.0fs)", now - self._terms_cache_ts)
            return self._terms_cache

        query = """
        MATCH (t:Term)
        OPTIONAL MATCH (t)-[:SUGGESTS_INTENT]->(i:Intent)-[:ROUTES_TO]->(r:Route)
        OPTIONAL MATCH (t)-[:PREFERS_SOURCE]->(s:InternalSource)
        OPTIONAL MATCH (t)-[:USES_REPLY]->(reply:ReplyTemplate)
        OPTIONAL MATCH (p:Policy)-[:APPLIES_TO]->(i)
        RETURN
          t.id AS term_id,
          t.canonical AS canonical,
          t.category AS category,
          coalesce(t.aliases, []) AS aliases,
          t.action AS action,
          coalesce(t.meanings, []) AS meanings,
          i.id AS intent,
          coalesce(i.risk_level, 'low') AS risk_level,
          r.id AS route,
          collect(DISTINCT coalesce(s.filename, s.id)) AS preferred_sources,
          CASE WHEN reply IS NULL THEN null ELSE {id: reply.id, text: reply.text} END AS reply_template,
          collect(DISTINCT CASE WHEN p IS NULL THEN null ELSE {
            id: p.id,
            label: p.label,
            risk_level: p.risk_level,
            public_guidance: p.public_guidance
          } END) AS policies
        """
        with self.driver.session(database=self.database) as session:
            rows = session.run(query)
            result = [dict(row) for row in rows]

        self._terms_cache = result
        self._terms_cache_ts = time.time()
        log.info("[NEO4J_CACHE] terms refreshed (%d rows)", len(result))
        return result

    def _matches_for_message(self, message: str) -> list[KnowledgeMatch]:
        normalized_message = normalize_text(message)
        matches: list[KnowledgeMatch] = []

        for row in self.fetch_terms():
            aliases = [str(x) for x in row.get("aliases") or []]
            normalized_aliases = normalize_aliases(aliases)
            hits = [alias for alias in normalized_aliases if contains_alias(normalized_message, alias)]
            if not hits:
                continue

            raw_policies = row.get("policies") or []
            policies = [item for item in raw_policies if isinstance(item, dict) and item.get("id")]

            route = str(row.get("route") or "fallback")
            risk = str(row.get("risk_level") or "low").lower()
            if risk not in RISK_RANK:
                risk = "low"

            matches.append(
                KnowledgeMatch(
                    term_id=str(row.get("term_id") or ""),
                    canonical=str(row.get("canonical") or ""),
                    category=str(row.get("category") or ""),
                    aliases=aliases,
                    matched_aliases=hits,
                    action=row.get("action"),
                    meanings=[str(x) for x in row.get("meanings") or []],
                    intent=row.get("intent"),
                    risk_level=risk,
                    route=route,
                    preferred_sources=[str(x) for x in row.get("preferred_sources") or [] if x],
                    reply_template=row.get("reply_template"),
                    policies=policies,
                )
            )

        return matches

    @staticmethod
    def _pick_best_match(matches: list[KnowledgeMatch]) -> KnowledgeMatch | None:
        if not matches:
            return None

        def score(match: KnowledgeMatch) -> tuple[int, int, int, int]:
            # Priority: risk, number of matched aliases, longest alias, explicit source/reply.
            risk_score = RISK_RANK.get(match.risk_level, 1)
            hit_count = len(match.matched_aliases)
            longest_hit = max((len(x) for x in match.matched_aliases), default=0)
            structured_bonus = int(bool(match.preferred_sources)) + int(bool(match.reply_template))
            return (risk_score, hit_count, longest_hit, structured_bonus)

        return sorted(matches, key=score, reverse=True)[0]

    @staticmethod
    def _contract_from_match(match: KnowledgeMatch | None, message: str) -> dict[str, Any]:
        if match is None:
            return {
                "recognized_terms": [],
                "matched_aliases": [],
                "intent": "unknown",
                "route": "fallback",
                "risk_level": "low",
                "requires_human": False,
                "requires_rag": False,
                "requires_clarification": True,
                "preferred_sources": [],
                "reply_template": None,
                "policies": [],
                "reason": "no_controlled_term_match",
                "normalized_message": normalize_text(message),
            }

        route = match.route or "fallback"
        return {
            "recognized_terms": [match.term_id],
            "matched_aliases": match.matched_aliases,
            "intent": match.intent or "unknown",
            "route": route,
            "risk_level": match.risk_level,
            "requires_human": route in ROUTES_REQUIRING_HUMAN or match.risk_level == "high",
            "requires_rag": route in ROUTES_REQUIRING_RAG,
            "requires_clarification": route in ROUTES_REQUIRING_CLARIFICATION,
            "preferred_sources": match.preferred_sources,
            "reply_template": match.reply_template,
            "policies": match.policies,
            "term_details": [
                {
                    "id": match.term_id,
                    "canonical": match.canonical,
                    "category": match.category,
                    "action": match.action,
                    "meanings": match.meanings,
                }
            ],
            "reason": f"term_{match.term_id}_suggests_{match.intent or 'unknown'}",
            "normalized_message": normalize_text(message),
        }

    def fetch_profile_nodes(self) -> list[dict[str, Any]]:
        """Return all GeoArea and VehicleType nodes used for profile fact extraction."""
        now = time.time()
        if self._profile_nodes_cache is not None and (now - self._profile_nodes_cache_ts) < self._CACHE_TTL:
            log.debug("[NEO4J_CACHE] profile_nodes cache hit (age %.0fs)", now - self._profile_nodes_cache_ts)
            return self._profile_nodes_cache

        query = """
        MATCH (n)
        WHERE n:GeoArea OR n:VehicleType
        RETURN
          n.id AS id,
          labels(n)[0] AS node_type,
          coalesce(n.aliases, []) AS aliases,
          n.profile_fact_group AS fact_group,
          n.profile_fact_key AS fact_key,
          n.profile_fact_value AS fact_value,
          coalesce(n.confidence, 0.9) AS confidence
        """
        with self.driver.session(database=self.database) as session:
            rows = session.run(query)
            result = [dict(row) for row in rows]

        self._profile_nodes_cache = result
        self._profile_nodes_cache_ts = time.time()
        log.info("[NEO4J_CACHE] profile_nodes refreshed (%d rows)", len(result))
        return result

    def extract_profile_facts_from_neo4j(self, message: str) -> list[dict[str, Any]]:
        """Match GeoArea/VehicleType aliases in message, return profile facts.

        Returns the same {fact_group, fact_key, fact_value, confidence} dicts as
        profile_extractor.extract_profile_facts(), so callers can merge both sources.
        Higher-confidence match wins when two nodes produce the same fact_group+key.
        """
        normalized = normalize_text(message)
        facts: list[dict[str, Any]] = []

        for row in self.fetch_profile_nodes():
            aliases = [str(x) for x in row.get("aliases") or []]
            normalized_aliases = normalize_aliases(aliases)
            if any(contains_alias(normalized, a) for a in normalized_aliases):
                facts.append(
                    {
                        "fact_group": str(row["fact_group"] or ""),
                        "fact_key": str(row["fact_key"] or ""),
                        "fact_value": str(row["fact_value"] or ""),
                        "confidence": float(row.get("confidence") or 0.9),
                        "neo4j_node_id": str(row["id"] or ""),
                    }
                )

        # Dedup: highest confidence wins for each (fact_group, fact_key) pair.
        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for f in facts:
            key = (f["fact_group"], f["fact_key"])
            if key not in dedup or f["confidence"] > dedup[key]["confidence"]:
                dedup[key] = f
        return list(dedup.values())

    def resolve_message(self, message: str, conversation_state: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            matches = self._matches_for_message(message)
            best = self._pick_best_match(matches)
            contract = self._contract_from_match(best, message)
            contract["all_matches"] = [
                {
                    "term_id": item.term_id,
                    "intent": item.intent,
                    "route": item.route,
                    "risk_level": item.risk_level,
                    "matched_aliases": item.matched_aliases,
                    "preferred_sources": item.preferred_sources,
                }
                for item in matches[:10]
            ]
            contract["conversation_stage"] = (conversation_state or {}).get("current_stage")
            return contract
        except Exception as exc:
            # Neo4j caído o lento: devolver contrato de fallback seguro para que
            # el bot pueda responder al candidato en lugar de generar un 500.
            log.error("[NEO4J_FALLBACK] resolve_message falló, usando fallback: %s", exc)
            fallback = self._contract_from_match(None, message)
            fallback["conversation_stage"] = (conversation_state or {}).get("current_stage")
            fallback["neo4j_error"] = str(exc)[:200]
            return fallback


_DEFAULT_CLIENT: Neo4jKnowledgeClient | None = None


def get_knowledge_client() -> Neo4jKnowledgeClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = Neo4jKnowledgeClient()
    return _DEFAULT_CLIENT


def resolve_message(message: str, conversation_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_knowledge_client().resolve_message(message, conversation_state=conversation_state)


def extract_profile_facts_from_neo4j(message: str) -> list[dict[str, Any]]:
    return get_knowledge_client().extract_profile_facts_from_neo4j(message)

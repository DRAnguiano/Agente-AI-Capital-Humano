from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from neo4j import GraphDatabase

from app.knowledge.text_normalizer import contains_alias, normalize_aliases, normalize_text


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
          collect(DISTINCT s.id) AS preferred_sources,
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
            return [dict(row) for row in rows]

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

    def resolve_message(self, message: str, conversation_state: dict[str, Any] | None = None) -> dict[str, Any]:
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


_DEFAULT_CLIENT: Neo4jKnowledgeClient | None = None


def get_knowledge_client() -> Neo4jKnowledgeClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = Neo4jKnowledgeClient()
    return _DEFAULT_CLIENT


def resolve_message(message: str, conversation_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_knowledge_client().resolve_message(message, conversation_state=conversation_state)

# Production hybrid migration plan

Goal: reduce latency and hallucination risk for the HR recruiting chatbot without losing the useful graph/vector behavior already tested.

## Guardrails for the migration

- Do not add more LLM validation nodes.
- Keep LangGraph as a simple orchestrator, not a long chain of LLM judges.
- Use exactly one centralized regex rule module for obvious entry/output guards.
- Keep rewrite because candidates send fragmented and misspelled messages.
- Use vector/RAG only for documentary knowledge: pay, benefits, routes, bases, requirements, medical, antidoping, training.
- Use persisted graph/state for candidate context: stage, lead status, profile fields, risk, last intent, answered topics.
- Every phase must be debugged and closed before moving to the next one.

## Phase 1 — Centralize deterministic guards and measure baseline

Status target: safe refactor, no behavioral rewrite of the full graph yet.

Changes:
- Add `app/graphs/hr_hybrid_rules.py`.
- Centralize entry regex rules and output cleanup rules.
- Route final output cleanup through the centralized output guard.
- Keep the current graph working while we measure latency and routes.

Debug completion criteria:
- 20–25 production-like test cases run successfully.
- No `<think>` in replies.
- No repeated assistant greeting in RAG/profile replies.
- No generic closing such as “¿hay algo más...?”.
- Baseline latency measured: avg, p95/manual max, slow cases identified.

Exit decision:
- Close Phase 1 only after we review debug output together.

## Phase 2 — Add context builder contract

Status target: stop making the LLM infer candidate state from raw history.

Changes:
- Add a context builder node that returns one compact payload:
  - rewritten_message
  - graph_state
  - profile summary
  - lead status
  - risk level
  - answered topics
  - vector_context
- Keep existing nodes behind a feature flag while comparing results.

Debug completion criteria:
- Candidate profile fields are not asked twice.
- Lead status remains consistent.
- RAG answers use vector context only for documentary facts.
- Latency is not worse than Phase 1.

## Phase 3 — Collapse LLM judges into one generate contract

Status target: reduce serial LLM calls.

Changes:
- Introduce a unified generate node.
- Move safety and anti-hallucination instructions into the generate prompt and deterministic output guard.
- Disable/freeze redundant LLM nodes behind flags:
  - hallucination_check
  - answer_check
  - semantic_uncertainty
  - profile_response_guard
  - standalone substance analysis, when safe to replace

Debug completion criteria:
- 20–30 production-like cases pass.
- Average latency drops materially.
- Sensitive policy cases remain safe.
- Documentary answers do not invent pay, routes, benefits, or approval.

## Phase 4 — Production pilot with Chatwoot/WhatsApp lead status

Status target: deploy the lean path for real operator leads.

Changes:
- Integrate lead status writes for Chatwoot labels:
  - nuevo
  - en_proceso
  - perfil_listo
  - requiere_humano
  - sin_respuesta
- Keep rollback flag to current graph.
- Track latency and handoff rate.

Debug completion criteria:
- No severe false promises.
- Human handoff is triggered for high-risk cases.
- Lead status is useful to recruiters.
- P95 latency is acceptable for sales/recruiting.

## Current phase

We are in Phase 1.
Do not proceed to Phase 2 until Phase 1 debug output is reviewed and accepted.

# Knowledge Graph Core

This folder contains the Neo4j migration path for the HR recruiting assistant.

Goal: move operational rules, controlled dictionary terms, routes, replies, and policies into a centralized knowledge graph instead of scattering regex/routing logic across LangGraph nodes.

Initial scope:
- Greeting and static replies
- Candidate dropoff recovery rules
- Controlled trucking/recruiting dictionary
- Sensitive policy boundaries
- FAQ/RAG topic routing metadata
- Cost and trace metadata hooks

The current LangGraph flow remains available while the `knowledge` mode is introduced behind a feature flag.

# Proposal: live-business-rule-enforcement

## Why

Una auditoría read-only del camino vivo (`tasks_chatwoot.py` →
`knowledge_orchestrator.handle_message` → `resolve_message` en `neo4j_client.py`)
encontró que varias reglas de negocio críticas **están especificadas pero solo obligan
al shadow classifier** (`business-route-shadow-classifier`), que por contrato "no muta
estado productivo". El camino vivo decide `requires_human` por match de aliases contra el
seed de Neo4j; y el seed **no contiene** términos para estas reglas, así que **no se
aplican en producción**:

1. **B1 / Estados Unidos no va a handoff en vivo.** No hay alias B1/USA/visa/cruce con
   `route=human_handoff` en el seed. Un candidato binacional/de cruce se perfila como
   vacante estándar. *(Riesgo alto: legal/operativo.)*
2. **Reingreso no va a handoff en vivo.** El seed solo tiene `dropoff_already_called`
   ("ya conseguí otro trabajo"), concepto distinto. *(Riesgo alto.)*
3. **Torton/rabón/reparto no se marcan escuelita en vivo.** Ausentes del seed; no se
   distinguen de experiencia objetivo full/sencillo. *(Riesgo medio.)*
4. **Sin guard de salida para "caduca"/"caducidad".** El léxico de plantillas es limpio,
   pero nada impide que el LLM (RAG/amistoso) emita esos términos. *(Riesgo bajo.)*

Estas reglas ya tienen texto y Scenarios en `business-route-shadow-classifier`
(req. B1 @124, reingreso @142, escuelita @83, "caduca" @190). Este change **no las
reinventa**: las **vincula al camino vivo** y fija el mecanismo.

## What Changes

- **Contrato:** delta en `message-orchestration` que obliga al camino vivo a aplicar
  handoff ante B1/US (1) y reingreso (2), señal escuelita ante torton/rabón/reparto (3),
  y a NO emitir "caduca/caducidad" (4) — reusando el comportamiento ya especificado para
  el shadow, ahora exigible en producción.
- **Mecanismo (decisión de arquitectura, ver design.md):** **guard determinista en
  Python** en el orquestador vivo, NO términos en el seed de Neo4j. El seed es solo
  vocabulario (faltas/coloquialismos para mapear lenguaje→concepto); la política
  operativa vive en código determinista, testeable sin Neo y alineada con el destino de
  la migración (clasificación de lenguaje separada de políticas de negocio).
- **Sin implementación de lógica todavía:** este change entrega el contrato + tests
  RED-first contra el orquestador vivo. La implementación del guard se hace después, con
  aprobación.

## Impact

- Specs: delta en `message-orchestration` (capability base).
- Código (fase posterior, no en este change): guard determinista en
  `app/orchestrators/knowledge_orchestrator.py` (pre-Neo o post-resolución), reusando la
  detección léxica ya existente en `app/knowledge/business_route_*`. Sin re-seed de Neo4j.
- Tests: nuevos casos RED contra el camino vivo (extensión de
  `tests/test_route1_contextual.py` / archivo nuevo `tests/test_live_business_rules.py`).
- No toca: OCR/audio, Meta, RAG corpus, ni el shadow classifier (sigue intacto).

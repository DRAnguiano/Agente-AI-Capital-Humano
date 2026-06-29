## Why

Cuando un candidato responde con una confirmación implícita a una pregunta del funnel — "Es correcto señor", "Sí", "Así es", "Exacto" — el bot vuelve a preguntar lo mismo porque no conecta la respuesta con la pregunta anterior. La infraestructura de Route-1 contextual (`route1_contextual.py` + `last_asked_field.py`) ya resuelve esto correctamente en shadow mode (Fase A): detecta el campo preguntado, clasifica la polaridad y devuelve `status=confirmed`. El problema es que ese resultado solo se loguea (`[ROUTE1_SHADOW]`) y no alimenta el flujo vivo.

El fix es conectar esa resolución al funnel nudge (Fase B): si route-1 confirma un campo, inyectarlo en `active_facts` para que el nudge no lo vuelva a preguntar, y prefijar la respuesta con un ack breve del dato confirmado.

## What Changes

- Promover route-1 de shadow a **activo** para los campos de su allowlist (`experience.years`, `experience.vehicle_type`, `documents.proof`): cuando `resolve_route1` devuelve `status=confirmed`, inyectar el hecho confirmado en `active_facts` del `_build_funnel_nudge`.
- Si route-1 confirma un campo y la ruta es `friendly_smalltalk`, anteponer un ack corto del dato antes del nudge del funnel: `"[Ack del dato]. [Siguiente pregunta]"`. El ack lo genera el sistema (string determinista por campo), no el LLM.
- El `[ROUTE1_SHADOW]` log se mantiene para trazabilidad, ahora reflejando la acción real.

## Capabilities

### New Capabilities

_(ninguna)_

### Modified Capabilities

- `message-orchestration`: Route-1 contextual MUST alimentar `active_facts` del funnel nudge cuando devuelve `status=confirmed`. La respuesta al candidato SHALL incluir un ack del dato confirmado antes de la siguiente pregunta del funnel.

## Impact

- `app/orchestrators/knowledge_orchestrator.py` — leer resultado de `resolve_route1` antes de llamar `_build_funnel_nudge`; si confirmed, inyectar en `active_facts` vía `pre_validated_facts` o parámetro adicional; prefijar reply con ack.
- `app/knowledge/route1_contextual.py` — agregar ack strings por campo para que el orquestador los use.
- Sin cambios en BD, API, Neo4j ni Chatwoot.
- Sin cambios en `last_asked_field.py` ni `contextual_answer_classifier.py` — ya funcionan.

## Why

Revisión de la conversación 130 (prod 2026-06-29) revela cuatro problemas de naturalidad que hacen al bot sonar robótico o corporativo:

1. **"Con ese perfil nos interesa conocerle" se repite 3 veces en el mismo chat** — viene de dos fuentes independientes: el string fijo de `current_turn.py:695` al capturar `experience.years`, y el prompt del LLM amistoso que sugiere exactamente esa frase como ejemplo, provocando que el LLM la imite. El candidato lo percibe como formulaico.

2. **Variante de funnel "¿cuántos años lleva manejando de manera profesional?"** suena a entrevista de RH formal. El candidato es trailero; las otras variantes existentes ("¿Cuántos años tiene de experiencia como operador?", "¿Cuánto tiempo tiene de experiencia al volante?") ya son mejores. La variante problemática puede eliminarse.

3. **El prompt del LLM amistoso (`_answer_friendly_message`) sugiere frases concretas** en el campo `tono_extra` cuando el candidato tiene buen perfil (`_is_strong_candidate`): `"tipo 'Con ese perfil nos interesa conocerle' o 'Va por buen camino'"`. Eso convierte al LLM en un imitador de su propio prompt en lugar de generar variedad genuina.

4. **El string fijo de confirmación de experiencia** (`"Esa experiencia es valiosa. Con ese perfil nos interesa conocerle."`) es el mismo para todos los candidatos, independientemente de cuántos años tienen o qué unidad manejan.

## What Changes

- Eliminar la variante `"Para su perfil, ¿cuántos años lleva manejando de manera profesional?"` de `_FUNNEL_STEPS[experience.years]` en `knowledge_orchestrator.py`.
- Reemplazar el string fijo de confirmación de experiencia en `current_turn.py:695` por una confirmación simple y neutral que no elogie (evita la repetición de "nos interesa conocerle").
- Reescribir `tono_extra` en el prompt del LLM amistoso: en lugar de sugerir frases concretas (que el LLM imita), dar una instrucción de tono sin ejemplos literales.

## Capabilities

### New Capabilities

_(ninguna)_

### Modified Capabilities

- `message-orchestration`: El LLM amistoso MUST NOT recibir frases de ejemplo concretas en el prompt cuando el candidato tiene buen perfil — solo instrucción de tono general. El string de confirmación de `experience.years` MUST ser neutral, sin "nos interesa conocerle". La variante "de manera profesional" del nudge de experiencia MUST eliminarse.

5. **RAG responde con "nuestro equipo lo contactará" antes de completar el perfil** — el prompt del RAG (`context_builder.py`) instruye a usar esa frase "si es horario de atención". Cuando el perfil está incompleto, esa frase no tiene sentido: el equipo no puede contactar a alguien sin perfil. La instrucción debe condicionarse a que el perfil esté completo (`perfil_listo`), o eliminarse del RAG completamente dejando que la lógica de handoff la emita cuando corresponda.

## Impact

- `app/orchestrators/knowledge_orchestrator.py` — eliminar variante de funnel y reescribir `tono_extra` del prompt amistoso.
- `app/knowledge/current_turn.py` — reemplazar string de confirmación de experiencia línea 695.
- `app/knowledge/context_builder.py` — eliminar o condicionar la instrucción de "nuestro equipo lo contactará" en el prompt RAG para que solo aplique cuando el perfil ya está completo.
- Sin cambios en BD, Neo4j, Chatwoot, ni API.

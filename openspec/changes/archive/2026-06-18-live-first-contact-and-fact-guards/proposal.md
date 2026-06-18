# Proposal: live-first-contact-and-fact-guards

## Why

Los smokes del canal demo (conv. 80, 81 y 2026-06-12 10:40) mostraron cuatro
defectos del camino vivo que el realineamiento del corpus no puede corregir
porque son deterministas (no pasan por el LLM):

1. **Primer contacto sin saludo.** El mensaje default de la publicación de
   Facebook ("Me interesa la vacante de operador de quinta rueda") produce
   `candidate.vacancy_accepted` → el current-turn guard responde "Perfecto, lo
   dejo registrado. ¿en qué ciudad...?" en lugar del saludo oficial de Mundo.
   Regla de negocio (2026-06-12): Mundo SIEMPRE recibe con su saludo.
2. **El interés dispara el ack del guard.** `candidate.vacancy_accepted` cuenta
   como señal de perfil en `has_current_turn_profile_signal`, pero el interés no
   es un dato de perfil (regla ya documentada en el corpus).
3. **Facts geo extraídos de preguntas.** "¿qué rutas maneja para nuevo laredo?"
   persistió `candidate.city=Nuevo Laredo` + labels `foraneo`/`validar_traslado`
   porque la extracción de facts corre "regardless of route/intent" sin guard de
   pregunta (knowledge_orchestrator:712-735, alias GeoArea de Neo4j).
4. **Ciudad glotona.** "soy de Laredo ahí de donde a donde me toca ir?" →
   `candidate.city="Laredo Ahí De Donde A Donde Me Toca Ir"` (el regex de
   `_extract_city` captura hasta 40 caracteres sin cortar en conectores).

## What Changes

- `current_turn.py`: helper `is_campaign_or_interest_entry` (entrada de
  campaña/interés, no-pregunta) y exclusión de `candidate.vacancy_accepted` de
  las señales del guard.
- `tasks_chatwoot.py`: en primer contacto (sin mensaje previo del asistente),
  una entrada de campaña/interés responde `GREETING_REPLY` y el guard no aplica.
- `knowledge_orchestrator.py`: los facts geo (`candidate.city`/`candidate.state`)
  no se persisten desde mensajes-pregunta salvo que haya marcador de residencia
  ("soy de", "vivo en", "radico en", ...).
- `profile_extractor.py` · `_extract_city`: corte en conectores/interrogativos y
  tope de tokens en la captura.

## Impact

- Specs: deltas en `message-orchestration` y `profile-extraction`.
- Código: 4 archivos, cambios quirúrgicos deterministas; sin LLM, sin DB nueva.
- Tests: `tests/test_first_contact_and_fact_guards.py` (rojos primero).

## 1. Residencia: fuente única (geo-residency-single-source)

- [x] 1.1 Crear helper de dominio `residency_document_question(facts)` que centralice la regla local→IMSS / foráneo→cartas (incluye caso `proof == "ninguno"`), usando sólo `location.is_local_laguna`. **+ `residency_is_local(facts)`** como fuente única.
- [x] 1.2 En `app/knowledge/current_turn.py`: reemplazar el bloque `:458-477` por el helper; eliminar `LOCAL_LAGUNA` (`:34`) y el `OR normalize_text(...) in LOCAL_LAGUNA` (`:461`).
- [x] 1.3 En `app/orchestrators/knowledge_orchestrator.py`: reemplazar el bloque `:1626-1655` por el helper; eliminar `_LOCAL_LAGUNA` (`:1569`, `:1632`).
- [x] 1.4 Grep de confirmación: no quedan referencias activas a `LOCAL_LAGUNA`/`_LOCAL_LAGUNA` como fuente de residencia. **(Hallazgos extra fuera del audit: `chatwoot_note_sync.py:8` import muerto eliminado; `intent_orchestrator.py:31` lista hardcodeada reemplazada por catálogo.)**

## 2. LLM no infiere residencia (message-orchestration)

- [x] 2.1 Inyectar `location.is_local_laguna` (resuelto) al contexto que recibe la ruta RAG/LLM. **Vía `build_generation_prompt(residency_note=...)` + `_residency_prompt_note(facts)`; facts threaded desde `plan_and_respond` (merged) y `_resolve_embedded_question` (lead_memory + answers del turno).**
- [x] 2.2 Regla explícita anti-inferencia de residencia. **Añadida como instrucción 8 en `build_generation_prompt` (prompt RAG real), que es donde el LLM improvisó. `persona_config.SYSTEM_PROMPT` es para el endpoint `/ask`; la ruta viva usa el prompt del context_builder.**
- [x] 2.3 Verificar que con la señal `is_local_laguna=true` el LLM no emite "se considera foráneo". → ver 5.1

## 3. Política de horario para llamada (business-hours-contact-policy)

- [x] 3.1 Centralizar la decisión de copy de llamada por horario. **`get_template` ahora ramifica por `is_business_hours()`; el live-path ya usaba el gate en `_profile_complete_closing`.**
- [x] 3.2 En `app/followup/templates.py`: variantes `_PLANTILLAS_EN_HORARIO` para profile_ready/human_review (en horario → "el equipo te contacta"; fuera → coordinar llamada).
- [x] 3.3 Ruta RAG/LLM no sugiere llamada en horario: señal de horario inyectada al prompt (instrucción 9) + fallback sin-contexto consciente del horario.

## 4. Voz de equipo en fallbacks

- [x] 4.1 En `app/tasks_chatwoot.py:128`: default de `ASSISTANT_PUBLIC_INTRO` → "del equipo de reclutamiento de Transmontes".
- [x] 4.2 Voz de equipo en derivaciones: helper de residencia ("nuestro equipo le indique") + `greeting_reply_for_facts` (`:78`) + acuse escuelita (`:1769`). **Nota: `app/app.py:253-260` (endpoint `/ask` interno/test) aún dice "Capital Humano confirma" — fuera del path vivo; no tocado.**

## 5. Verificación

- [x] 5.1 Reproducir conversación 121: `_generate_rag_answer("soy de Chávez, ¿cuánto pagan?", {city:Chávez})` → prompt inyecta "LOCAL de la ZM Laguna", NO "FORÁNEO"; nota usa el mismo catálogo (`is_zm_laguna_canonical`) → coinciden. Verificado capturando el prompt.
- [x] 5.2 Caso en horario: nota determinista "Horario ACTIVO: el equipo contacta"; `get_template('profile_ready')` en horario → "se pondrá en contacto", sin llamada. Verificado con mock.
- [x] 5.3 Caso fuera de horario: `get_template` fuera de horario → "¿le hacemos una llamada?"; fallback RAG fuera de horario → "llámenos de 8:00 a 17:30". Verificado con mock.
- [x] 5.4 `openspec validate --strict` → válido. + `py_compile` de los 7 módulos + worker `celery ready` sin errores de import.

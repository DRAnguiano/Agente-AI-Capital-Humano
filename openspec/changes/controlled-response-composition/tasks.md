## 1. Contrato `ResponseComposition`

- [x] 1.1 Crear `app/knowledge/response_composer.py` con el frozen dataclass `ResponseComposition`. (Alcance bloqueado "solo el ack del guard": el guard no maneja laterales/política multi-bloque, así que los campos efectivos son `pending_question`, `deterministic_prefix`, `deterministic_ack`, `override`, `tone_signal`, `persisted`, `candidate_first_name`, `extraction_state`. `authorized_policy` se representa como `override`; `lateral_reply`/`transition`/`constraints` quedan fuera de alcance porque los laterales viven en el camino del orquestador, no en el guard.)
- [x] 1.2 Ensamblador `build_response_composition(message, merged_facts, current_facts, pre_validated, last_bot_message) -> ResponseComposition`: deriva cada campo de las fuentes que el worker ya tiene en el guard (sin nueva extracción). `pending_question` y `deterministic_prefix` salen de `current_turn_ack_parts` (misma lógica canónica que `build_current_turn_ack`).
- [x] 1.3 `_first_name(facts) -> str | None` (primer token capitalizado de `candidate.name`) y regla "persistido y confiable": `candidate_first_name` solo se puebla cuando `persisted` (hay facts validados del turno).
- [x] 1.4 Derivar `extraction_state` y `tone_signal` SOLO de señales ya disponibles (`pre_validated` y el texto del mensaje vía `_derive_tone`). Sin llamada LLM autoritativa.

## 2. Capa lingüística por bloques (Opción B)

- [x] 2.1 `compose_reply(rc: ResponseComposition) -> str`: si flag OFF, hay `override` de política, o el bloque no valida → ruta determinista directa.
- [x] 2.2 Prompt construido SOLO desde `rc` (prefijo canónico + `tone_signal` + nombre/persistencia). (Adaptado al alcance bloqueado: el guard produce un único bloque de reconocimiento, no el JSON `{acknowledgment, lateral, transition}`; no hay laterales ni transición libre que componer en el guard.)
- [x] 2.3 Ensamblado determinista: `bloque_reconocimiento + pending_question` vía `_join_ack_and_question`. La pregunta nunca proviene del modelo.
- [x] 2.4 Laterales (chiste/hora) viven en el camino del orquestador, NO en el guard (decisión bloqueada). El chiste ya se genera por LLM; la hora sigue determinista con `_time_reply`. El composer del guard no los toca. Ver 2.5 para el debanking del chiste.
- [x] 2.5 Retirado el banco estático de chistes de `_generate_joke_reply`: ya no recibe `fallback`; ante fallo/longitud/barda OMITE con cortesía (`_JOKE_SKIP`), no repite un chiste guardado. `_JOKE_BANNED` queda solo como validador. `_controlled_reply_from_contract` ya no sirve el texto del seed como chiste.

## 3. Validación estricta + fallback + anti-injection

- [x] 3.1 Validador en cascada (`_validate_ack_block`): `clean_reply`, longitud máx. (160), sin `?`/`¿`, sin cifras nuevas (`_has_number` del bloque vs. prefijo). (Nota: `_enforce_vigencia_lexicon` no se aplica al bloque de tono porque la pregunta canónica —que sí lleva el léxico de vigencia— la añade Python; el bloque solo reformula la confirmación.)
- [x] 3.2 Guarda de persistencia: si `not rc.persisted`, descartar bloques que casen `_PERSISTENCE_CLAIM` ("registrad", "aprobad", "quedó registrad/anotad", "ya avanzó", "cumple", …).
- [x] 3.3 Fallback total: cualquier excepción/timeout/vacío/JSON inválido/guarda violada → `deterministic_ack` (= `build_current_turn_ack`). Cubierto por `tests/test_response_composer.py`.
- [x] 3.4 Anti-injection: el mensaje crudo del candidato NO entra al prompt (solo viaja una `tone_signal` derivada de forma determinista) → resistente por construcción; además post-validación descarta afirmaciones de aprobación.

## 4. Integración en el worker (rama del current-turn guard)

- [x] 4.1 En `tasks_chatwoot.py`, rama `_guard_should_fire` (~502): `rc = build_response_composition(combined_content, merged_facts, _current_turn_facts, _pre_validated, last_bot_message)` y `guarded_reply = compose_reply(rc)`. `build_current_turn_ack` sigue siendo la fuente de `pending_question` y el fallback (vía `deterministic_ack`).
- [x] 4.2 NO se añadió un segundo escritor de facts: `persisted` se lee de `_pre_validated` (escritor único ya corrió en 428→1988 antes del guard). El upsert preexistente del guard (drift documentado) se dejó intacto, fuera de alcance.
- [x] 4.3 NO se tocó `_controlled_reply_from_contract` ni las ramas `local_time`/`requires_rag`/`greeting`/embedded_question/funnel nudge con el composer; el composer solo decora el prefijo del ack del guard. (`_generate_joke_reply` se modificó por la petición explícita de debanking, no por el composer.)
- [x] 4.4 Flags: `KNOWLEDGE_RESPONSE_COMPOSER_ENABLED` (default OFF) y `KNOWLEDGE_RESPONSE_COMPOSER_SHADOW`. (Timeout: se usa el del propio `call_llm`; no se añadió uno separado.)

## 5. Observabilidad

- [x] 5.1 Log estructurado `[COMPOSER]`: `used`/`fallback`, `reason` (`empty`/`too_long`/`has_question`/`fabricated_number`/`persistence_claim`/`llm_error:*`), `tone`, `persisted`, `canonical_question_preserved`, `compose_added_ms`. (Logs, no contadores de métricas dedicados.)
- [x] 5.2 Modo shadow (`[COMPOSER_SHADOW]`): genera y loguea `composed` vs `deterministic` sin enviar; el candidato sigue recibiendo el determinista.

## 6. Pruebas ejecutables

- [x] 6.1 `tests/test_response_composer.py` — unidad del ensamblador y validadores: contrato bien formado; `deterministic_ack` == `build_current_turn_ack`; `pending_question` intacta; `candidate_first_name` vacío si no persistido.
- [ ] 6.2 (e2e — task 9.2) Edad aproximada → no persiste exacta, reconoce tono, repite pregunta exacta.
- [ ] 6.3 (e2e — task 9.2) Experiencia como rango/broma → no fija número exacto, mantiene pregunta de años.
- [ ] 6.4 (e2e — task 9.2) Documento faltante → solo política autorizada, sin inventar alternativas.
- [x] 6.5 Respuesta evasiva / frustrada → tono respetuoso (`_derive_tone`), conserva pregunta pendiente (fallback la preserva).
- [x] 6.6 Chiste generado por LLM y variado; fallback OMITE chiste sin caer en enlatado (no filtra el texto del seed). `TestHumorLLMConBarda` actualizado.
- [ ] 6.7 (regresión orquestador — sin cambios) Hora de fuente inyectada `_time_reply` + retoma; cubierto por suite existente.
- [ ] 6.8 (e2e — task 9.2) Pregunta de dominio con conocimiento aprobado → sustentada por política/RAG, no por el composer.
- [x] 6.9 Prompt injection → no confirma aprobación (guarda anti-persistencia), conserva pregunta, mensaje crudo no entra al prompt.
- [x] 6.10 LLM inválido/timeout/vacío → fallback determinista exacto.
- [x] 6.11 Webhook reintentado: el composer es puro (sin side-effects) e idempotente; la idempotencia del worker queda intacta.
- [ ] 6.12 (e2e — task 9.2) Dato válido → persistencia (escritor único, 1988) ocurre ANTES de que el guard pueda confirmarlo.
- [x] 6.13 Dato inválido / bloque inválido → la respuesta conserva la MISMA pregunta pendiente.

## 7. Casos xfail (límites reales declarados)

- [x] 7.1 `xfail`: tono perfecto en humor muy idiomático/regional (se acepta degradar a neutro).
- [x] 7.2 `xfail`: sarcasmo/ironía como `frustration` vs `humor` (señal best-effort).
- [x] 7.3 `xfail`: laterales fuera del catálogo soportado — el guard no los compone.

## 8. Migración incremental

- [x] 8.1 Fase 0 (shadow): `KNOWLEDGE_RESPONSE_COMPOSER_SHADOW=true` + `ENABLED=false` en prod desde 2026-06-24. Shadow NO bloqueante (hilo daemon) → cero latencia al candidato. Smoke-test en worker desplegado: candidato recibe determinista; `[COMPOSER_SHADOW]` se emite (ej. real: tono humor → guarda `fabricated_number` disparó, `composed:null`). Recolectando de tráfico real. (Operacional, ACTIVO.)
- [ ] 8.2 Fase 1 (canary): activar `KNOWLEDGE_RESPONSE_COMPOSER_ENABLED` por subconjunto; criterio = tasa de fallback baja + QA de naturalidad. (Operacional.)
- [ ] 8.3 Fase 2 (on): default ON; determinista como fallback permanente. (Operacional.)

## 9. Verificación y cierre

- [x] 9.1 `docker compose build worker api && docker compose up -d worker api` (2026-06-24, OK del usuario). Ambos `Up`; flags confirmados en el worker; smoke-test del módulo desplegado OK. Despliega el código de la rama `feat/controlled-response-composition` (PR #5, sin merge a main aún).
- [ ] 9.2 End-to-end por endpoint (casos 6.2, 6.3, 6.4, 6.8, 6.12) con user único; capturar request/respuesta. (Tras 9.1.)
- [x] 9.3 Regresión verde: `test_response_composer.py` (18 passed, 3 xfailed), `TestHumorLLMConBarda` (8 passed), `test_reply_cleaner.py`, `test_friendly_grounding.py` + `test_route1_contextual.py` (53 passed). NOTA: 3 fallas preexistentes en `test_current_turn_ack.py` (`*_single_perfecto`, `*_experience_years_not_duplicated_as_age`) — fallan idéntico contra HEAD (probado con stash), ajenas a este cambio (tests esperan redacción de confirm vieja "20 años de experiencia"). El refactor de `build_current_turn_ack` es byte-idéntico.
- [x] 9.4 `openspec validate controlled-response-composition --strict` → "Change is valid".
- [x] 9.5 Las 8 decisiones abiertas del design se resolvieron en `/opsx:verify` (incl. punto de inyección = solo ack del guard; drift escritor único = fuera de alcance).

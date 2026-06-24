> Convención: RED-first (test que falla → implementación → GREEN). Tests Groq-free en `api-test`.
> Implementación RAMA POR RAMA; cada rama se verifica 1×1 en producción (chat real) ANTES de
> marcar su task como completa. No marcar nada resuelto sin corroboración del usuario en Chatwoot/Telegram.

## 0. Prerequisitos (ya implementados, en esta sesión)

- [x] 0.1 `_contextual_expiration_text` migrado a LLM T=0 (P0 #1) — `current_turn.py`
- [x] 0.2 Edad/experiencia elíptica migrada a LLM T=0 (P0 #2) — `current_turn.py`
- [x] 0.3 `AGE_DISQUALIFICATION_LIMIT` movido a `settings.py` (env var)
- [x] 0.4 `AGE_DISQUALIFICATION_REPLY` eliminado; mensaje generado por LLM via `call_groq_with_system` + `persona_config.SYSTEM_PROMPT`
- [x] 0.5 Regla de descalificación por edad añadida a `persona_config.py` (sección DESCALIFICACIÓN POR EDAD)
- [x] 0.6 `guard_asked_field.py` + `knowledge_orchestrator.py` — todos los literales `>= 50` reemplazados por `AGE_DISQUALIFICATION_LIMIT` desde settings

## 1. Contrato B — Eliminar disambiguate_numeric_units.py

- [x] 1.1 Verificado: único caller era `route1_contextual.py` en modo shadow (log-only, no afecta replies)
- [x] 1.2 Eliminado `app/knowledge/disambiguate_numeric_units.py`
- [x] 1.3 `route1_contextual.py` actualizado: lógica numérica inlineada (isdigit + fractional + subannual check); import eliminado
- [x] 1.4 Nota en `docs/deuda_tecnica.md` — módulo eliminado 2026-06-23, lógica absorbida en route1_contextual + current_turn

## 2. P1 batch — profile_extractor migración a LLM

> Prerequisito para Contratos A y C.
> Ver auditoría P1 en la sesión de exploración (items 3–7 del reporte del auditor).

- [x] 2.1 RED+impl: `_find_expiration_text` en `profile_extractor.py` → LLM T=0
- [x] 2.2 RED+impl: `experience.years` en `profile_extractor.py` → LLM T=0
- [x] 2.3 RED+impl: `road_experience` + `_experience_context` guard → LLM T=0
- [x] 2.4 RED+impl: `candidate.city` rama libre → LLM T=0 (confianza 0.65)
- [x] 2.5 RED+impl: `scheduling.call_window_text` → LLM T=0; `classify_call_window` (determinista) se conserva
- [x] 2.6 Suite completa verde tras cada migración individual

## 3. Contrato C — Eliminar _NUM_WORDS duplicados

> Prerequisito: task 2 completo.

- [x] 3.1 `_NUMBER_WORDS` + `_number_token_to_int()` en `current_turn.py` — CONSERVADOS (uso determinista sobre facts ya estructurados, equivalente a fact_corrections._NUM_WORDS)
- [x] 3.2 `_NUMBER_WORDS` + `_number_word_to_text()` en `profile_extractor.py` — eliminados (eran para extracción de texto crudo, ya migrada)
- [x] 3.3 `fact_corrections.py._NUM_WORDS` — conservado intacto
- [x] 3.4 Suite completa verde

## 4. Contrato A — normalize_text sin typo canon

> Prerequisito: task 2 completo (todos los extractores de texto crudo migrados).

- [x] 4.1 Eliminado `_TYPO_CANON` dict de `text_normalizer.py`
- [x] 4.2 Eliminado `_PHRASE_CANON` tuple de `text_normalizer.py`
- [x] 4.3 Eliminado bloque de aplicación de ambos en `normalize_text()`; docstring actualizado
- [x] 4.4 Suite completa — cualquier fallo por typo = extractor sin migrar (blocker)
- [x] 4.5 Producción: verificar que candidatos con "licensia", "vijente", "sensillo" extraen correctamente via LLM

## 5. Verificación y cierre

- [x] 5.1 Suite completa verde (Groq-free)
- [x] 5.2 Rebuild + recreate; verificación en producción (chat real)
- [x] 5.3 `openspec validate llm-first-extraction --strict`
- [x] 5.4 Sincronizar deltas a specs principales y archivar el change

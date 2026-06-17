# Tasks: core-consistency-fixes

> Contrato + tests primero. NO implementar lógica hasta aprobación. Solo atiende los gaps
> de contrato (#1, #8) y la normalización (#15). Track B (#2/#3/#4/#10/#17) NO va aquí —
> ya está especificado y es deuda del cutover.

## Fase 0 — Decisión (DONE)

- [x] 0.1 Política #8 decidida: HUMAN_REVIEW no auto-reversible por el bot; liberable por
  acción humana explícita; sin auto-expiración; sin bloqueo permanente. (Ver design.md.)
- [x] 0.2 #15: zona canónica = `America/Mexico_City` (decisión de negocio del usuario).

## Fase 1 — Contrato (DONE en este change)

- [x] 1.1 Delta `message-orchestration`: requisito "Voz de equipo — no Capital Humano como
  tercero" (#1).
- [x] 1.2 Delta `message-orchestration`: requisito "Ciclo de vida de la revisión humana" (#8).
- [x] 1.3 Normalización #15: `America/Monterrey` → `America/Mexico_City` en el contrato de
  horario de oficina/llamada de `live-reply-grounding-and-quality` (specs/design/proposal/tasks).

## Fase 2 — Tests RED (sin implementación) — DONE

> `tests/test_core_consistency.py` creado. Deterministas, **sin Groq/LLM**. Verificado:
> **2 passed, 2 xfailed** (api-test, 0.34s). Los xfail(strict) son los gaps de contrato;
> al implementar Fase 3 harán XPASS y forzarán quitar el mark.

- [x] 2.1 #1 voz de equipo: `test_system_prompt_no_capital_humano_as_third_party`
  (xfail — cada línea con "Capital Humano" debe ser la regla que lo prohíbe) +
  `test_system_prompt_keeps_voz_de_equipo_rule` (verde, la regla persiste).
- [x] 2.2 #8 HUMAN_REVIEW: `test_update_stage_pins_human_review_no_auto_regression`
  (verde — el guard de no-auto-regresión ya existe en el SQL) +
  `test_human_review_has_explicit_release_path` (xfail — falta `db.release_human_review`).

## Fase 3 — Implementación (DONE — sin Groq)

- [x] 3.1 #1: reescritas las 12 instrucciones/ejemplos del SYSTEM_PROMPT que usaban
  "Capital Humano" como tercero → voz de equipo ("nuestro equipo"/"aquí lo
  validamos/revisamos"). Solo quedan las líneas 19 y 283, que lo nombran para PROHIBIRLO.
  `context_builder.py` ya cumplía (lo usa solo en la prohibición "jamás 'Capital Humano'").
- [x] 3.2 #8: `db.release_human_review(conversation_key, stage_to="START")` — UPDATE acotado
  con `WHERE current_stage='HUMAN_REVIEW_REQUIRED'`, pone `requires_human=false`/`risk_level='low'`.
  `update_stage` conserva el CASE que pin-ea HUMAN_REVIEW (no auto-regresión por mensajes).
  Tests `test_core_consistency.py` pasaron de xfail → verde.
- [x] 3.3 #8 operativo: endpoint `POST /admin/release-human-review` (guard `INTERNAL_API_KEY`)
  que invoca `db.release_human_review` — la vía explícita para que un agente/operación
  libere la conversación. Tests `tests/test_admin_release.py` (3 passed, sin Groq).
  Alternativa no implementada: detectar la señal de reasignación del agente en el webhook
  de Chatwoot (queda como opción futura; el endpoint cubre el contrato).

## Fase 4 — Validación

- [x] 4.1 `openspec validate core-consistency-fixes --strict` → valid.
- [x] 4.2 `tests/test_core_consistency.py`: **5 passed** (api-test, sin Groq). Suite completa
  diferida (política no-Groq del día); impacto en otros tests descartado por análisis de
  dependencias (nadie depende de las cadenas editadas; `release_human_review` es aditiva).
- [x] 4.3 Commiteado y pusheado (commit `1546ac3`, 2026-06-17). El endpoint operativo (3.3)
  queda pendiente de su propio commit.

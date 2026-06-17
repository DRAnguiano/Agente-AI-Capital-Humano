# Tasks: funnel-vigencia-edad

> Implementación pendiente de: (a) confirmación del copy de descarte por edad,
> (b) cierre de los changes anteriores (commits + suite). Tests rojos primero.

## Fase 0 — Confirmaciones de negocio

- [x] V0.0 Umbral de edad confirmado por negocio (2026-06-12): menor a 50 años;
  con 50 o más, descarte.
- [x] V0.1 Copy del descarte APROBADO (2026-06-12): "Gracias por su interés. Por
  el momento el perfil de esta vacante considera operadores menores de 50 años,
  por lo que no podemos continuar con su solicitud."
- [x] V0.2 El descarte por edad es DEFINITIVO (sin revisión de CH) — no se
  emite `requiere_revision_ch`; cierre del funnel con la razón visible en la
  Nota IA (bloqueo: edad fuera de perfil).
- [x] V0.3 Sin labels nuevas: el descartado queda sin `bot_activo` (terminal) y
  sin labels de revisión; el registro del motivo vive en facts/Nota.

## Fase 1 — Tests (RED)

- [x] V1.1 `tests/test_funnel_vigencia_edad.py`: orden del funnel (ciudad→edad→
  unidad→licencia→apto→años→documento laboral); descarte 50+; preguntas de
  vencimiento; repregunta "¿en cuánto tiempo se le vence?"; guion de trámite
  fijo (incl. insistencia); extracción de fechas/tiempos relativos.

## Fase 2 — Implementación (GREEN)

- [x] V2.1 `current_turn.py` · `next_question_from_missing_facts`: nuevo orden +
  pregunta de edad + preguntas de vencimiento + puente suave.
- [x] V2.2 Extractor de vencimientos (fecha y tiempo relativo) →
  `license.expiration_text` / `medical.apto_expiration_text`.
- [x] V2.3 Lógica >3 meses + rama de trámite (`aclaracion_pendiente` con papel;
  guion fijo sin papel; sin desviaciones).
- [x] V2.4 Descarte por edad 50+: guion + cierre del funnel.
- [x] V2.5 Renderer/Nota: vencimientos visibles (ya soportado: `· vigencia X`);
  pendiente solo si cambia el formato.

## Fase 3 — Verificación

- [x] V3.1 pytest targeted (`test_funnel_vigencia_edad.py`) + suite completa Docker:
  targeted 64 passed (junto a first-contact); suite **598 passed, 0 fallos** (2026-06-17).
- [x] V3.2 `openspec validate funnel-vigencia-edad --strict` → valid (2026-06-17).
- [~] V3.3 Comportamientos del smoke **cubiertos por tests deterministas**:
  `test_age_50_or_more_discards_without_more_questions`, `test_age_under_50_continues`,
  `test_vigente_without_expiration_reprompts_time`, `test_short_expiry_triggers_fixed_renewal_branch`.
  Falta solo la confirmación en el **stack vivo** (demo Chatwoot/worker) — acción del operador.
- [ ] V3.4 Commit aislado — pendiente de autorización (regla: no commit/push sin visto bueno).

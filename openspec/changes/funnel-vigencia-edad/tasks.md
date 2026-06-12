# Tasks: funnel-vigencia-edad

> Implementación pendiente de: (a) confirmación del copy de descarte por edad,
> (b) cierre de los changes anteriores (commits + suite). Tests rojos primero.

## Fase 0 — Confirmaciones de negocio

- [ ] V0.1 Copy exacto del descarte por edad (>56). Borrador en proposal.
- [ ] V0.2 ¿El descarte por edad admite revisión de CH o es definitivo?
- [ ] V0.3 ¿Label/etapa para descartado por edad? (sin inventar labels nuevas).

## Fase 1 — Tests (RED)

- [ ] V1.1 `tests/test_funnel_vigencia_edad.py`: orden del funnel (ciudad→edad→
  unidad→licencia→apto→años→documento laboral); descarte >56; preguntas de
  vencimiento; repregunta "¿en cuánto tiempo se le vence?"; guion de trámite
  fijo (incl. insistencia); extracción de fechas/tiempos relativos.

## Fase 2 — Implementación (GREEN)

- [ ] V2.1 `current_turn.py` · `next_question_from_missing_facts`: nuevo orden +
  pregunta de edad + preguntas de vencimiento + puente suave.
- [ ] V2.2 Extractor de vencimientos (fecha y tiempo relativo) →
  `license.expiration_text` / `medical.apto_expiration_text`.
- [ ] V2.3 Lógica >3 meses + rama de trámite (`aclaracion_pendiente` con papel;
  guion fijo sin papel; sin desviaciones).
- [ ] V2.4 Descarte por edad >56: guion + cierre del funnel.
- [ ] V2.5 Renderer/Nota: vencimientos visibles (ya soportado: `· vigencia X`);
  pendiente solo si cambia el formato.

## Fase 3 — Verificación

- [ ] V3.1 pytest targeted + suite completa Docker.
- [ ] V3.2 `openspec validate funnel-vigencia-edad --strict`.
- [ ] V3.3 Smoke demo: edad temprana; >56 descarta; "sí está vigente" repregunta
  tiempo; apto que vence en 18 días dispara guion de trámite.
- [ ] V3.4 Commit aislado.

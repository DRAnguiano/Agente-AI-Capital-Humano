# Tasks — candidate-label-safety

> Sin commits ni push hasta aprobación explícita de David.
> No tocar `openspec/changes/chatwoot-ai-note-contract/` ni
> `tests/test_chatwoot_note_renderer.py` (frente Nota IA separado).

## L1. Diagnóstico y contrato (este paso)

- [x] L1.1 Diagnóstico con archivo:línea de los tres riesgos (ver proposal.md):
      `app/app.py:559,562` (requiere_humano), `app/chatwoot_note_sync.py:245-248`
      + `271-273` (perfil_listo sin unidad, falta_unidad nunca emitida),
      `app/chatwoot_note_sync.py:236` (bot_activo nunca removido).
- [x] L1.2 Delta MODIFIED sobre `chatwoot-label-taxonomy` con los tres contratos
      (`specs/chatwoot-label-taxonomy/spec.md`).
- [x] L1.3 Tests inicialmente ROJOS en `tests/test_candidate_labels.py`
      (sección "candidate-label-safety"): fallback oficial, perfil_listo
      requiere unidad, bot_activo vs terminales.
- [x] L1.4 Confirmado en Docker (2026-06-11): 16 failed / 62 passed en
      `tests/test_candidate_labels.py` — los 16 fallos son exactamente los tests
      nuevos, por el bug actual (requiere_humano emitido, perfil_listo sin
      unidad, bot_activo no removido). Suite completa excluyendo
      `tests/test_chatwoot_note_renderer.py`: mismos 16 fallos, resto verde.

## L2. Implementación (bloqueada hasta aprobación)

- [x] L2.1 `app/app.py` `_fallback_chatwoot_labels`: `requiere_humano` →
      `requiere_agente`; aplicar regla terminal y filtro de catálogo (design D3).
- [x] L2.2 `app/chatwoot_note_sync.py` `calculate_candidate_labels`:
      `perfil_listo` exige `experience.vehicle_type ∈ VALID_VEHICLE_TYPES`;
      emitir/remover `falta_unidad` (design D2).
- [x] L2.3 `app/chatwoot_note_sync.py`: `TERMINAL_LABELS` + descarte de
      `bot_activo` al final del cálculo (design D1).
- [x] L2.4 Tests de L1.3 en verde sin modificar sus aserciones (Docker
      2026-06-11: 78 passed).

## L3. Validación y cierre

- [x] L3.1 Targeted: 78 passed (Docker 2026-06-11).
- [x] L3.2 Suite completa excluyendo `tests/test_chatwoot_note_renderer.py`:
      419 passed, 8 warnings externos (Docker 2026-06-11).
- [x] L3.3 `openspec validate candidate-label-safety --strict`: valid.
- [x] L3.4 Crear un commit aislado del change.
  - Evidencia: change, implementación y pruebas versionados en un único commit aislado.

## Deuda relacionada (NO en este change)

- Emisión de `objetivo_full_sencillo`, `local_laguna`, `cecati_sugerido`,
  `considerar_escuelita_transmontes`, `considerar_operador_b1` y
  `reingreso_verificar` desde el cálculo de labels (auditoría N7). El escenario
  terminal de `reingreso_verificar` quedará cubierto por la regla D1 cuando
  exista esa emisión.

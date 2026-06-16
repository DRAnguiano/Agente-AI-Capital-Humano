# Change: candidate-label-safety

## Why

La auditoría del 2026-06-11 confirmó tres violaciones vivas del contrato
`chatwoot-label-taxonomy` en el cálculo y fallback de labels:

1. **Label fantasma `requiere_humano`** — `_fallback_chatwoot_labels` en
   `app/app.py:559,562` emite `requiere_humano`, que no existe en el catálogo
   oficial de 24 labels. La label correcta es `requiere_agente`. Si el sync
   principal falla, Chatwoot recibe una label fuera de catálogo.
2. **`perfil_listo` sin unidad confirmada** — `calculate_candidate_labels` en
   `app/chatwoot_note_sync.py:245-248` usa
   `has_experience = vehicle_type OR years`: un candidato con solo
   `experience.years` (sin `full`/`sencillo` confirmado) puede recibir
   `perfil_listo`. Además `falta_unidad` está en el catálogo y en
   `_LABEL_DISPLAY` pero **nunca se emite**.
3. **`bot_activo` coexiste con labels terminales** — el spec
   (`chatwoot-label-taxonomy/spec.md:94-101`) exige remover `bot_activo` al
   aplicar `perfil_listo`, `requiere_agente`, `requiere_revision_ch`,
   `riesgo_alto` o `reingreso_verificar`; `calculate_candidate_labels:236`
   lo inicializa y ningún punto lo descarta.

## What Changes

- Delta MODIFIED sobre `chatwoot-label-taxonomy`: catálogo oficial obligatorio
  en todo path de emisión (incluido fallback), `perfil_listo` requiere
  `experience.vehicle_type` confirmado como `full` o `sencillo` (con emisión
  de `falta_unidad` cuando no lo está), y exclusión de `bot_activo` con un
  escenario por cada label terminal.
- Tests inicialmente rojos en `tests/test_candidate_labels.py` que demuestran
  los tres bugs actuales.
- Implementación posterior (tras aprobación): `app/chatwoot_note_sync.py`
  (`calculate_candidate_labels`) y `app/app.py` (`_fallback_chatwoot_labels`).

## Out of Scope

- Emisión de `objetivo_full_sencillo`, `local_laguna`, `cecati_sugerido`,
  `considerar_escuelita_transmontes`, `considerar_operador_b1` y
  `reingreso_verificar` desde `calculate_candidate_labels` (deuda N7 de la
  auditoría; requiere señales que hoy no llegan a este módulo).
- El renderer de la Nota IA (`render_candidate_note`) y el change
  `chatwoot-ai-note-contract` (frente separado, no tocar).
- Cambios en el shadow classifier.

## Impact

- Specs afectados: `chatwoot-label-taxonomy` (3 requirements MODIFIED).
- Código afectado (al implementar): `app/chatwoot_note_sync.py`, `app/app.py`.
- Tests: `tests/test_candidate_labels.py` (sección candidate-label-safety,
  roja hasta implementar).
- Sin impacto en DB, Chatwoot real, RAG ni Nota IA.

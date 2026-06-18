# Tasks: chatwoot-ai-note-contract

Referencia: `multi-intent-migration` tareas 10c.3, 10c.4, 10c.6, 10c.7 (parcialmente).

## Fase 1 — Tests primero (RED)

- [x] N1.1 `tests/test_chatwoot_note_renderer.py` escrito con los tests del contrato,
  incluyendo vigencia independiente de licencia/apto y nombre canónico
  `📋 Perfil confirmado`.
- [x] N1.2 Verificado en Docker (2026-06-11): 12 failed / 23 passed — los 12 fallos
  mapeados 1:1 contra requirements del spec (prohibiciones, acción única,
  nombre canónico, vigencia).

## Fase 2 — Implementación (GREEN)

- [x] N2.1 `render_candidate_note`: eliminada `Interés en pago/compensación`
  (variables `payment_raw`/`payment` + línea de render).
- [x] N2.2 `render_candidate_note`: eliminada la sección `🏷️ Labels`. Las labels
  siguen calculándose y sincronizándose como metadatos
  (`calculate_candidate_labels` y `_fallback_chatwoot_labels` sin cambios).
- [x] N2.3 `render_candidate_note`: eliminada `Acción:` de cabecera;
  `next_best_action` aparece solo en `⏭️ Siguiente acción`.
- [x] N2.4 `render_candidate_note`: eliminada `Disponibilidad actual`
  (variables `availability_raw`/`availability`).
- [x] N2.5 `render_candidate_note`: eliminada `🧠 Memoria breve` y la variable
  `memory` (incl. la guarda que reescribía memory); el campo de DB no se toca.
- [x] N2.6 Sección condicional `⚠️ Pendientes o conflictos`: derivada de los mismos
  `has_*` del blocker (unidad/licencia/apto/ciudad); ausente cuando el núcleo
  está completo. `Bloqueo actual` permanece en `📍 Embudo`.
- [x] N2.7 Renombrado `📋 Perfil detectado` → `📋 Perfil confirmado`; vigencia de
  licencia corregida (`license_exp_text`, no `apto_exp_text`); campo `Edad`
  agregado al perfil.
- [x] N2.8 Tests legacy del formato viejo migrados al contrato:
  `test_phase0_quick_wins.py::test_f26_nota_conserva_secciones_clave`
  (`Perfil confirmado`) y 3 tests de display en `test_candidate_labels.py`
  que exigían nombres de labels dentro de la nota (ahora verifican su ausencia,
  conforme al requirement "Labels fuera del cuerpo").

## Fase 3 — Verificación (REFACTOR/PASS)

- [x] N3.1 `pytest tests/test_chatwoot_note_renderer.py` — todos pasan (cubierto por la
  suite completa en Docker, 2026-06-11: 461 passed / 8 warnings, sin fallos del renderer).
- [x] N3.2 `pytest tests/test_candidate_labels.py tests/test_phase0_quick_wins.py` — sin
  regresión (misma corrida: 461 passed incluye ambos archivos en verde).
- [x] N3.3 `docker compose --profile test run --rm -e PYTHONPATH=/app api-test pytest -q`
  — full suite: 461 passed / 8 warnings (2026-06-11).
- [x] N3.4 `openspec validate chatwoot-ai-note-contract --strict` — valid (2026-06-11).
- [x] N3.5 `git diff --check` — limpio (solo warnings LF/CRLF de Windows).

## Fuera de este change (tareas separadas)

- [ ] Inconsistencia `objetivo_full_sencillo` en `calculate_candidate_labels` → tarea separada.
- [ ] Auditoría de nota (`note_version`, `facts_snapshot` → tarea 10c.9).
- [ ] Resumen determinístico de facts para reemplazar `memory_summary` → versión futura.
- [ ] Lógica horaria / `llamada_pendiente` → planner/handoff.

## Cierre para portafolio (2026-06-18)

Contrato de la Nota IA implementado. Las 4 tasks abiertas son **diferidas a otros changes /
versiones futuras** (objetivo_full_sencillo, auditoría de nota 10c.9, resumen determinístico de
facts, lógica horaria/llamada — esta última ya cubierta en live-reply B7.4/B7.5). Fuera del
alcance de este change. Archivado por portafolio.

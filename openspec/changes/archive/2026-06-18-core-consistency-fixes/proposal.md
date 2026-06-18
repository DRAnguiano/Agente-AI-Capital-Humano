# Proposal: core-consistency-fixes

## Why

Una auditoría read-only del núcleo (21 hallazgos, validados con evidencia) detectó dos
**gaps reales de contrato** y una **contradicción contrato↔código**. La mayoría de los
otros hallazgos (#2/#3/#4/#10/#17) ya están correctamente especificados y son deuda del
cutover multi-intent, o son detalles de implementación. Este change atiende solo lo que
necesita contrato nuevo o normalización:

1. **#1 — Voz de equipo sin contrato (gap).** `persona_config.py` exige "nunca uses
   'Capital Humano' como tercero" pero el mismo SYSTEM_PROMPT lo viola en ~10 instrucciones
   y ejemplos; `context_builder.py` refuerza la regla. No existe ningún SHALL en OpenSpec
   que fije esta regla, así que la inconsistencia no está protegida por contrato ni test.

2. **#8 — Ciclo de vida de HUMAN_REVIEW sin contrato (gap).** `db.py:update_stage` bloquea
   `HUMAN_REVIEW_REQUIRED` de forma **permanente** (CASE que nunca cambia). No hay spec que
   diga si el handoff es terminal o liberable. Resultado: leads válidos quedan atrapados sin
   vía de regreso.

3. **#15 — Zona horaria contradictoria (normalización).** El contrato de horario de oficina
   en `live-reply-grounding-and-quality` dice `America/Monterrey`; el código del check
   (`current_turn._TZ_CENTRO`, `knowledge_orchestrator`) usa `America/Mexico_City`. Decisión
   de negocio: **`America/Mexico_City` es la canónica**. Se normaliza el contrato a esa zona.

## What Changes

- **Contrato (este change):** delta en `message-orchestration` con dos requisitos nuevos:
  voz de equipo (#1) y ciclo de vida de la revisión humana (#8, política: no auto-reversible
  por el bot, liberable por acción humana explícita, sin bloqueo permanente).
- **Normalización (#15):** las referencias `America/Monterrey` del contrato de horario de
  oficina/llamada en `live-reply-grounding-and-quality` se cambian a `America/Mexico_City`
  para alinear con el código del check. NO se toca `followup/ventana.py`/`celery_app.py`
  (followup async, ventana 08:30–20:30 L–S, dominio distinto y funcionalmente equivalente).
- **Implementación de lógica:** este change entrega contrato + tests RED. Los cambios de
  código (limpiar el prompt, vía de liberación de HUMAN_REVIEW) se hacen después con aprobación.

## Impact

- Specs: delta en `message-orchestration`; normalización de texto de zona en
  `live-reply-grounding-and-quality` (no cambia comportamiento, solo el nombre canónico).
- Código (fase posterior): `persona_config.py` + `context_builder.py` (voz de equipo);
  `db.py:update_stage` + una vía de liberación (admin/agente) para HUMAN_REVIEW.
- No toca: el pipeline shadow, el cutover, OCR/audio, Meta.

# Proposal: chatwoot-ai-note-contract

## Antecedente

El change `multi-intent-migration` definió la arquitectura objetivo para la Nota IA
(spec `multi-intent-migration/specs/chatwoot-sync/spec.md`, tareas 10c.*). Las tareas
10c.3, 10c.4, 10c.6 y 10c.7 quedaron abiertas. Este change las cierra parcialmente:
implementa el renderer determinístico con el formato objetivo limpio.

El spec base (`openspec/specs/chatwoot-sync/spec.md`) establece que la nota es
display-only y nunca fuente de verdad. Este change no altera ese contrato; solo limpia
el renderer para que lo cumpla sin secciones que violan la spec.

## Problema

`render_candidate_note` en `app/chatwoot_note_sync.py` tiene 5 desviaciones respecto
al formato objetivo definido en `multi-intent-migration/specs/chatwoot-sync`:

1. **`Interés en pago/compensación`** — aparece en el perfil; la spec lo prohíbe (10c.3).
2. **`🏷️ Labels`** — aparece como sección; la spec exige que no esté en el cuerpo (10c.3).
3. **`Acción:` duplicada** — aparece en la cabecera y en `⏭️ Siguiente acción`; mismo valor (10c.4).
4. **`Disponibilidad actual: Pendiente`** — se muestra aunque no hay evidence; no aporta
   decisión operativa y usa el nombre de la label deprecada `disponible_acudir`.
5. **`🧠 Memoria breve`** — renderiza directamente `lead.memory_summary`, que puede
   contener texto LLM-generado no auditado; viola la garantía de renderer determinístico.

## Propuesta

Limpiar `render_candidate_note` para producir estrictamente el formato objetivo.
No cambiar `calculate_candidate_labels` ni la lógica de labels en este change.
No implementar lógica de horario/llamada (pertenece al planner/handoff, futuro).

## Fuera de alcance

- Lógica de `calculate_candidate_labels` (inconsistencia `objetivo_full_sencillo` → tarea separada).
- Scheduling/handoff de llamadas (`llamada_pendiente` → planner futuro).
- Auditoría de evento de nota (`note_version`, `facts_snapshot` → 10c.9).
- Resumen determinístico de facts para reemplazar `memory_summary` → versión futura.
- Cambios en DB, migraciones, Chatwoot real, RAG, shadow classifier.

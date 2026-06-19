## Context

`calculate_candidate_labels` (`app/chatwoot_note_sync.py`) es el único punto que aplica labels
en Chatwoot. Hoy emite un subconjunto del catálogo oficial; faltan `objetivo_full_sencillo`,
`cecati_sugerido`, `considerar_escuelita_transmontes`, `considerar_operador_b1`,
`reingreso_verificar`, `aclaracion_pendiente`, `falta_ciudad`, `falta_experiencia`. El catálogo
(`chatwoot-label-taxonomy`) ya especifica QUÉ y CUÁNDO; lo que falta es (1) que existan los
facts que disparan esas labels y (2) que la función los traduzca. El invariante del contrato es
**labels derivadas de Postgres, no del LLM**.

Las señales de negocio (cecati/escuelita/B1) hoy las calcula `business_route_classifier`/
`business_route_policy` en **shadow** vía LLM. El reto de diseño es completar las labels sin
romper el invariante determinista ni acoplar el etiquetado a una salida LLM no validada.

## Goals / Non-Goals

**Goals:**
- Emitir las 8 labels faltantes de forma determinista desde facts en Postgres, con las
  exclusividades del catálogo.
- Producir los facts que las disparan mediante detección determinista (catálogos/keywords),
  con evidencia literal y sin sobrescribir facts confirmados.
- RED-first, sin Groq en la decisión de labels ni en los tests.

**Non-Goals:**
- Activar el `business_route_classifier` LLM como fuente productiva de labels (queda en shadow;
  su wiring validado es trabajo futuro).
- Migraciones destructivas de `rh_lead_facts_v2` (los nuevos facts son aditivos).
- Tocar el path del bot vivo (webhook→worker→orquestador) más allá de extracción de facts y
  función de labels.

## Decisions

**D1 — Facts deterministas en `current_turn.py`, no desde el LLM de business-route.**
Los nuevos facts (`experience.non_target_vehicle_type`, ausencia de experiencia en carretera,
intención B1, reingreso, unidad ambigua) se derivan con catálogos/keywords normalizados —el
mismo patrón ya probado para `local_laguna` y `vehicle_type`— en la capa determinista del turno.
*Alternativa descartada:* persistir el `business_signal` del clasificador LLM. Rechazada porque
viola "labels desde Postgres, no del LLM" y acopla el etiquetado a una salida shadow no validada.
El clasificador LLM sigue como observador; su promoción es un change aparte.

**D2 — `calculate_candidate_labels` lee facts y aplica una resolución con prioridad.**
La tricotomía de experiencia-objetivo se resuelve con precedencia explícita
`objetivo_full_sencillo > considerar_escuelita_transmontes > cecati_sugerido` (unidad confirmada
gana sobre no-objetivo, que gana sobre ausencia de experiencia), garantizando exclusividad. `aclaracion_pendiente`
solo si la unidad no está confirmada. *Alternativa descartada:* emitir todas las que matcheen y
deduplicar después — rechazada por riesgo de estados contradictorios en Chatwoot.

**D3 — `falta_ciudad`/`falta_experiencia` desde campos núcleo ausentes**, consistente con el
requisito existente "Labels de campo faltante derivadas de missing_fields": sin `candidate.city`
→ `falta_ciudad`; sin ninguna señal de experiencia (ni unidad, ni años, ni no-objetivo, ni
ausencia declarada) → `falta_experiencia`. Se retiran al completarse, como las demás `falta_*`.

**D4 — `reingreso_verificar` es terminal:** al emitirse remueve `bot_activo` y marca
`requires_human` (canalización), reusando la mecánica ya existente para labels terminales.

**D5 — El contexto del worker debe incluir los nuevos facts.** `app/tasks_chatwoot.py` ya pasa
`facts` a la función; basta con que los nuevos `fact_key` se persistan en `rh_lead_facts_v2` y se
carguen en ese dict. Sin cambios de firma.

## Risks / Trade-offs

- [Detección determinista con menor recall que el LLM] → Mitigación: catálogos/keywords
  conservadores con evidencia literal; preferir no-emitir a falso positivo (el shadow LLM sigue
  disponible para comparar recall y priorizar ampliaciones de catálogo).
- [Falsos `considerar_operador_b1`/`reingreso` que canalizan a humano de más] → Mitigación:
  exigir evidencia literal fuerte; cubrir negativos en tests (B1 mencionado como duda ≠ intención).
- [Interacción de exclusividades con `perfil_listo`] → Mitigación: tests de matriz
  (objetivo+listo, no-objetivo bloquea listo) y reuso del gate existente.

## Migration Plan

1. Aditivo: nuevos `fact_key` en `rh_lead_facts_v2` (sin DDL destructivo; la tabla es de
   pares clave/valor).
2. Implementar RED-first: extracción determinista → emisión de labels.
3. Rebuild de la imagen `hr-rag-api` + recreate `api`/`worker`.
4. Verificación end-to-end por webhook (como `local_laguna`).
5. Rollback: revertir la función de labels; los facts nuevos quedan inertes si nadie los lee.

## Open Questions

- ¿`considerar_operador_b1` debe además bloquear `perfil_listo`, o solo canalizar a humano?
  (propuesta: canaliza y marca revisión, no bloquea el resto del perfil).
- ¿La señal de ausencia de experiencia en carretera amerita un fact propio o se infiere de
  "sin unidad ni años + intención de aprender"? (propuesta: fact propio explícito para
  trazabilidad y test determinista).

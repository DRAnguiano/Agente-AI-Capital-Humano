## Why

La auditoría 2026-06-19 encontró una incongruencia contrato↔código: el catálogo oficial
(`chatwoot-label-taxonomy`) declara labels core que `calculate_candidate_labels` (el path
vivo que realmente etiqueta en Chatwoot) **no emite**. El reclutador abre Chatwoot y no ve
si el candidato es objetivo, va a CECATI/escuelita, es B1 (EUA), es reingreso, o le falta
ciudad/experiencia — justo las señales que el sistema existe para mostrar (un perfil
accionable sin leer el chat). Es el mismo patrón ya corregido hoy para `answer_primary_question`
y `local_laguna`: el shadow/contrato va por delante del path vivo determinista.

## What Changes

- **Persistir como facts canónicos las señales que hoy solo existen en shadow o en el
  contrato del turno** (no en Postgres): experiencia en unidad no-objetivo
  (`experience.non_target_vehicle_type`: torton/rabón/reparto local/interurbano), ausencia
  de experiencia en carretera, intención B1/EUA, reingreso, y unidad ambigua (quinta
  rueda/tráiler/caja seca sin confirmar full/sencillo). Esto preserva el invariante del
  contrato "labels derivadas de Postgres, no del LLM".
- **Completar `calculate_candidate_labels` para emitir las 8 labels faltantes** de forma
  determinista desde facts: `objetivo_full_sencillo`, `cecati_sugerido`,
  `considerar_escuelita_transmontes`, `considerar_operador_b1`, `reingreso_verificar`,
  `aclaracion_pendiente`, `falta_ciudad`, `falta_experiencia` — respetando las exclusividades
  del catálogo (objetivo ⊕ cecati ⊕ escuelita) y las labels terminales que remueven
  `bot_activo` (`reingreso_verificar`).
- **Cablear la decisión de negocio del path vivo** (`business_route_classifier` /
  `business_route_policy`, hoy en shadow) hacia la persistencia de esos facts — el wiring
  productivo pendiente (business-route C7.4), sin reescribir el clasificador.
- Consolida tasks vigentes y dispersas de tres changes archivados (multi-intent 10a.1–10a.8,
  business-route C7.4, chatwoot-ai-note objetivo_full_sencillo) en un contrato vivo.
- **Corrige el silencio en canalización** (hallazgo prueba prod 2026-06-19): hoy
  `app/tasks_chatwoot.py` suprime TODA respuesta pública cuando `requires_human`, dejando al
  candidato en visto. El candidato SHALL recibir un **acuse específico por motivo** (reingreso,
  B1, escuelita, cecati…) antes de que el humano tome el caso.

No se toca el path del bot vivo más allá de la extracción/persistencia de facts y la función
de labels. Determinista, sin LLM en la decisión de labels. RED-first.

## Capabilities

### New Capabilities
<!-- ninguna: todas las labels y su semántica ya viven en capabilities existentes -->

### Modified Capabilities
- `profile-extraction`: nuevos facts canónicos que hoy no se extraen/persisten y que las
  labels core necesitan como fuente (`experience.non_target_vehicle_type`, ausencia de
  experiencia en carretera, intención B1, reingreso, unidad ambigua). Reglas de evidencia
  y no-sobrescritura aplican.
- `chatwoot-label-taxonomy`: precisar como requisitos *testables* la emisión determinista
  por label faltante (trigger + exclusividad) donde hoy solo está la tabla descriptiva —
  en particular `aclaracion_pendiente` (unidad ambigua) y la fuente-fact de
  `cecati_sugerido` / `considerar_escuelita_transmontes` / `considerar_operador_b1` /
  `reingreso_verificar`; más el cierre de funnel + canalización del candidato no-apto.
- `message-orchestration`: la canalización a Capital Humano entrega un acuse específico por
  motivo al candidato (no silencio); deja de suprimirse la respuesta pública en handoff.

## Impact

- **Código:** `app/chatwoot_note_sync.py` (`calculate_candidate_labels`); `app/lead_memory/profile_extractor.py`
  y/o `app/knowledge/current_turn.py` (producción de los nuevos facts); el contexto que el
  worker (`app/tasks_chatwoot.py`) pasa a la función de labels (debe incluir los facts/señales).
- **Datos:** nuevos `fact_key` en `rh_lead_facts_v2` (sin migración destructiva; aditivo).
- **Sin impacto en:** el bot vivo (webhook→worker→orquestador), nginx, infra de despliegue.
- **Riesgo:** bajo — lógica determinista sobre facts, cubierta RED-first; las labels nuevas
  son aditivas y respetan exclusividades del catálogo ya validadas.

## Why

La prueba en producción (2026-06-19, chat real del usuario) y la revisión de contratos
mostraron dos brechas grandes que el contrato vigente no cubre:

1. **El funnel es secuencial y rígido**, no un ciclo: re-pregunta lo ya contestado, no detecta
   respuestas ambiguas ("todo en regla" → no sabe que falta la vigencia), y no diferencia el
   documento laboral por residencia (local vs foráneo) ni infiere la unidad desde la licencia.
2. **La Nota IA es técnica** (`Embudo`, `Riesgo`, `Requiere humano`, `Canal`), pensada para TI,
   cuando quien la lee es personal administrativo de Capital Humano. Debe ser un **resumen
   operativo por escenario**, no una traducción del funnel técnico.

Objetivo: perfilar sin hostigar (preguntar solo lo ambiguo/no respondido) y entregar a Capital
Humano una nota administrativa clara por estado operativo.

## What Changes

- **Funnel como ciclo** (`message-orchestration`): cada turno re-evalúa TODA la request contra los
  campos núcleo y emite **solo** lo ambiguo o no respondido, respetando lo ya dado y los turnos
  previos (no re-saludar, no re-preguntar). Una respuesta tipo "tengo todo en regla" marca la
  **vigencia como ambigua** (no como confirmada) y dispara la pregunta de vencimiento.
- **Inferencia de unidad desde licencia** (`message-orchestration`): licencia **B** → ofrecer
  sencillo ("¿quiere una vacante de sencillo?"); **E** → ofrecer ambas ("¿full o sencillo?"); si
  declara full con licencia B, aclarar amablemente que con B aplica sencillo.
- **Documento laboral por residencia** (`message-orchestration` + `profile-extraction`): foráneo →
  **2 cartas laborales membretadas (forzoso)**; local ZM Laguna → 2 cartas **o** semanas cotizadas
  del **IMSS**. La pregunta del funnel se ajusta una vez conocida la ciudad.
- **Estado vencido-en-trámite** (`profile-extraction`): licencia/apto vencidos PERO con comprobante
  de cita/trámite → continúa con `aclaracion_pendiente`; sin comprobante → cierre suave (puede
  volver), `requiere_agente`, el bot deja de responder y la nota lo refleja.
- **Bienvenida** (`message-orchestration`): solo en la primera interacción — bienvenida, resolver
  duda si la hay, explicar que se hará una serie de preguntas (sin pedir documentación todavía) y
  pedir el nombre por cortesía.
- **Nota IA administrativa por escenario** (`chatwoot-ai-note`) — **BREAKING** del formato actual:
  quitar `Canal`; `Riesgo` solo si `riesgo_alto`; `Requiere humano` → `Requiere Agente`; reemplazar
  `Embudo/Etapa/Bloqueo` por lenguaje administrativo (`Estado del candidato` / `Lo que ya sabemos` /
  `Falta confirmar` / `Para Capital Humano`); cabecera por escenario; ciudad exacta de la ZM (no
  "La Laguna"); `Siguiente acción` dinámica según el último pendiente resuelto.

**No-Goals:** la edad mantiene la regla vigente (descarte desde 50 años, sin cambios). Las labels
técnicas siguen operando por detrás; solo dejan de ser el lenguaje visible de la nota.

## Capabilities

### New Capabilities
<!-- ninguna -->

### Modified Capabilities
- `message-orchestration`: funnel como ciclo (solo ambiguo/no respondido), inferencia
  licencia→unidad, documento laboral por residencia, detalles de bienvenida.
- `chatwoot-ai-note`: nota administrativa por escenario (reemplaza el formato técnico canónico).
- `profile-extraction`: facts de documento laboral por residencia, vencido-en-trámite con
  comprobante, y vigencia ambigua ("todo en regla").

## Impact

- **Código:** `app/knowledge/intent_orchestrator.py` (FUNNEL_STEPS / next_funnel_question →
  ciclo + ambigüedad + licencia→unidad + docs por residencia); `app/orchestrators/knowledge_orchestrator.py`
  (bienvenida, puente, cierre por vigencia); `app/lead_memory/profile_extractor.py` /
  `app/knowledge/current_turn.py` (facts nuevos); `app/chatwoot_note_sync.py` (`render_candidate_note`
  → nota administrativa por escenario).
- **Sin impacto en:** edad (se mantiene 50), webhook/worker/infra, labels técnicas (siguen).
- **Dependencia:** se apoya en los facts/labels de `live-label-completion` (escuelita/B1/reingreso/
  cecati/aclaracion_pendiente) para decidir el escenario de la nota.
- **Riesgo:** medio — toca el funnel vivo y el renderer de la nota; se mitiga RED-first, rama por
  rama (escuelita primero) y verificación 1×1 en producción antes de marcar tasks completas.

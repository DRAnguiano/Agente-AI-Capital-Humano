## Context

El funnel vivo (`intent_orchestrator.FUNNEL_STEPS` + `next_funnel_question`) es secuencial: emite
el primer campo incompleto, no detecta ambigüedad ("todo en regla") ni diferencia documento por
residencia, y no infiere unidad desde la licencia. La Nota IA (`render_candidate_note`) usa el
formato técnico canónico (Embudo/Riesgo/Requiere humano/Canal). Quien lee la nota es personal
administrativo de Capital Humano, no TI. Este change rediseña ambos sin tocar la edad (se mantiene
la regla vigente <50) ni la infraestructura.

## Goals / Non-Goals

**Goals:**
- Funnel como ciclo: preguntar solo lo ambiguo/no respondido sobre la request completa, sin
  hostigar ni re-preguntar.
- Nota administrativa por escenario, en lenguaje simple para Capital Humano.
- Documento laboral por residencia y estado vencido-en-trámite con comprobante.

**Non-Goals:**
- Cambiar la regla de edad (se mantiene descarte desde 50).
- Reemplazar las labels técnicas (siguen operando por detrás; solo dejan de ser lenguaje visible).
- OCR/validación de documentos por imagen (se mantiene: solo registrar para revisión humana).

## Decisions

**D1 — El ciclo del funnel se resuelve determinista sobre facts, no con LLM.** `next_funnel_question`
pasa de "primer incompleto" a "primer campo no resuelto NI ambiguo", evaluando los facts ya
persistidos del turno + memoria. La ambigüedad ("todo en regla") se detecta en extracción
(`current_turn`/`profile_extractor`): NO se confirma vigencia, queda pendiente → el ciclo la
pregunta. *Alternativa descartada:* clasificar ambigüedad con LLM en el funnel — rechazada por
costo/determinismo.

**D2 — Inferencia licencia→unidad en el orquestador del funnel.** Tras confirmar licencia, la
siguiente pregunta de unidad se condiciona: B→sencillo, E→full/sencillo. Se apoya en la semántica
B/E ya documentada (B apta solo sencillo; E ambas).

**D3 — Documento por residencia.** La pregunta y la validez del documento dependen de
`location.is_local_laguna` (ya computado en `current_turn`). Local: cartas o `semanas_imss`;
foráneo: cartas membretadas. El fact canónico es `documents.proof` (consolida la fragmentación
actual con `documents.labor_letters*`; la migración/uso unificado es parte de este change).

**D4 — Nota administrativa por escenario, renderer determinista.** `render_candidate_note` calcula
el **escenario operativo** desde facts/labels/estado (no LLM) y selecciona cabecera + campos
visibles + Siguiente acción. La nota mantiene determinismo (misma entrada → misma salida) y no
inventa valores. Las secciones técnicas (Embudo/Riesgo/Requiere humano/Canal) se reemplazan por
administrativas (Estado del candidato / Lo que ya sabemos / Falta confirmar / Para Capital Humano /
Siguiente acción). Riesgo solo si `riesgo_alto`.

**D5 — Siguiente acción dinámica = primer pendiente del núcleo.** Se deriva del mismo cálculo de
campos faltantes; al resolverse uno, avanza al siguiente. Núcleo completo: local → validar
documentos y continuar; foráneo → validar traslado, documentos y continuidad.

**D6 — Vencido-en-trámite.** Señal `*.tramite_comprobante`: con comprobante → `aclaracion_pendiente`
y el ciclo continúa; sin comprobante → cierre suave (mensaje de retomar), `requiere_agente`, bot
deja de responder, nota lo refleja.

## Risks / Trade-offs

- [Detección de ambigüedad con keywords pierde casos] → Mitigación: conservador; ante duda
  pregunta (no confirma de más); se valida 1×1 en producción.
- [Rediseño de la nota rompe tests del formato viejo] → Mitigación: MODIFIED explícito del contrato
  + tests RED por escenario; los tests del formato técnico se actualizan, no se ignoran.
- [Fragmentación `documents.proof` vs `labor_letters*`] → Mitigación: consolidar a `documents.proof`
  como canónico; vista/labels leen de ahí.

## Migration Plan

1. Aditivo en facts (`documents.proof`, `*.tramite_comprobante`); sin DDL destructivo.
2. RED-first **rama por rama**, empezando por **escuelita**, luego local listo, foráneo listo,
   vencido-en-trámite, CECATI, B1, reingreso, no-aplica.
3. Rebuild + recreate; verificación 1×1 en producción (chat real) antes de marcar tasks completas.
4. Rollback: el renderer y el funnel se revierten por función; los facts nuevos quedan inertes.

## Open Questions

- Orden de campos del ciclo cuando el candidato no aportó nada: ¿edad→ciudad→licencia→unidad→
  vigencia→experiencia→documentos? (la edad mantiene su regla; la unidad depende de la licencia).
- ¿`documents.proof` reemplaza por completo a `documents.labor_letters_status`/`labor_letters`, o
  se mantiene una vista de compatibilidad temporal?

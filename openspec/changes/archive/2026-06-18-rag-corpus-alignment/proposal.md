# Proposal: rag-corpus-alignment

## Why

El smoke test en el canal demo (2026-06-11, conversación 80) demostró que el corpus
RAG (`data/`) y el copy del código contradicen los contratos del proyecto y
envenenan la extracción de facts:

1. **"Quinta rueda" como identidad de la vacante.** `00_politicas_generales.md`,
   `02_documentos_requisitos.md`, `05_jerga_rcontrol.md`, el saludo vivo
   (`GREETING_REPLY`), el saludo de Fase 1A, la plantilla de follow-up y el nodo
   Neo4j `fifth_wheel_full` (aliases `full` ↔ `quinta rueda` ↔ `tracto`) enseñan
   al LLM —y al candidato— que la vacante es "operador de quinta rueda". El
   contrato (`domain_catalog`, 10b.13, 7.1a) dice lo contrario: quinta rueda es
   jerga compatible → `needs_clarification`, nunca un `vehicle_type`. Resultado
   observado: `experience.vehicle_type="quinta_rueda"` persistido en vivo.
2. **Vigencia "más de 6 meses"** en `02_documentos_requisitos.md` (6 lugares) y
   `persona_config.py` vs la regla oficial ">3 meses" (decisión 2C.0c, confirmada
   por negocio en el smoke).
3. **Boleto de autobús ofrecido a un candidato local** de Torreón: la respuesta
   sugerida principal de `04_bases_rutas.md` no condiciona por residencia aunque
   la sección se titula "Apoyo para candidatos foráneos".
4. **Fallback telefónico estando en horario y repregunta de ciudad conocida**:
   `00` enseña "indicar que llame" como regla general y la respuesta sugerida de
   pagos incluye "dime de qué ciudad eres" incondicional.
5. **Tres flujos de precalificación distintos** (doc 00, FUNNEL_STEPS,
   `next_question_from_missing_facts`); el doc 00 ni siquiera pregunta la unidad.
6. **Regla de negocio nueva fijada por Capital Humano**: el documento laboral
   depende de la residencia — foráneo: ≥2 cartas laborales membretadas; local
   (ZM de La Laguna): cartas o documento de semanas cotizadas del IMSS. RFC pasa
   a expediente (no precalificación). Edad sí se pregunta en el funnel.

## What Changes

- Reescritura quirúrgica de `data/00, 01, 02, 04, 05` (03 ya está alineado).
- Copy de código: `GREETING_REPLY` (knowledge_orchestrator), `_SIGNAL_REPLIES`
  greeting (intent_orchestrator), plantilla "new" de followup, ejemplos de
  `persona_config` (vigencia 3 meses, documento laboral por residencia, RFC a
  expediente), ack de `current_turn.py` (quinta_rueda ya no implica full).
- Seed Neo4j: separar el nodo `fifth_wheel_full` — `full` deja de tener alias
  `quinta rueda`/`quinta`/`tracto`; esos términos pasan a un nodo de jerga
  ambigua que no fija unidad.
- NO cambia: lógica de extracción, gates, labels, renderer (cambios de
  comportamiento van en changes separados con tests rojos primero).

## Impact

- Specs: nueva capability `rag-knowledge-corpus`.
- Código: solo strings/copy (sin lógica nueva).
- Despliegue: requiere **reindexar Chroma** (data/) y **re-seed de Neo4j**
  (nodos de jerga) después del deploy.

## Decisión: data/ permanece fuera de git

Por decisión de negocio (2026-06-12), `data/` sigue en `.gitignore`: el corpus
con tarifas no se versiona en el repo. Riesgo aceptado y conocido: no hay
historial ni rollback del contenido vía git; el respaldo es el disco/volumen y
este change documenta el estado alineado del corpus en su descripción
(K1.1–K1.5). El seed de Neo4j SÍ queda versionado
(`app/knowledge/neo4j_seed_hr_rules.cypher`).

## Why

El filtro de fuente del RAG (`_source_where`) exige igualdad EXACTA entre el
`preferred_source` y el metadata `source` de Chroma. Cuando Neo4j entrega el
nombre de fuente sin extensión (`"01_pago_prestaciones"` vía
`coalesce(s.filename, s.id)`, neo4j_client.py:104) no casa con el `source`
indexado con extensión (`"01_pago_prestaciones.md"`, app/indexer.py) → 0 chunks
→ `retrieve_preferred_context` vacío → `_answer_rag_message` devuelve
`NO_CONTEXT_REPLY`. Resultado: toda pregunta RAG cuyo contrato venga del grafo
(pago, requisitos, rutas) se deflecta al fallback telefónico/handoff pese a
existir contenido relevante (score ~0.6, min 0.25). Verificado en runtime:
`preferred_sources=[]` → 3 items; `['01_pago_prestaciones.md']` → 3 items;
`['01_pago_prestaciones']` → **0 items**.

## What Changes

- El emparejamiento de fuente del RAG SHALL ser insensible a extensión y a ruta:
  un `preferred_source` selecciona el chunk si su *stem* (basename sin extensión)
  coincide con el stem del `source` indexado, independientemente de si uno trae
  `.md`/`.markdown`/`.txt` o prefijo de ruta y el otro no.
- Reemplazar el `where` de igualdad exacta de Chroma en `_source_where`
  (context_builder.py:49-55) por una selección tolerante: recuperar candidatos y
  filtrar por stem en Python (junto al post-filtrado por fuente dominante que ya
  existe en context_builder.py:93-113), o normalizar ambos lados a stem antes de
  comparar.
- Sin cambios de datos en Neo4j ni en el indexer (alternativa descartada en
  design): el fix vive en la capa de recuperación para tolerar ambos productores
  de `preferred_sources` (intent_enricher con `.md`, grafo sin extensión).

## Capabilities

### New Capabilities
<!-- ninguna -->

### Modified Capabilities
- `knowledge-source-hygiene`: el filtrado por fuente preferida SHALL casar por
  stem (insensible a extensión/ruta), de modo que un nombre de fuente sin
  extensión proveniente del grafo siga seleccionando el contenido indexado y no
  deflecte una pregunta que sí tiene fuente autorizada.

## Impact

- Código: `app/knowledge/context_builder.py` (`_source_where`,
  `retrieve_preferred_context`, y/o el post-filtrado por fuente).
- Comportamiento: preguntas de pago/requisitos/rutas enrutadas por Neo4j dejan de
  deflectarse; el fallback telefónico/handoff vuelve a ser excepción (sin fuente
  real), no la norma.
- Sin cambios de esquema, de datos (`data/`) ni de reindexado.
- Independiente del change `funnel-loop-proof-and-response-data-consistency` (ya
  archivado); este hallazgo se documentó allí como fuera de alcance.

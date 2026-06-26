## Context

`retrieve_preferred_context` (context_builder.py:162) acota la recuperación de
Chroma a las fuentes que el contrato marca como preferidas. La selección se
construye en `_source_where` (context_builder.py:49-55) como un filtro de
igualdad exacta de Chroma: `{"source": <valor>}` o `{"source": {"$in": [...]}}`.

El metadata `source` se persiste en el indexer como la ruta relativa del archivo
**con extensión** (p. ej. `01_pago_prestaciones.md`). Hay dos productores de
`preferred_sources`:

- `intent_enricher.py` (mapa estático): usa nombres **con** `.md` → casa.
- Neo4j `neo4j_client.py:104` (`coalesce(s.filename, s.id)`): cuando `filename`
  es nulo cae al `id`, que es el nombre **sin** extensión → no casa.

Como Chroma sólo hace match exacto, el caso del grafo devuelve 0 chunks; aguas
abajo, `_answer_rag_message` (knowledge_orchestrator.py:960) interpreta "sin
items" como "sin contexto" y responde `NO_CONTEXT_REPLY`. Reproducción runtime:

| `preferred_sources` | items |
|---|---|
| `[]` | 3 |
| `['01_pago_prestaciones.md']` | 3 |
| `['01_pago_prestaciones']` | **0** |

## Goals / Non-Goals

**Goals:**
- Que un `preferred_source` con o sin extensión (y con o sin prefijo de ruta)
  seleccione el mismo contenido indexado.
- Fix mínimo en la capa de recuperación; tolerar ambos productores sin acoplarse
  a uno.
- No regresar el aislamiento por fuente: una pregunta de pago sigue limitándose a
  su fuente, no debe colar chunks de otros temas.

**Non-Goals:**
- No se modifica el indexer ni el formato de `source` en Chroma.
- No se modifica el seed/grafo de Neo4j (alternativa de datos descartada).
- No se toca el umbral `RAG_MIN_SCORE` ni la lógica de generación LLM.
- No se aborda el caso "el grafo no entrega ninguna fuente" (eso es correcto: sin
  fuente preferida la recuperación es global, ya funciona).

## Decisions

**D1 — Casar por stem en Python, no por `where` exacto de Chroma.**
El `$eq`/`$in` de Chroma no admite comparación por sufijo ni normalización. Se
retira (o se relaja) el `where` estricto de `_source_where` y se filtra el
resultado por *stem* del `source` contra los stems de `preferred_sources`. El
stem se define como el basename sin extensión conocida (`.md`, `.markdown`,
`.txt`). Esto reutiliza el punto donde ya existe post-filtrado por fuente
dominante (context_builder.py:93-113).

**D2 — Recuperar un poco más amplio cuando hay filtro de fuente.**
Al mover el filtro de Chroma a Python, se debe pedir suficientes candidatos
(`n_results`) para que, tras filtrar por stem, queden al menos `RAG_TOP_K`. Se
amplía `n_results` (p. ej. `max(RAG_TOP_K * 4, ...)`) sólo cuando hay
`source_filter`, preservando el comportamiento sin filtro.

**D3 — Normalización compartida.**
Una sola helper `_source_stem(value)` normaliza ambos lados (lower, basename,
quita extensión conocida). Se usa tanto para construir el conjunto permitido como
para comparar cada `item["source"]`, evitando divergencias.

## Risks / Trade-offs

- **Riesgo:** colisión de stems si dos archivos comparten basename con distinta
  extensión. Mitigación: el corpus actual usa nombres únicos (`00..05_*.md`); de
  todos modos casar por stem agrupa intencionalmente variantes del mismo doc.
- **Trade-off:** pedir más candidatos a Chroma cuando hay filtro tiene costo
  marginal; aceptable porque el corpus es pequeño (57 chunks) y evita el
  deflection. Sin filtro no cambia nada.
- **Riesgo:** que el filtrado en Python deje pasar fuentes no preferidas si la
  comparación se invierte. Mitigación: el item entra sólo si su stem está en el
  conjunto de stems permitidos (allowlist), nunca por defecto.

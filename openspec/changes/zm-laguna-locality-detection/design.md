## Context

El sistema actual determina si un candidato es local de la ZM Laguna comparando `candidate.city`
contra una lista hardcodeada de ~6 nombres canónicos (Torreón, Gómez Palacio, Lerdo, Matamoros,
Francisco I. Madero, Lerdo). Los candidatos reales usan apodos, diminutivos y nombres de ejidos
que no coinciden: "lerdito", "gomitos", "chávez", "torreoncito", "los meloneros", etc.
El resultado es que candidatos locales son clasificados como foráneos.

## Goals / Non-Goals

**Goals:**
- Construir un catálogo estructurado de los ~4 municipios ZML con sus localidades (INEGI) y alias coloquiales curados.
- Hacer que el extractor de ciudad normalice alias coloquiales al nombre canónico del municipio antes de persistir.
- Hacer que `is_local_laguna` derive correctamente de cualquier localidad del catálogo.
- Agregar los alias al seed de Neo4j para que el clasificador de intención los resuelva.

**Non-Goals:**
- No se hace geocodificación en tiempo real (sin llamadas a APIs externas de mapas).
- No se amplía la cobertura geográfica fuera de la ZML (otras ciudades siguen igual).
- No se cambia el flujo del funnel ni las preguntas que hace el bot.

## Decisions

### D1: Catálogo como archivo JSON estático en `data/`
El catálogo vive en `data/zm_laguna_localities.json`. Se carga en memoria al arrancar el worker.
No se usa Neo4j como fuente primaria del catálogo porque el grafo ya tiene una función diferente
(vocabulario de intención → ruta), y el catálogo de geo es más denso y requiere búsqueda fuzzy.

**Alternativa descartada**: Neo4j como única fuente. Requeriría cargar cientos de nodos Term
de geo solo para matching, mezclando semántica de intención con semántica de localidad.

### D2: Normalización en el extractor de ciudad, no en el clasificador de intención
El punto de normalización es `turn_extractor.py` (y su equivalente en `intent_classifier.py`),
inmediatamente después de que el LLM devuelve el valor crudo de `candidate.city`.
Si el valor crudo coincide con un alias del catálogo, se reemplaza por el nombre canónico.

**Por qué aquí**: el extractor ya tiene la responsabilidad de limpiar typos y valores crudos.
Agregar la normalización geo aquí es coherente con el principio "valor limpio antes de persistir".

### D3: Matching case-insensitive con diacríticos opcionales
La comparación usa `unicodedata.normalize` + `casefold` para que "Gomez Palacio", "gómez palacio",
"GOMEZ PALACIO" y "gomez palasio" (typo) todos resuelvan al mismo alias. Los alias del catálogo
se precomputan normalizados en memoria al cargar.

**Alternativa descartada**: fuzzy matching (Levenshtein). Agrega dependencia y falsos positivos
("lerma" ≠ "lerdo"). El catálogo curado con variantes explícitas es más predecible.

### D4: Neo4j seed recibe solo los alias más frecuentes/ambiguos
No todos los ~200+ ejidos van al seed de Neo4j (el grafo no está diseñado para eso).
Solo los alias coloquiales de los 5 municipios principales + los 10-15 ejidos más grandes/mencionados
se agregan como Terms con `intent: city_local_laguna` y `route: profile`.
El catálogo JSON es la fuente exhaustiva; Neo4j es el acelerador para los casos más comunes.

## Risks / Trade-offs

- **[Riesgo] Catálogo incompleto**: habrá ejidos que no estén. Mitigación: Capital Humano puede
  ampliar el JSON; el sistema tiene fallback al flujo actual si no hay match.
- **[Riesgo] Alias ambiguos entre regiones**: "San Pedro" existe en muchos estados.
  Mitigación: los alias del catálogo son específicos de la ZML; sin contexto de región, el LLM
  ya maneja la ambigüedad como antes.
- **[Trade-off] JSON estático vs. base de datos**: el JSON requiere redeploy para actualizarlo.
  Aceptable por ahora; el catálogo no cambia frecuentemente.

## Migration Plan

1. Crear `data/zm_laguna_localities.json` con el catálogo inicial.
2. Actualizar `turn_extractor.py` e `intent_classifier.py` para cargar y aplicar el catálogo.
3. Actualizar `app/knowledge/business_route_classifier.py` para usar el catálogo en `is_local_laguna`.
4. Agregar Terms al seed Neo4j para los alias más frecuentes.
5. Re-seedear Neo4j: `docker compose exec neo4j cypher-shell ...` (merge, no recreate).
6. Rebuild worker + api.

**Rollback**: el catálogo es aditivo; si se elimina el archivo y se revierte el código de
normalización, el sistema vuelve al comportamiento anterior sin pérdida de datos de candidatos.

## Open Questions

- ¿Incluir colonias de Torreón/Gómez Palacio/Lerdo como alias? (e.g., "el centro", "jardines")
  Probablemente no: son demasiado genéricas y no identifican municipio.
- ¿Con qué frecuencia actualizará Capital Humano el catálogo? Definir responsable.

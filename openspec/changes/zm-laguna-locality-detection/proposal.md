## Why

El sistema clasifica como "foráneo" a candidatos que son locales de la Zona Metropolitana de La Laguna (ZML) porque no reconoce variantes coloquiales de sus municipios y ejidos: "lerdito" (Lerdo), "gomitos" / "gomez paletas" (Gómez Palacio), "chávez" (Francisco I. Madero), "torreoncito" (Torreón oriente), "meloneros de matamoros" (Matamoros), entre cientos de localidades rurales. Un candidato local mal clasificado como foráneo genera trabajo manual innecesario y puede perderse.

## What Changes

- **Catálogo de localidades ZML**: nuevo archivo de datos con los municipios oficiales de la ZML (Torreón, Gómez Palacio, Lerdo, Matamoros / Francisco I. Madero) y todas sus localidades, ejidos y rancherías, más alias coloquiales curados.
- **Actualización del seed Neo4j**: los alias coloquiales de ciudades locales se agregan como términos al grafo de conocimiento para que el clasificador de intención los normalice.
- **Lógica de geo-inferencia en extracción**: cuando `candidate.city` contiene un alias coloquial conocido, el extractor lo normaliza al nombre canónico y `location.is_local_laguna` se deriva correctamente.
- **Documentación de la cobertura**: lista curada de alias incluidos para que Capital Humano pueda auditarla y ampliarla.

## Capabilities

### New Capabilities

- `zm-laguna-locality-catalog`: Catálogo estructurado de municipios, ejidos y alias coloquiales de la ZML que alimenta Neo4j y la lógica de inferencia local/foráneo.

### Modified Capabilities

- `city-extraction`: la extracción de `candidate.city` ahora normaliza alias coloquiales ZML al nombre canónico antes de persistir.
- `recruiting-business-route-classification`: la derivación de `location.is_local_laguna` se apoya en el catálogo ampliado, no solo en coincidencias de texto exactas.

## Impact

- `app/knowledge/neo4j_seed_hr_rules.cypher` — nuevos Terms para alias coloquiales ZML
- `app/knowledge/turn_extractor.py` — regla de normalización de ciudad vía catálogo
- `app/knowledge/intent_classifier.py` — ejemplos de alias coloquiales reconocidos
- `data/zm_laguna_localities.json` (nuevo) — catálogo canónico de localidades ZML
- `app/knowledge/business_route_classifier.py` — posiblemente ajustar si la derivación `is_local_laguna` cambia
- Neo4j: requiere re-seed o merge de los nuevos nodos Term

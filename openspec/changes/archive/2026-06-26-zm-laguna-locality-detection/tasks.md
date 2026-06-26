## 1. Catálogo de localidades ZML

- [x] 1.1 Crear `data/zm_laguna_localities.json` con los 4 municipios canónicos (Torreón, Gómez Palacio, Lerdo, Matamoros/Francisco I. Madero) y sus alias coloquiales principales (lerdito, gomitos, gomez paletas, chávez, torreoncito, etc.)
- [x] 1.2 Ampliar el catálogo con ejidos y localidades rurales relevantes de cada municipio (meloneros de matamoros, lucio blanco, san pedro de las colonias, etc.) consultando fuentes INEGI/DENUE
- [x] 1.3 Documentar en el JSON el criterio de inclusión y el responsable de mantenimiento

## 2. Utilidad de normalización

- [x] 2.1 Crear `app/knowledge/geo_utils.py` con la función `normalize_zm_laguna_city(raw: str) -> str` que carga el catálogo una vez al importar y aplica matching case-insensitive sin diacríticos
- [x] 2.2 Agregar función auxiliar `is_zm_laguna_canonical(city: str) -> bool` que verifica si el nombre canónico está en el catálogo

## 3. Integración en extracción

- [x] 3.1 En `app/knowledge/turn_extractor.py`, aplicar `normalize_zm_laguna_city` al valor de `candidate.city` antes de devolverlo en el JSON de extracción
- [x] 3.2 En `app/knowledge/intent_classifier.py`, aplicar la misma normalización al campo `candidate.city` de los answers extraídos
- [x] 3.3 Agregar ejemplo en el prompt del `intent_classifier.py` con un alias coloquial ZML ("lerdito" → "Lerdo")

## 4. Derivación is_local_laguna desde catálogo

- [x] 4.1 En `app/knowledge/business_route_classifier.py` (o donde se derive `is_local_laguna`), reemplazar la lista hardcodeada por una consulta a `is_zm_laguna_canonical(city)` del catálogo

## 5. Seed Neo4j

- [x] 5.1 Agregar en `app/knowledge/neo4j_seed_hr_rules.cypher` Terms para los alias coloquiales más frecuentes de los 5 municipios (lerdito, gomitos, gomez paletas, chávez, torreoncito, lerdo) con `intent: city_local_laguna`, `route: profile`, `source: city_catalog`
- [x] 5.2 Re-seedear Neo4j: `docker compose exec neo4j cypher-shell -u neo4j -p neo4j_password` con el nuevo seed (merge, no drop)

## 6. Build y prueba

- [x] 6.1 Rebuild worker y api: `docker compose build worker api && docker compose up -d worker api`
- [x] 6.2 Enviar mensaje de prueba con "soy de lerdito" y verificar en logs que `candidate.city = "Lerdo"` y `is_local_laguna = true`
- [x] 6.3 Verificar que "soy de Matehuala" sigue dando `is_local_laguna = false`

# zm-laguna-locality-catalog Specification

## Purpose
TBD - created by archiving change zm-laguna-locality-detection. Update Purpose after archive.
## Requirements
### Requirement: Catálogo estructurado de localidades de la ZM Laguna

El sistema SHALL mantener un archivo `data/zm_laguna_localities.json` con la estructura canónica
de municipios, localidades y alias coloquiales de la Zona Metropolitana de La Laguna (ZML).
El catálogo SHALL cubrir como mínimo los municipios de Torreón (Coahuila), Gómez Palacio (Durango),
Lerdo (Durango) y Matamoros/Francisco I. Madero (Coahuila).
Cada entrada SHALL tener: `canonical` (nombre oficial), `state`, `aliases` (lista de variantes
coloquiales, diminutivos, abreviaturas y nombres de ejidos asociados).
El catálogo SHALL cargarse en memoria al iniciar el worker; no se requieren llamadas externas.

#### Scenario: Alias coloquial de municipio principal resuelve a canónico

- **WHEN** `candidate.city` crudo es "lerdito", "gomitos", "gomez paletas", "chávez" o "torreoncito"
- **THEN** la función de normalización devuelve el nombre canónico correspondiente
  ("Lerdo", "Gómez Palacio", "Gómez Palacio", "Francisco I. Madero", "Torreón")

#### Scenario: Nombre de ejido o ranchería ZML resuelve a municipio anfitrión

- **WHEN** `candidate.city` crudo es el nombre de un ejido listado en el catálogo
  (e.g., "san pedro de las colonias", "meloneros de matamoros", "lucio blanco")
- **THEN** la función devuelve el municipio canónico al que pertenece ese ejido

#### Scenario: Ciudad fuera del catálogo no se modifica

- **WHEN** `candidate.city` crudo es una ciudad no listada (e.g., "Matehuala", "Durango")
- **THEN** la función devuelve el valor sin cambios

#### Scenario: Matching es case-insensitive y tolera ausencia de diacríticos

- **WHEN** el valor crudo es "Gomez Palacio", "GÓMEZ PALACIO" o "gomez palasio" (typo)
- **THEN** todos resuelven al alias "Gómez Palacio" y por ende al canónico correcto

### Requirement: Función de normalización de localidad ZML disponible como utilidad compartida

El sistema SHALL exponer una función `normalize_zm_laguna_city(raw: str) -> str` en un módulo
utilitario (e.g., `app/knowledge/geo_utils.py`) que reciba el valor crudo de ciudad y devuelva
el nombre canónico si hay match en el catálogo, o el valor original si no hay match.
La función SHALL precomputar el índice de búsqueda al importar el módulo (no en cada llamada).

#### Scenario: Primer llamado y llamados subsiguientes son igualmente rápidos

- **WHEN** `normalize_zm_laguna_city` se llama por primera vez y luego múltiples veces
- **THEN** el índice ya está precargado; no hay I/O en ninguno de los llamados


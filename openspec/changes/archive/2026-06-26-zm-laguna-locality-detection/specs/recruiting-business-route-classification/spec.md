## ADDED Requirements

### Requirement: is_local_laguna deriva del catálogo ZML, no de lista hardcodeada

El sistema SHALL derivar `location.is_local_laguna = true` cuando `candidate.city` (ya normalizado)
coincide con cualquier municipio canónico del catálogo ZML.
La comparación SHALL ser case-insensitive.
La lista de municipios válidos SHALL provenir del catálogo (`data/zm_laguna_localities.json`),
no de una lista hardcodeada en el código.

#### Scenario: Municipio canónico ZML → is_local_laguna = true

- **WHEN** `candidate.city` es "Torreón", "Gómez Palacio", "Lerdo", "Matamoros" o "Francisco I. Madero"
- **THEN** `location.is_local_laguna = true`

#### Scenario: Alias coloquial normalizado → is_local_laguna = true

- **WHEN** el candidato dijo "gomitos" y fue normalizado a "Gómez Palacio"
- **THEN** `location.is_local_laguna = true` (porque "Gómez Palacio" está en el catálogo)

#### Scenario: Ciudad foránea → is_local_laguna = false

- **WHEN** `candidate.city` es "Matehuala", "Monterrey" o cualquier ciudad fuera del catálogo ZML
- **THEN** `location.is_local_laguna = false`

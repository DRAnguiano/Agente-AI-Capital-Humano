## ADDED Requirements

### Requirement: Normalización de alias coloquiales ZML en la extracción de ciudad

El sistema SHALL aplicar `normalize_zm_laguna_city` al valor crudo de `candidate.city` antes de persistirlo,
tanto en `turn_extractor.py` como en `intent_classifier.py`. Si el valor crudo es un alias coloquial
del catálogo ZML, SHALL almacenarse el nombre canónico, no el alias.

#### Scenario: "lerdito" se almacena como "Lerdo"

- **WHEN** el candidato dice "soy de lerdito" y el LLM extrae `candidate.city = "lerdito"`
- **THEN** `normalize_zm_laguna_city("lerdito")` devuelve "Lerdo"
- **AND** el fact persistido es `candidate.city = "Lerdo"`

#### Scenario: "gomez paletas" se almacena como "Gómez Palacio"

- **WHEN** el candidato dice "vivo en gomez paletas"
- **THEN** el fact persistido es `candidate.city = "Gómez Palacio"`

#### Scenario: Ciudad foránea no se altera

- **WHEN** el candidato dice "soy de Monterrey"
- **THEN** `normalize_zm_laguna_city("Monterrey")` devuelve "Monterrey" sin cambios
- **AND** el fact persistido es `candidate.city = "Monterrey"`

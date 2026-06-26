# city-extraction Specification

## Purpose
TBD - created by archiving change regex-audit-llm-migration. Update Purpose after archive.
## Requirements
### Requirement: city-extraction LLM-first con marcador de residencia

Cuando el mensaje contiene un marcador de residencia, el sistema SHALL usar LLM T=0 como fuente primaria para `candidate.city`.
El catálogo MUST usarse solo como fallback si el LLM falla con excepción.
Los marcadores reconocidos MUST incluir: `"soy de"`, `"soy d "`, `"soi de"`, `"soi d "`, `"vivo en"`, `"vivo n "`, `"radico en"`, `"resido en"`, `"estoy en"`.
Esta lista SHALL estar sincronizada en `profile_extractor.py` y `knowledge_orchestrator.py`.
El prompt `_CITY_FALLBACK_SYSTEM` MUST instruir: extraer SOLO la ciudad inmediatamente después del marcador, no ciudades de destino.
Sin marcador de residencia, el sistema SHALL usar el catálogo directamente sin LLM call.

#### Scenario: Ciudad con typo anclada al marcador

**Given** el candidato envía "soy d gomez palasio, que rutas ay y dan voleto pa ir a torreon"
**When** se extrae el perfil con `extract_profile_facts_as_dict`
**Then** `candidate.city` = "Gómez Palacio" (residencia, no destino)

#### Scenario: Respuesta directa sin marcador usa catálogo

**Given** el candidato envía "torreon"
**When** se extrae la ciudad
**Then** `candidate.city` = "Torreón" (catálogo, sin LLM call)

#### Scenario: Neo4j geo sin marcador no se descarta

**Given** Neo4j extrae ciudad "Torreón" desde el mensaje "torreon"
**And** el mensaje no contiene marcador de residencia
**When** se aplica `_drop_unanchored_neo4j_geo`
**Then** el fact de ciudad se conserva

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


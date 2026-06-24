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


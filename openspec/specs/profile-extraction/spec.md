# profile-extraction Specification

## Purpose

Extraer los datos de perfil del candidato a partir de sus mensajes, con una sola fuente
por tipo de dato y una prioridad clara de fuentes de verdad. Neo4j resuelve geografía y
tipo de vehículo; `app/lead_memory/profile_extractor.py` resuelve por regex licencia,
apto médico, experiencia, documentos y edad. Los facts resultantes alimentan
`rh_lead_facts_v2`.

> Nota: el extractor por **regex** es la implementación **baseline actual (deuda técnica)**.
> Sus reglas de negocio se auditarán y migrarán a catálogos/grafo/planners declarativos
> (ver `multi-intent-migration` §13 — auditoría de regex/if de negocio).

## Requirements

### Requirement: Extractor único por tipo de dato

El sistema SHALL extraer ciudad, estado y tipo de vehículo desde nodos `GeoArea` /
`VehicleType` de Neo4j, y licencia, apto médico, experiencia, documentos y edad desde el
extractor regex. No SHALL existir lógica de extracción duplicada fuera de estas dos
fuentes; `current_turn.extract_current_turn_facts` es un wrapper delgado sobre el
extractor regex.

#### Scenario: Ciudad/vehículo
- **WHEN** el mensaje contiene una ciudad o tipo de vehículo reconocible
- **THEN** el fact se resuelve vía Neo4j (con sus aliases y confidence), no por regex ad-hoc

#### Scenario: Licencia/apto/experiencia/documentos/edad
- **WHEN** el mensaje contiene uno de esos datos
- **THEN** el fact se extrae con el extractor regex único y se normaliza a su clave canónica

### Requirement: Prioridad de fuentes de verdad

Al determinar un fact, el sistema SHALL respetar la prioridad: turno actual > lead_memory
> Neo4j > RAG/ChromaDB > generación LLM. El RAG NUNCA SHALL decidir un fact de perfil del
candidato.

#### Scenario: Conflicto entre turno actual y memoria previa
- **WHEN** el dato afirmado en el turno actual contradice un fact previo
- **THEN** prevalece el dato del turno actual

#### Scenario: RAG no fija facts
- **WHEN** una respuesta RAG menciona datos del candidato
- **THEN** esos datos no se persisten como facts; el RAG solo responde políticas/HR

### Requirement: Merge y persistencia de facts

Los facts de Neo4j y del extractor regex SHALL fusionarse en
`_store_lead_memory_updates` y persistirse en `rh_lead_facts_v2` como pares
`fact_group.fact_key = value`, marcando los facts activos del lead.

#### Scenario: Facts extraídos en un turno
- **WHEN** un turno produce facts desde Neo4j y/o regex
- **THEN** se fusionan y se escriben en `rh_lead_facts_v2`, quedando disponibles para el funnel y el status del lead

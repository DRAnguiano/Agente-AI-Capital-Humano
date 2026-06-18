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

### Requirement: La edad no se infiere de años de experiencia

El extractor de perfil SHALL NOT inferir `candidate.age` a partir de expresiones de
experiencia o antigüedad ("20 años de fullero", "llevo 20 años manejando"). La edad SHALL
extraerse solo ante una señal explícita de edad (p. ej. "tengo 35 años de edad").

> Nota de implementación: requirement doc-only; el ajuste del regex de edad en
> `profile_extractor.py` queda para una fase posterior.

#### Scenario: Años de experiencia no producen edad
- **WHEN** el candidato dice "llevo más de 20 años de fullero"
- **THEN** el extractor puede registrar experiencia (`experience.years`)
- **AND** no registra `candidate.age`

#### Scenario: Edad explícita sí se registra
- **WHEN** el candidato dice "tengo 35 años de edad"
- **THEN** el extractor registra `candidate.age=35`

### Requirement: Dominio de unidad — sencillo, full, torton/rabón/reparto y escuelita

El sistema SHALL tratar `sencillo` (camión rígido de dos ejes / vehículo de carga mediano)
como experiencia/vacante válida y SHALL NOT convertirlo en `escuelita`. El sistema SHALL
tratar `full` (tractocamión con doble remolque unido mediante convertidor/dolly) como
experiencia objetivo para la vacante full. `torton`, `rabón`, reparto local y servicio
interurbano son experiencias en unidades de carga que pueden derivar a valoración
`escuelita`/CECATI; el sistema SHALL NOT confirmarlas como experiencia `full`, SHALL NOT
describirlas como "transferencia hacia quinta rueda" y SHALL NOT tratarlas como `sencillo`.
Estas categorías SHALL mantenerse distintas entre sí, según
`docs/esquema_perfilamiento_v1.md` (§3) y `data/02_documentos_requisitos.md`.

> Nota de implementación: requirement doc-only; alinea el camino vivo
> (`current_turn.py`, `chatwoot_note_sync.py`) a la fuente de verdad.

#### Scenario: "manejo sencillo" → sencillo, no escuelita
- **WHEN** el candidato dice "manejo sencillo"
- **THEN** el sistema registra `experience.vehicle_type=sencillo`
- **AND** no aplica `escuelita`

#### Scenario: "manejo full" → full
- **WHEN** el candidato dice "manejo full"
- **THEN** el sistema registra `experience.vehicle_type=full`

#### Scenario: "manejo torton" → puede derivar a escuelita/CECATI, no full
- **WHEN** el candidato dice "manejo torton"
- **THEN** el sistema puede derivar a valoración `escuelita`/CECATI
- **AND** no confirma `full` ni lo describe como "transferencia hacia quinta rueda"

#### Scenario: "rabón y reparto local" → puede derivar a escuelita/CECATI, no full ni sencillo
- **WHEN** el candidato dice "manejo rabón y reparto local"
- **THEN** el sistema puede derivar a valoración `escuelita`/CECATI
- **AND** no confirma `full` ni `sencillo` salvo que el candidato diga explícitamente "sencillo"

#### Scenario: Corrección "no quiero escuelita, manejo sencillo"
- **WHEN** el candidato dice "no quiero escuelita, manejo sencillo"
- **THEN** el sistema reconoce la corrección y registra `experience.vehicle_type=sencillo`
- **AND** no mantiene ni repite `escuelita`

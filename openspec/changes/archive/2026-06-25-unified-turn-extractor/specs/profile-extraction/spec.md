## MODIFIED Requirements

### Requirement: Extractor único por tipo de dato

El sistema SHALL extraer el lenguaje natural del candidato mediante el **extractor unificado
de turno** (una sola pasada LLM), y SHALL validar/normalizar los conceptos resultantes contra
catálogos deterministas: ciudad y tipo de vehículo contra Neo4j / `domain_catalog`, edad
contra rango plausible, licencia contra el catálogo A/B/E. SHALL NOT existir extracción de
texto natural por-campo gateada por regex (los `_SYSTEM` por campo y los gates `if <hint> in
last_bot` se eliminan). El regex/catálogo se conserva únicamente como **validador** sobre el
JSON ya estructurado, nunca como extractor.

#### Scenario: Ciudad/vehículo validados por catálogo
- **WHEN** el extractor unificado reporta una ciudad o tipo de vehículo
- **THEN** el concepto se valida/normaliza vía Neo4j / `domain_catalog` (con sus aliases y semántica de negocio), no por regex ad-hoc de extracción

#### Scenario: Licencia/apto/experiencia/edad extraídos en una pasada
- **WHEN** el mensaje contiene uno o varios de esos datos
- **THEN** se extraen en la única pasada del extractor unificado y se normalizan a sus claves canónicas, sin extractores por-campo separados

#### Scenario: Validador determinista descarta valor fuera de rango
- **WHEN** el extractor reporta una edad fuera del rango plausible (p. ej. derivada de una cifra monetaria)
- **THEN** la capa de validación la descarta y no se persiste como `candidate.age`

### Requirement: Merge y persistencia de facts

Los facts validados del extractor unificado SHALL fusionarse y persistirse en
`rh_lead_facts_v2` como pares `fact_group.fact_key = value` con su confianza derivada,
mediante un **único escritor por turno**. SHALL NOT haber dos rutas de escritura (orquestador
y guard) compitiendo sobre el mismo turno.

#### Scenario: Facts de un turno escritos una sola vez
- **WHEN** un turno produce facts validados
- **THEN** se escriben en `rh_lead_facts_v2` por un único escritor, quedando disponibles para el funnel y el status del lead

#### Scenario: Campo de texto libre sin anclaje no se persiste
- **WHEN** el extractor reporta un campo de texto libre (p. ej. `candidate.name`) sin `explicit_marker` y sin `answered_direct_question`
- **THEN** el valor no se persiste (evita registrar ruido como un saludo en lugar de un nombre)

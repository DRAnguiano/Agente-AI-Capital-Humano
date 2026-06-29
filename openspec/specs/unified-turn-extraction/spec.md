# unified-turn-extraction Specification

## Purpose
TBD - created by archiving change unified-turn-extractor. Update Purpose after archive.
## Requirements
### Requirement: Extracción unificada del turno en una sola pasada

El sistema SHALL extraer todos los datos del candidato de un turno mediante una **única**
pasada LLM que recibe el mensaje, la última pregunta del bot y los facts ya conocidos, y
devuelve un objeto `TurnExtraction` estructurado con: los campos del perfil (cada uno con su
evidencia), la pregunta embebida (si la hay) y las señales de turno. SHALL NOT existir
extracción de texto natural por-campo gateada por regex repartida en varios módulos.

#### Scenario: Mensaje con varios datos a la vez
- **WHEN** el candidato escribe "me llamo Juan, soy de Gómez, manejo full hace 10 años y mi licencia E vence en 2 años"
- **THEN** una sola pasada devuelve `candidate.name`, `candidate.city`, `experience.vehicle_type`, `experience.years=10 años` y `license.expiration_text=2 años` sin que los campos se pisen entre sí

#### Scenario: Dato y pregunta en el mismo mensaje
- **WHEN** el candidato escribe "ramon, ¿a cómo pagan el km?"
- **THEN** la extracción devuelve `candidate.name=Ramon` y `embedded_question` con la duda de pago

#### Scenario: Referencia resuelta con facts conocidos
- **WHEN** el bot preguntó el vencimiento del apto y el candidato responde "igual que mi licencia"
- **AND** `license.expiration_text` ya es un fact conocido
- **THEN** la extracción resuelve `medical.apto_expiration_text` al mismo valor de la licencia

### Requirement: El LLM reporta evidencia, no confianza

La capa LLM SHALL devolver por campo el valor crudo y señales de evidencia observables
(`explicit_marker`, `answered_direct_question`), y SHALL NOT devolver un score numérico de
confianza. La confianza SHALL computarse determinísticamente en código a partir de esa
evidencia y del resultado de la validación de catálogo.

#### Scenario: Marcador explícito reportado
- **WHEN** el candidato dice "me llamo Ramón"
- **THEN** el campo `candidate.name` se reporta con `explicit_marker = true`

#### Scenario: Valor sin marcador en respuesta a pregunta directa
- **WHEN** el bot preguntó la edad y el candidato responde "30"
- **THEN** `candidate.age` se reporta con `answered_direct_question = true` y `explicit_marker = false`

### Requirement: Capas de validación y política deterministas

La extracción SHALL separarse en tres capas: (1) LLM lenguaje→concepto, (2) validación
determinista contra catálogo cerrado (Neo4j para ciudad, `domain_catalog` para unidad, rango
de edad, catálogo A/B/E para licencia), (3) política de negocio en código. La política de
negocio (inferencia licencia→vacante, clasificación de unidad objetivo/escuelita, documento
por residencia) SHALL NOT residir en el prompt del LLM.

La capa de validación (`validate_extraction`) SHALL surface no solo los campos de
`extraction.fields`, sino también las señales del turno que representan facts del candidato.
En particular, cuando la extracción trae `signals.renewal_proof` con valor `"si"` o `"no"`,
`validate_extraction` SHALL emitir un fact canónico `documents.renewal_proof` con ese valor,
para que el path activo (current-turn guard y persistencia) lo registre. SHALL NOT descartar
silenciosamente esa señal.

#### Scenario: Unidad no-objetivo clasificada por catálogo, no por LLM
- **WHEN** el candidato menciona "torton"
- **THEN** el LLM reporta el término crudo y la capa determinista lo mapea a NON_TARGET (escuelita), sin que el LLM decida el estatus de negocio

#### Scenario: Ciudad validada contra catálogo
- **WHEN** el LLM extrae una ciudad de residencia
- **THEN** la capa determinista la valida/normaliza contra Neo4j; si no hay match, queda como texto crudo de baja confianza y no se afirma como ciudad canónica

#### Scenario: Señal de comprobante de renovación se surfacea como fact
- **WHEN** la extracción del turno trae `signals.renewal_proof = "si"` (candidato dijo "ya tengo
  el comprobante de renovación")
- **THEN** `validate_extraction` emite un fact `documents.renewal_proof = "si"`
- **AND** ese fact fluye al current-turn guard y se persiste, evitando que el funnel re-pregunte

#### Scenario: Señal de renovación ausente no inventa fact
- **WHEN** la extracción del turno trae `signals.renewal_proof = null`
- **THEN** `validate_extraction` no emite ningún fact `documents.renewal_proof`

### Requirement: Degradación segura sin regex-adivinanza

Si la pasada LLM falla o el JSON no parsea, el sistema SHALL degradar a "sin extracción en
este turno" (el funnel re-pregunta el campo pendiente) y SHALL NOT recurrir a extracción por
regex de texto natural como respaldo.

#### Scenario: JSON inválido del extractor
- **WHEN** la respuesta del LLM no parsea como JSON válido
- **THEN** el turno no produce facts nuevos y el funnel continúa con su pregunta pendiente, sin inventar valores


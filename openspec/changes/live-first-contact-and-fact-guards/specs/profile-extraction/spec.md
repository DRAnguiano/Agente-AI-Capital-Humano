# profile-extraction (delta)

## ADDED Requirements

### Requirement: Geo no se extrae de preguntas sin marcador de residencia

El sistema NO SHALL persistir `candidate.city` ni `candidate.state` desde un
mensaje que es una pregunta, salvo que contenga un marcador de residencia en
primera persona ("soy de", "vivo en", "radico en", "resido en", "estoy en").
Aplica a ambos extractores del camino vivo (alias GeoArea de Neo4j y regex de
`profile_extractor`).

#### Scenario: Pregunta de rutas no fija ciudad
- **WHEN** el candidato pregunta "¿qué rutas maneja para nuevo laredo?"
- **THEN** no se persiste `candidate.city` y no se emiten labels `foraneo`/`validar_traslado`

#### Scenario: Pregunta con marcador de residencia sí fija ciudad
- **WHEN** el candidato escribe "soy de laredo, ¿a dónde salen las corridas?"
- **THEN** se persiste `candidate.city` con el valor acotado ("Laredo")

### Requirement: Captura de ciudad acotada

La extracción de ciudad por regex SHALL acotar la captura: corta en conectores e
interrogativos (y, con, a, ahí, donde, que, para, pero, como, cuando, tengo,
licencia, apto, cartas) y limita el valor a un máximo de 4 tokens.

#### Scenario: Ciudad seguida de pregunta no se traga la frase
- **WHEN** el candidato escribe "soy de Laredo ahí de donde a donde me toca ir?"
- **THEN** `candidate.city` capturada es "Laredo", no la frase completa

#### Scenario: Ciudades multi-palabra siguen funcionando
- **WHEN** el candidato escribe "vivo en san luis potosi"
- **THEN** `candidate.city` capturada es "San Luis Potosí" (o el alias canónico del catálogo)

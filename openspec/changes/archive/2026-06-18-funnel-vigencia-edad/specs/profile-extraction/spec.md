# profile-extraction (delta)

## ADDED Requirements

### Requirement: Captura de vencimientos en fecha o tiempo relativo

El extractor SHALL capturar el vencimiento de licencia y apto médico expresado
como fecha ("31 de diciembre de 2027", "12/2027") o tiempo relativo ("en 2
años", "como en 6 meses", "el año que entra"), persistiendo
`license.expiration_text` / `medical.apto_expiration_text` y, cuando sea
interpretable, una fecha normalizada. Sin fecha clara NO SHALL inferirse
vigencia suficiente (límite 2B.1).

#### Scenario: Fecha explícita
- **WHEN** el candidato dice "mi licencia vence el 31 de diciembre de 2027"
- **THEN** se persiste `license.expiration_text="31 de diciembre de 2027"`

#### Scenario: Tiempo relativo
- **WHEN** el candidato dice "el apto se me vence como en dos meses"
- **THEN** se persiste `medical.apto_expiration_text` y el planner detecta vencimiento <3 meses

### Requirement: Edad como dato temprano del perfil

El extractor SHALL capturar `candidate.age` desde respuestas a la pregunta de
edad y el planner SHALL evaluar el descalificador (50 años o más) en cuanto
exista el dato.

#### Scenario: Edad declarada
- **WHEN** el candidato responde "tengo 45" tras la pregunta de edad
- **THEN** se persiste `candidate.age=45` y el funnel continúa

#### Scenario: Edad descalificante también se persiste
- **WHEN** el candidato responde "tengo 52" tras la pregunta de edad
- **THEN** se persiste `candidate.age=52` y el planner dispara el descarte

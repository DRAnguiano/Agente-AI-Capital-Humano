## ADDED Requirements

### Requirement: Fact de experiencia en unidad no-objetivo

El sistema SHALL persistir el fact canónico `experience.non_target_vehicle_type` cuando el
candidato declare con evidencia literal experiencia manejando una unidad **no objetivo**
(torton, rabón, reparto local, interurbano/urbano), normalizando el valor al término
canónico. SHALL NOT inferirlo sin evidencia en el mensaje, y SHALL NOT sobrescribir un
`experience.vehicle_type` ya confirmado como `full` o `sencillo`.

#### Scenario: Candidato con experiencia en torton
- **WHEN** el candidato dice que su experiencia es manejando torton o rabón
- **THEN** el sistema persiste `experience.non_target_vehicle_type` con el término normalizado
- **AND** no marca `experience.vehicle_type` como full ni sencillo

#### Scenario: Sin evidencia no se infiere
- **WHEN** el mensaje no menciona una unidad no objetivo
- **THEN** el sistema no escribe `experience.non_target_vehicle_type`

### Requirement: Fact de ausencia de experiencia en carretera

El sistema SHALL persistir una señal canónica de **ausencia de experiencia en carretera**
(p. ej. `experience.road_experience = "none"`) cuando el candidato declare que no tiene
experiencia manejando tractocamión/carretera o que desea aprender a manejar. Esta señal es
la fuente determinista de la orientación a CECATI; SHALL requerir evidencia literal.

#### Scenario: Candidato sin experiencia que quiere aprender
- **WHEN** el candidato dice que no ha manejado tracto/carretera o que quiere aprender
- **THEN** el sistema persiste la señal de ausencia de experiencia en carretera

#### Scenario: Candidato con experiencia declarada no dispara la señal
- **WHEN** el candidato declara años de experiencia o una unidad manejada
- **THEN** el sistema no persiste la señal de ausencia de experiencia en carretera

### Requirement: Fact de intención B1 / Estados Unidos

El sistema SHALL persistir un fact canónico de intención B1/EUA (p. ej.
`experience.b1_us_intent = true`) cuando el candidato mencione con evidencia literal licencia
B1, cruce a Estados Unidos, o rutas a EUA. Es la fuente determinista de la canalización a
operador B1.

#### Scenario: Mención de B1 o cruce a EUA
- **WHEN** el candidato menciona licencia B1, EUA/USA/EEUU o cruzar a Estados Unidos
- **THEN** el sistema persiste el fact de intención B1/EUA

### Requirement: Fact de reingreso

El sistema SHALL persistir un fact canónico de reingreso (p. ej. `candidate.reingreso = true`)
cuando el candidato declare con evidencia literal que ya trabajó antes en Transmontes y desea
reingresar. Es la fuente determinista de `reingreso_verificar`.

#### Scenario: Candidato declara reingreso
- **WHEN** el candidato dice que ya trabajó en Transmontes y quiere regresar
- **THEN** el sistema persiste el fact de reingreso

### Requirement: Unidad ambigua no confirma vehicle_type y marca aclaración

El sistema SHALL NOT escribir `experience.vehicle_type` como `full` o `sencillo` cuando el
candidato use un término de unidad **ambiguo** (camión, tráiler, caja seca, quinta rueda,
tractocamión sin precisar) y SHALL persistir una señal canónica de aclaración pendiente de
unidad (p. ej. `experience.vehicle_type_pending = true`), fuente determinista de
`aclaracion_pendiente`.

#### Scenario: Término de unidad ambiguo
- **WHEN** el candidato menciona "tráiler" o "quinta rueda" sin precisar full/sencillo
- **THEN** el sistema no confirma `experience.vehicle_type`
- **AND** persiste la señal de aclaración pendiente de unidad

#### Scenario: Unidad explícita no marca aclaración
- **WHEN** el candidato dice explícitamente "full" o "sencillo"
- **THEN** el sistema confirma `experience.vehicle_type` y no marca aclaración pendiente

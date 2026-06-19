## ADDED Requirements

### Requirement: Emisión determinista de la tricotomía de experiencia-objetivo

El sistema SHALL emitir exactamente una de las labels de experiencia-objetivo a partir de
facts en Postgres, nunca del tono del LLM, y SHALL respetar su exclusividad mutua:
- `objetivo_full_sencillo` cuando `experience.vehicle_type` esté confirmado como `full` o
  `sencillo`;
- `considerar_escuelita_transmontes` cuando exista `experience.non_target_vehicle_type`
  (torton/rabón/reparto local/interurbano) y NO haya unidad objetivo confirmada;
- `cecati_sugerido` cuando exista la señal de ausencia de experiencia en carretera y NO haya
  unidad objetivo ni experiencia no-objetivo.

SHALL NOT emitir dos de estas tres labels simultáneamente. SHALL NOT emitir las deprecadas
`cecati` ni `escuelita`.

#### Scenario: Unidad objetivo confirmada
- **WHEN** `experience.vehicle_type` es `full` o `sencillo`
- **THEN** se emite `objetivo_full_sencillo`
- **AND** no se emite `cecati_sugerido` ni `considerar_escuelita_transmontes`

#### Scenario: Experiencia en unidad no-objetivo
- **WHEN** existe `experience.non_target_vehicle_type` y no hay unidad objetivo confirmada
- **THEN** se emite `considerar_escuelita_transmontes`
- **AND** no se emite `objetivo_full_sencillo` ni `cecati_sugerido`

#### Scenario: Sin experiencia en carretera
- **WHEN** existe la señal de ausencia de experiencia en carretera y no hay unidad objetivo ni experiencia no-objetivo
- **THEN** se emite `cecati_sugerido`
- **AND** no se emite `objetivo_full_sencillo` ni `considerar_escuelita_transmontes`

#### Scenario: Sin señal de experiencia no emite tricotomía
- **WHEN** no hay unidad confirmada, ni experiencia no-objetivo, ni señal de ausencia de experiencia
- **THEN** no se emite ninguna de las tres labels de experiencia-objetivo

### Requirement: Emisión de aclaracion_pendiente por unidad sin confirmar

El sistema SHALL emitir `aclaracion_pendiente` cuando exista la señal de aclaración pendiente
de unidad (candidato usó un término ambiguo: tráiler, quinta rueda, caja seca, camión sin
precisar) y `experience.vehicle_type` no esté confirmado. La label SHALL retirarse cuando el
candidato confirme `full` o `sencillo`.

#### Scenario: Unidad ambigua sin confirmar
- **WHEN** existe la señal de aclaración pendiente de unidad y `experience.vehicle_type` no está confirmado
- **THEN** se emite `aclaracion_pendiente`

#### Scenario: Aclaración resuelta al confirmar unidad
- **WHEN** el candidato confirma `experience.vehicle_type` como `full` o `sencillo`
- **THEN** no se emite `aclaracion_pendiente`

## ADDED Requirements

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

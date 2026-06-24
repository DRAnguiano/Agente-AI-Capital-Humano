## ADDED Requirements

### Requirement: Verificación de licencia antes de handoff escuelita/CECATI

Antes de canalizar a Capital Humano por rama escuelita o CECATI, el sistema SHALL verificar que el candidato tiene licencia federal vigente (tipo B o E) o comprobante de cita de renovación. Si no tiene ninguno, el sistema SHALL cerrar el perfilamiento con un mensaje informativo y NO emitir handoff.

#### Scenario: Candidato escuelita con licencia vigente → handoff

- **WHEN** el bot detecta señal `considerar_escuelita_transmontes` o `cecati_sugerido`
- **AND** `license.category` está en {B, E} Y `license.expiration_text` indica vigencia > 3 meses o `license.tramite_comprobante = true`
- **THEN** el sistema emite handoff con `requires_human=True` incluyendo en el acuse el tipo de licencia

#### Scenario: Candidato escuelita sin licencia → pregunta verificación

- **WHEN** el bot detecta señal escuelita o CECATI
- **AND** `license.category` no está en facts o `license.expiration_text` no está en facts
- **THEN** el sistema pregunta: "Para considerarlo, necesitamos que cuente con licencia federal tipo B o E vigente. ¿Tiene licencia federal?"

#### Scenario: Candidato escuelita confirma no tener licencia → cierre informativo

- **WHEN** la verificación ya se hizo (turno previo preguntó licencia)
- **AND** el candidato responde negativamente o indica que no tiene licencia
- **THEN** el sistema responde indicando que sin licencia vigente no es posible continuar el proceso por ahora, y cierra sin emitir handoff

### Requirement: Verificación de unidad y documentos antes de handoff B1

Antes de canalizar por rama B1/US, el sistema SHALL verificar que el candidato ha declarado tipo de unidad (full o sencillo), licencia vigente y apto vigente.

#### Scenario: B1 con datos completos → handoff enriquecido

- **WHEN** el bot detecta señal `business_route_us`
- **AND** `experience.vehicle_type`, `license.category`, `license.expiration_text` y `medical.apto_expiration_text` están en facts
- **THEN** el sistema emite handoff incluyendo en el acuse el tipo de unidad y licencia

#### Scenario: B1 con datos incompletos → pregunta verificación

- **WHEN** el bot detecta señal `business_route_us`
- **AND** alguno de los campos anteriores no está en facts
- **THEN** el sistema pregunta por el primer campo faltante antes de canalizar

### Requirement: Verificación de tipo de vacante antes de handoff reingreso

Antes de canalizar por rama reingreso, el sistema SHALL verificar si el candidato busca vacante de operador u otro tipo de vacante.

#### Scenario: Reingreso operador → verificar licencia y apto antes de handoff

- **WHEN** el bot detecta señal `reingreso_verificar`
- **AND** el candidato confirma que busca vacante de operador
- **AND** `license.category`, `license.expiration_text` y `medical.apto_expiration_text` están en facts
- **THEN** el sistema emite handoff incluyendo ciudad, licencia, apto y tipo de unidad

#### Scenario: Reingreso otro tipo de vacante → handoff directo

- **WHEN** el bot detecta señal `reingreso_verificar`
- **AND** el candidato indica que busca otro tipo de vacante (no operador)
- **THEN** el sistema canaliza directamente a Capital Humano sin pasar por funnel de operador

#### Scenario: Reingreso tipo de vacante no confirmado → pregunta

- **WHEN** el bot detecta señal `reingreso_verificar`
- **AND** no hay confirmación del tipo de vacante en facts
- **THEN** el sistema pregunta: "¿Busca volver como operador o tiene en mente otro tipo de vacante?"

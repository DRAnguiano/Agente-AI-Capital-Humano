## MODIFIED Requirements

### Requirement: Acuse de handoff incluye datos verificados

El acuse de handoff que recibe el candidato SHALL ser específico a la rama y SHALL incluir los datos clave que se recolectaron en la verificación previa, no un texto genérico.

#### Scenario: Acuse escuelita con licencia

- **WHEN** el handoff por escuelita/CECATI se activa con licencia confirmada
- **THEN** el acuse menciona el tipo de licencia: "Gracias por compartir su información. Con su licencia tipo [B/E], nuestro equipo de Capital Humano revisará si hay generación disponible."

#### Scenario: Acuse B1 con unidad confirmada

- **WHEN** el handoff B1 se activa con unidad confirmada
- **THEN** el acuse menciona la unidad: "Gracias, lo canalizamos con Capital Humano para revisar las vacantes B1 de [full/sencillo]."

#### Scenario: Acuse reingreso con tipo de vacante

- **WHEN** el handoff reingreso se activa
- **THEN** el acuse menciona el tipo de vacante buscada y el siguiente paso concreto.

### Requirement: Nota IA — Siguiente acción por rama de handoff

El campo `Siguiente acción` en la nota privada de Chatwoot SHALL reflejar la acción concreta pendiente según la rama de handoff, no el texto genérico "continuar flujo automático".

#### Scenario: Siguiente acción reingreso

- **WHEN** la nota se renderiza para un candidato con señal `reingreso_verificar`
- **THEN** `Siguiente acción` dice "Verificar historial de [nombre] y confirmar disponibilidad de vacante."

#### Scenario: Siguiente acción escuelita/CECATI con licencia

- **WHEN** la nota se renderiza para candidato con señal escuelita/cecati y licencia confirmada
- **THEN** `Siguiente acción` dice "Confirmar disponibilidad de generación de escuelita."

#### Scenario: Siguiente acción B1

- **WHEN** la nota se renderiza para candidato con señal B1 y datos confirmados
- **THEN** `Siguiente acción` dice "Revisar vacante B1/US para operador de [unidad]."

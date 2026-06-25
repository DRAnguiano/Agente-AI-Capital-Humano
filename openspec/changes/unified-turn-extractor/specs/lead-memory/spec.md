## MODIFIED Requirements

### Requirement: Registro de facts, mensajes y eventos

El sistema SHALL persistir los facts en `rh_lead_facts_v2` (key-value por lead), el log crudo
de mensajes en `rh_lead_messages_v2`, y los eventos de ciclo de vida en `rh_lead_events_v2`,
manteniendo además un resumen del lead. La escritura de un fact SHALL estar **gobernada por
confianza**: el valor se sobreescribe únicamente cuando la confianza nueva es mayor o igual a
la guardada, o cuando el turno trae una corrección explícita del candidato. SHALL NOT
sobreescribir el valor de forma incondicional dejando la confianza heredada del valor
anterior.

#### Scenario: Turno persistido
- **WHEN** se resuelve un turno
- **THEN** se guardan el/los mensajes, los facts activos y un evento de ciclo de vida del lead

#### Scenario: Dato débil no pisa a uno fuerte
- **WHEN** llega un fact con confianza menor que la del fact guardado y sin corrección explícita
- **THEN** el valor guardado se conserva (no se sobreescribe con el más débil)

#### Scenario: Corrección explícita del candidato sí actualiza
- **WHEN** el candidato corrige un dato de forma explícita (p. ej. "no, son 51 no 61")
- **THEN** el valor se actualiza aunque la confianza nueva no supere a la guardada, porque la corrección explícita es autoritativa

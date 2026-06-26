# lead-memory Specification

## Purpose

Mantener la memoria persistente de cada lead en PostgreSQL (`hrdb`): identidad,
facts, mensajes, eventos de ciclo de vida, resumen y etapa del embudo. Es la base sobre
la que se construye la vista accionable del reclutador (`v_rh_work_queue`) y el status
del candidato.
## Requirements
### Requirement: Identidad única de lead

El sistema SHALL identificar a cada lead por `(channel, channel_user_id)` con una sola
fila en `rh_leads_v2`, vinculando los identificadores de Chatwoot (account, inbox,
conversation, contact) cuando estén disponibles.

#### Scenario: Primer contacto
- **WHEN** llega un mensaje de un `channel_user_id` nunca visto
- **THEN** el sistema crea una fila en `rh_leads_v2` y la asocia a su conversación de Chatwoot

#### Scenario: Contacto recurrente
- **WHEN** vuelve a escribir un lead existente
- **THEN** el sistema reutiliza su fila y memoria, sin duplicar el lead

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

### Requirement: Escritura de facts gobernada por confianza

El sistema SHALL implementar `upsert_lead_fact` con gobernanza por confianza cuando
`CONFIDENCE_GOVERNED_WRITES=true`: un valor en `rh_lead_facts_v2` SHALL sobrescribirse
solo si la confianza nueva ≥ la confianza guardada, O si el fact es una corrección
explícita (`is_explicit_correction=true`). Con `CONFIDENCE_GOVERNED_WRITES=false` (default
backward-compat), el sistema mantiene el comportamiento anterior (siempre pisa + GREATEST).

#### Scenario: Dato débil no pisa dato fuerte
- **WHEN** un fact ya tiene confianza 0.9 y llega una nueva extracción con confianza 0.5
- **THEN** el valor guardado no se sobrescribe (con `CONFIDENCE_GOVERNED_WRITES=true`)

#### Scenario: Corrección explícita pisa aunque sea menor
- **WHEN** el candidato corrige explícitamente un dato previo (`is_explicit_correction=true`)
- **THEN** el nuevo valor se persiste aunque su confianza sea menor al guardado

#### Scenario: Confianza igual pisa
- **WHEN** llega un fact con la misma confianza que el guardado
- **THEN** el nuevo valor pisa el anterior (comportamiento determinista)

### Requirement: Etapa del embudo derivada

El sistema SHALL mantener la etapa del lead dentro del embudo de reclutamiento
(`new → interested → ... → human_review → closed`), avanzándola según el contrato y la
completitud del perfil, y exponiendo la prioridad/acción recomendada en la vista
`v_rh_work_queue`.

#### Scenario: Avance de etapa
- **WHEN** un turno cambia la completitud del perfil o dispara revisión humana
- **THEN** la etapa del lead se actualiza y se refleja en la cola de trabajo del reclutador


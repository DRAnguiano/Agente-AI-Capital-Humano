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

El sistema SHALL persistir los facts en `rh_lead_facts_v2` (key-value por lead), el log
crudo de mensajes en `rh_lead_messages_v2`, y los eventos de ciclo de vida en
`rh_lead_events_v2`, manteniendo además un resumen del lead.

#### Scenario: Turno persistido
- **WHEN** se resuelve un turno
- **THEN** se guardan el/los mensajes, los facts activos y un evento de ciclo de vida del lead

### Requirement: Etapa del embudo derivada

El sistema SHALL mantener la etapa del lead dentro del embudo de reclutamiento
(`new → interested → ... → human_review → closed`), avanzándola según el contrato y la
completitud del perfil, y exponiendo la prioridad/acción recomendada en la vista
`v_rh_work_queue`.

#### Scenario: Avance de etapa
- **WHEN** un turno cambia la completitud del perfil o dispara revisión humana
- **THEN** la etapa del lead se actualiza y se refleja en la cola de trabajo del reclutador

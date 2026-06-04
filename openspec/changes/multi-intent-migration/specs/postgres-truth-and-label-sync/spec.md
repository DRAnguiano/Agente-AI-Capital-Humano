## ADDED Requirements

### Requirement: Postgres como fuente de verdad operativa

El sistema SHALL tratar PostgreSQL como la fuente de verdad operativa del perfil del
candidato y Chatwoot como display/canal de trabajo. Antes de decidir qué preguntar y qué
labels modificar, el sistema SHALL consultar los facts persistidos en Postgres. El flujo
del turno SHALL ser: extraer facts con evidence → validar/conflictos/correcciones →
actualizar Postgres → recalcular el estado del perfil desde Postgres → calcular
`labels_to_add` y `labels_to_remove` → sincronizar Chatwoot → guardar evento/auditoría.

#### Scenario: Estado del perfil se recalcula desde Postgres
- **WHEN** el sistema decide la siguiente pregunta o las labels a modificar
- **THEN** lee los facts activos en `rh_lead_facts_v2` y el estado en `rh_leads_v2`/`v_rh_work_queue`, no el texto del LLM ni la nota privada

#### Scenario: Orden del turno
- **WHEN** llega un mensaje con facts confirmables
- **THEN** el sistema actualiza Postgres antes de recalcular el estado, y sincroniza Chatwoot solo después de esa actualización

### Requirement: Labels derivados de Postgres

El sistema SHALL calcular los labels de Chatwoot a partir del estado persistido en
PostgreSQL, no desde texto generado por el LLM ni desde la nota privada.

#### Scenario: Perfil incompleto
- **GIVEN** Postgres indica que faltan licencia y apto médico
- **WHEN** se sincroniza Chatwoot
- **THEN** el sistema aplica `falta_licencia` y `falta_apto`
- **AND** no aplica `perfil_listo`

#### Scenario: Perfil listo
- **GIVEN** Postgres contiene todos los campos núcleo confirmados y sin conflicto
- **WHEN** se sincroniza Chatwoot
- **THEN** el sistema aplica `perfil_listo`
- **AND** remueve `bot_activo`

#### Scenario: Sin evidencia nueva
- **WHEN** el mensaje no contiene facts confirmables
- **THEN** el sistema no cambia Postgres
- **AND** no modifica labels en Chatwoot

#### Scenario: Conflicto de fact
- **GIVEN** Postgres tiene `experience_years=9`
- **WHEN** el candidato dice "creo que en realidad son 10 años"
- **THEN** el sistema no sobrescribe el fact confirmado
- **AND** crea fact pendiente o evento de corrección
- **AND** no cambia labels finales hasta confirmar

### Requirement: Verificación de completitud antes de perfil_listo

El sistema SHALL verificar en Postgres que todos los campos núcleo estén completos y sin
conflicto antes de aplicar `perfil_listo`. Al aplicar `perfil_listo` SHALL remover
`bot_activo`. Al detectar `reingreso_verificar` SHALL agregar ese label y remover
`bot_activo`.

#### Scenario: Núcleo incompleto en Postgres
- **WHEN** falta algún campo núcleo o hay un fact en conflicto en Postgres
- **THEN** el sistema NO aplica `perfil_listo` y mantiene `bot_activo`

#### Scenario: Reingreso detectado
- **WHEN** se detecta intención de reingreso
- **THEN** el sistema agrega `reingreso_verificar` y remueve `bot_activo`

### Requirement: Autoridad de modificación de labels

Solo `label_planner` o `chatwoot_sync` SHALL modificar labels en Chatwoot. El LLM NO SHALL
decidir, crear ni quitar labels. La nota privada de Chatwoot es display-only y NO SHALL
usarse como fuente de verdad. Si no hay evidence suficiente, el sistema NO SHALL modificar
facts ni labels; si hay conflicto, NO SHALL sobrescribir silenciosamente (marca conflicto
o pide aclaración).

#### Scenario: El LLM no toca labels
- **WHEN** el LLM redacta una respuesta
- **THEN** no modifica labels; cualquier cambio de label proviene de `label_planner`/`chatwoot_sync` a partir de facts de Postgres

#### Scenario: Nota privada no es fuente de verdad
- **WHEN** el sistema calcula labels o la siguiente pregunta
- **THEN** lo hace desde Postgres, nunca leyendo la nota privada de Chatwoot

### Requirement: Auditoría de sincronización Chatwoot

El sistema SHALL registrar cada cambio de label con: `conversation_id`, `lead_id`,
`labels_before`, `labels_after`, `labels_to_add`, `labels_to_remove`, `reason`,
`facts_source` y `event_id`.

#### Scenario: Cambio de labels auditado
- **WHEN** el sistema modifica labels en Chatwoot
- **THEN** registra `conversation_id`, `lead_id`, `labels_before`, `labels_after`, `labels_to_add`, `labels_to_remove`, `reason`, `facts_source` y `event_id`

#### Scenario: Sincronización sin cambios
- **WHEN** el recálculo desde Postgres no produce diferencias de labels
- **THEN** no se modifica Chatwoot y el evento de auditoría registra `labels_to_add` y `labels_to_remove` vacíos

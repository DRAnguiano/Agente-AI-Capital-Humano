# chatwoot-label-taxonomy Specification

## Purpose

Definir el catálogo oficial de labels activas de Chatwoot y sus reglas invariantes
(exclusividad, derivación desde Postgres, semántica). Es la referencia única de qué labels
existen y cómo se relacionan; el cálculo concreto por turno lo hacen `label_planner` y
`chatwoot_sync` a partir de Postgres/lead_memory (fuente de verdad operativa). El LLM no
decide labels.

## Requirements

### Requirement: Catálogo oficial de labels activas

El sistema SHALL usar únicamente las siguientes labels activas en Chatwoot:
`aclaracion_pendiente`, `bot_activo`, `cecati`, `disponible_acudir`, `documentos`,
`escuelita`, `falta_apto`, `falta_ciudad`, `falta_experiencia`, `falta_licencia`,
`falta_unidad`, `foraneo`, `jerga_ambigua`, `local_laguna`, `objetivo_full_sencillo`,
`perfil_listo`, `reingreso_verificar`, `requiere_agente`, `requiere_revision_ch`,
`riesgo_alto`, `seguimiento`, `urgente`, `validar_traslado`.

#### Scenario: Label fuera del catálogo
- **WHEN** un cálculo propone una label que no está en el catálogo oficial
- **THEN** el sistema no la aplica

### Requirement: Labels derivadas de Postgres, no del LLM

Las labels SHALL calcularse desde Postgres/lead_memory, no desde texto del LLM ni desde la
nota privada. Solo `label_planner` o `chatwoot_sync` SHALL calcular `labels_to_add` y
`labels_to_remove`. Si no hay evidence suficiente, el sistema NO SHALL modificar facts ni
labels.

#### Scenario: El LLM no decide labels
- **WHEN** el LLM redacta una respuesta o la nota
- **THEN** no crea, quita ni decide labels; el cambio proviene de `label_planner`/`chatwoot_sync` desde facts de Postgres

#### Scenario: Sin evidence suficiente
- **WHEN** el mensaje no permite confirmar un campo
- **THEN** no se modifican facts ni labels

### Requirement: Exclusividad mutua de labels

El sistema SHALL tratar `local_laguna` y `foraneo` como mutuamente excluyentes, y
`objetivo_full_sencillo`, `cecati` y `escuelita` como mutuamente excluyentes.

#### Scenario: Ubicación
- **WHEN** se aplica `local_laguna`
- **THEN** no coexiste `foraneo` (y viceversa)

#### Scenario: Objetivo de experiencia
- **WHEN** se aplica `objetivo_full_sencillo`
- **THEN** no coexisten `cecati` ni `escuelita`

### Requirement: Labels terminales remueven bot_activo

El sistema SHALL remover `bot_activo` al aplicar cualquiera de: `perfil_listo`,
`requiere_agente`, `requiere_revision_ch`, `riesgo_alto`, `reingreso_verificar`.

#### Scenario: Handoff o perfil listo
- **WHEN** se aplica `perfil_listo`, `requiere_agente`, `requiere_revision_ch`, `riesgo_alto` o `reingreso_verificar`
- **THEN** el sistema remueve `bot_activo`

### Requirement: Labels de campo faltante derivadas de missing_fields

El sistema SHALL derivar las labels `falta_*` (`falta_apto`, `falta_ciudad`,
`falta_experiencia`, `falta_licencia`, `falta_unidad`) directamente de `missing_fields`
calculado desde Postgres.

#### Scenario: Campo faltante
- **WHEN** `missing_fields` incluye la licencia
- **THEN** el sistema aplica `falta_licencia` y la retira cuando el campo se completa

### Requirement: Condiciones de perfil_listo

El sistema SHALL aplicar `perfil_listo` solo cuando todos los campos núcleo estén
completos, confirmados y sin conflicto en Postgres.

#### Scenario: Núcleo incompleto o en conflicto
- **WHEN** falta un campo núcleo o existe un fact en conflicto
- **THEN** el sistema NO aplica `perfil_listo`

### Requirement: Semántica de documentos, urgente y reingreso

El sistema SHALL aplicar `documentos` cuando el candidato habló o envió documentación, sin
que ello implique documentos completos. `urgente` SHALL aplicarse solo por regla explícita,
nunca por el tono del LLM. `reingreso_verificar` SHALL detener el bot automático y requerir
revisión humana.

#### Scenario: Mención de documentos
- **WHEN** el candidato dice que enviará o tiene documentación
- **THEN** se aplica `documentos`, pero no implica `perfil_listo` por sí solo

#### Scenario: Urgente por regla
- **WHEN** no hay una regla explícita que marque urgencia
- **THEN** el sistema no aplica `urgente` aunque el tono del mensaje lo sugiera

#### Scenario: Reingreso detiene el bot
- **WHEN** se aplica `reingreso_verificar`
- **THEN** el bot automático no continúa el funnel y se requiere revisión humana

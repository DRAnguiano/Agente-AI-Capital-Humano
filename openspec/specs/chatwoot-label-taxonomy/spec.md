# chatwoot-label-taxonomy Specification

## Purpose

Definir el catálogo oficial de labels activas de Chatwoot y sus reglas invariantes
(exclusividad, derivación desde Postgres, semántica). Es la referencia única de qué labels
existen y cómo se relacionan; el cálculo concreto por turno lo hacen `label_planner` y
`chatwoot_sync` a partir de Postgres/lead_memory (fuente de verdad operativa). El LLM no
decide labels.

## Catálogo operativo activo

### Labels activas (24)

`aclaracion_pendiente`, `bot_activo`, `cecati_sugerido`,
`considerar_escuelita_transmontes`, `considerar_operador_b1`, `documentos`, `falta_apto`,
`falta_ciudad`, `falta_experiencia`, `falta_licencia`, `falta_unidad`, `foraneo`,
`jerga_ambigua`, `llamada_pendiente`, `local_laguna`, `objetivo_full_sencillo`,
`perfil_listo`, `reingreso_verificar`, `requiere_agente`, `requiere_revision_ch`,
`riesgo_alto`, `seguimiento`, `urgente`, `validar_traslado`.

### Labels deprecadas — NO emitir

| label | reemplazada por | razón |
|---|---|---|
| `cecati` | `cecati_sugerido` | Semántica difusa; eliminada de Chatwoot |
| `escuelita` | `considerar_escuelita_transmontes` | Semántica ambigua; eliminada de Chatwoot |
| `disponible_acudir` | (ninguna) | Legacy/diferido; fuera del profile core |

El sistema SHALL NOT emitir labels deprecadas. `_filter_official_labels` las bloquea.

## Semántica de labels de clasificación de experiencia

| label | condición de emisión | exclusiva con |
|---|---|---|
| `objetivo_full_sencillo` | `experience.vehicle_type` confirmado como `full` o `sencillo` | `cecati_sugerido`, `considerar_escuelita_transmontes` |
| `considerar_escuelita_transmontes` | `experience.non_target_vehicle_type` detectado (torton, rabón, reparto local, interurbano) | `objetivo_full_sencillo`, `cecati_sugerido` |
| `cecati_sugerido` | candidato sin experiencia en carretera al que se orientó sobre CECATI | `objetivo_full_sencillo`, `considerar_escuelita_transmontes` |
| `considerar_operador_b1` | candidato potencial para vacante EUA/B1; requiere validación humana (inglés, documentos) | — |
| `llamada_pendiente` | perfil listo o `requiere_agente` + candidato solicitó o se programó llamada | — |

> **Nota**: `considerar_escuelita_transmontes` NO convierte al candidato en objetivo full/sencillo.
> Es una clasificación de derivación, no de confirmación de vacante.
> `cecati_sugerido` NO implica rechazo; es orientación informativa sobre el CECATI en Gómez Palacio
> sin convenio directo.

## Requirements

### Requirement: Catálogo oficial de labels activas

El sistema SHALL usar únicamente las labels del catálogo activo listado arriba.

#### Scenario: Label fuera del catálogo
- **WHEN** un cálculo propone una label que no está en el catálogo oficial
- **THEN** el sistema no la aplica

#### Scenario: Label deprecada
- **WHEN** se intenta emitir `cecati` o `escuelita`
- **THEN** `_filter_official_labels` la descarta silenciosamente

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

El sistema SHALL tratar `local_laguna` y `foraneo` como mutuamente excluyentes.
El sistema SHALL tratar `objetivo_full_sencillo`, `cecati_sugerido` y
`considerar_escuelita_transmontes` como mutuamente excluyentes.

#### Scenario: Ubicación
- **WHEN** se aplica `local_laguna`
- **THEN** no coexiste `foraneo` (y viceversa)

#### Scenario: Objetivo de experiencia
- **WHEN** se aplica `objetivo_full_sencillo`
- **THEN** no coexisten `cecati_sugerido` ni `considerar_escuelita_transmontes`

#### Scenario: Derivación no objetivo
- **WHEN** se aplica `considerar_escuelita_transmontes`
- **THEN** no coexiste `objetivo_full_sencillo` ni `cecati_sugerido`

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

### Requirement: llamada_pendiente solo tras perfil listo o handoff

`llamada_pendiente` SHALL emitirse únicamente cuando `perfil_listo` esté activo o
`requiere_agente` esté activo y el candidato haya solicitado o acordado una llamada.
La lógica de agenda (`call_scheduling`) pertenece a una fase separada.

#### Scenario: Llamada antes de perfil listo
- **WHEN** el perfil no está listo y el candidato pide ser contactado
- **THEN** el sistema NO aplica `llamada_pendiente`; usa `seguimiento`

### Requirement: considerar_operador_b1 canaliza a humano

`considerar_operador_b1` SHALL aplicarse cuando el candidato exprese interés en vacante
EUA o sea identificado como potencial para ese rol. El sistema SHALL combinarla con
`requiere_agente` para detener el funnel automático y requerir validación humana
(nivel de inglés, documentación B1/VISA). `disponible_acudir` SHALL NOT usarse como
señal de perfilamiento ni como requisito de `perfil_listo`.

#### Scenario: Candidato potencial B1
- **WHEN** se detecta interés o aptitud para vacante EUA/B1
- **THEN** el sistema aplica `considerar_operador_b1` y `requiere_agente`
- **AND** detiene el funnel automático

#### Scenario: disponible_acudir no perfila
- **WHEN** el candidato indica disponibilidad para acudir a instalaciones
- **THEN** el sistema NO aplica `disponible_acudir` ni la usa para calcular `perfil_listo`
- **AND** puede registrar el dato como nota contextual únicamente

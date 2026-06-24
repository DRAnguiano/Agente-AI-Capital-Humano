## MODIFIED Requirements

### Requirement: Catálogo oficial de labels activas

El sistema SHALL usar únicamente las labels del catálogo activo en TODO path de
emisión, incluido el fallback de sincronización (`_fallback_chatwoot_labels`).
`requiere_humano` SHALL NOT emitirse: no pertenece al catálogo. Cuando
corresponda canalización humana, el sistema SHALL emitir `requiere_agente`.

#### Scenario: Label fuera del catálogo
- **WHEN** un cálculo propone una label que no está en el catálogo oficial
- **THEN** el sistema no la aplica

#### Scenario: Label deprecada
- **WHEN** se intenta emitir `cecati` o `escuelita`
- **THEN** `_filter_official_labels` la descarta silenciosamente

#### Scenario: Fallback con requires_human
- **GIVEN** el sync principal falló y se usa el fallback de labels
- **WHEN** el resultado indica `requires_human = true`
- **THEN** el fallback emite `requiere_agente`
- **AND** NO emite `requiere_humano`

#### Scenario: Fallback con riesgo alto
- **GIVEN** el sync principal falló y se usa el fallback de labels
- **WHEN** el resultado indica `risk_level = high`
- **THEN** el fallback emite `riesgo_alto`
- **AND** NO emite `requiere_humano`

#### Scenario: Fallback solo emite labels oficiales
- **WHEN** el fallback de labels produce su lista para cualquier combinación de
  `requires_human`, `risk_level` y `current_stage`
- **THEN** toda label emitida pertenece al catálogo oficial activo

### Requirement: Condiciones de perfil_listo

El sistema SHALL aplicar `perfil_listo` solo cuando todos los campos núcleo estén
completos, confirmados y sin conflicto en Postgres. `experience.vehicle_type`
SHALL estar confirmado como `full` o `sencillo`; `experience.years` por sí solo
SHALL NOT satisfacer el requisito de unidad. Cuando `experience.vehicle_type`
no esté confirmado (vacío o con valor ambiguo como jerga vehicular), el sistema
SHALL emitir `falta_unidad` y SHALL NOT emitir `perfil_listo`. `falta_unidad`
SHALL removerse al confirmarse la unidad. `falta_unidad` y `perfil_listo`
SHALL NOT coexistir.

#### Scenario: Núcleo incompleto o en conflicto
- **WHEN** falta un campo núcleo o existe un fact en conflicto
- **THEN** el sistema NO aplica `perfil_listo`

#### Scenario: Años de experiencia sin unidad confirmada
- **GIVEN** facts con `experience.years = 5 años`, licencia, apto vigente y
  vacante aceptada, pero sin `experience.vehicle_type`
- **WHEN** se calculan las labels
- **THEN** el sistema NO aplica `perfil_listo`
- **AND** aplica `falta_unidad`

#### Scenario: Unidad ambigua no confirma
- **GIVEN** facts con `experience.years = 5 años` y
  `experience.vehicle_type = quinta rueda` (o tráiler/jerga ambigua)
- **WHEN** se calculan las labels
- **THEN** el sistema NO aplica `perfil_listo`
- **AND** aplica `falta_unidad`

#### Scenario: Full completo produce perfil_listo
- **GIVEN** facts núcleo completos con `experience.vehicle_type = full`
- **WHEN** se calculan las labels
- **THEN** el sistema aplica `perfil_listo`
- **AND** NO aplica `falta_unidad`

#### Scenario: Sencillo completo produce perfil_listo
- **GIVEN** facts núcleo completos con `experience.vehicle_type = sencillo`
- **WHEN** se calculan las labels
- **THEN** el sistema aplica `perfil_listo`
- **AND** NO aplica `falta_unidad`

### Requirement: Labels terminales remueven bot_activo

El sistema SHALL remover `bot_activo` al aplicar cualquiera de: `perfil_listo`,
`requiere_agente`, `requiere_revision_ch`, `riesgo_alto`, `reingreso_verificar`.
La regla SHALL aplicarse en todo path de emisión, incluido el fallback.
Cuando no hay label terminal presente, `bot_activo` SHALL conservarse.

#### Scenario: perfil_listo remueve bot_activo
- **WHEN** se aplica `perfil_listo`
- **THEN** el sistema remueve `bot_activo`

#### Scenario: requiere_agente remueve bot_activo
- **WHEN** se aplica `requiere_agente`
- **THEN** el sistema remueve `bot_activo`

#### Scenario: requiere_revision_ch remueve bot_activo
- **WHEN** se aplica `requiere_revision_ch`
- **THEN** el sistema remueve `bot_activo`

#### Scenario: riesgo_alto remueve bot_activo
- **WHEN** se aplica `riesgo_alto`
- **THEN** el sistema remueve `bot_activo`

#### Scenario: reingreso_verificar remueve bot_activo
- **WHEN** se aplica `reingreso_verificar`
- **THEN** el sistema remueve `bot_activo`

#### Scenario: Sin terminales bot_activo permanece
- **WHEN** el cálculo no aplica ninguna label terminal
- **THEN** `bot_activo` permanece activo

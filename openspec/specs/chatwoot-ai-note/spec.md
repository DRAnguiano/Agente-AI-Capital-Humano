# chatwoot-ai-note Specification

## Purpose

Contrato de la Nota IA privada en Chatwoot: formato canónico, secciones permitidas/prohibidas,
una sola "siguiente acción", renderer determinístico sin facts inventados y sección condicional
de pendientes/conflictos.

## Requirements

### Requirement: Formato canónico de la Nota IA

El sistema SHALL generar la nota privada de Chatwoot con exactamente estas secciones,
en este orden, comenzando con la cabecera literal `🤖 Nota IA: Seguimiento de candidato`:

```
🤖 Nota IA: Seguimiento de candidato

Último mensaje: "<literal del candidato, máx 500 chars>"

👤 Contacto
Nombre: <nombre | No disponible>
Teléfono: <teléfono | No disponible>
Canal: <canal | Chatwoot>

📋 Perfil confirmado
Tipo de unidad: <Tracto full | Sencillo | valor humano | Pendiente>
Experiencia: <valor | Pendiente>
Licencia: <tipo/estado | Pendiente> [· vigencia <license.expiration_text>]
Apto médico: <estado humano | Pendiente> [· <medical.apto_expiration_text>]
Cartas/documentos: <estado | Pendiente>
Ciudad: <valor | Pendiente>

⚠️ Pendientes o conflictos        ← CONDICIONAL: solo si existen
<campo>: <pendiente/conflicto clave>

📍 Embudo
Etapa: <etapa desde Postgres>
Bloqueo actual: <bloqueo | Sin bloqueo>
Riesgo: <Bajo | Medio | Alto | No disponible>
Requiere humano: <Sí | No>

⏭️ Siguiente acción
<una única acción determinística>
```

La sección de perfil SHALL titularse `📋 Perfil confirmado` (no `Perfil detectado`).

#### Scenario: Cabecera correcta
- **WHEN** se genera la nota privada
- **THEN** la nota comienza con `🤖 Nota IA: Seguimiento de candidato`

#### Scenario: Orden de secciones
- **WHEN** se genera la nota privada
- **THEN** `Último mensaje` aparece antes que `👤 Contacto`, que aparece antes que
  `📋 Perfil confirmado`, que aparece antes que `📍 Embudo`, que aparece antes que
  `⏭️ Siguiente acción`

#### Scenario: Perfil confirmado renombrado
- **WHEN** se genera la nota privada
- **THEN** la sección de perfil se titula `📋 Perfil confirmado`
- **AND** la nota no contiene `📋 Perfil detectado`

### Requirement: Secciones y campos prohibidos en la nota

El sistema SHALL NOT renderizar en la nota privada: `Interés en pago/compensación`,
la sección `🏷️ Labels` (ni ninguna lista de labels en el cuerpo), `Disponibilidad
actual`, `Disponibilidad para acudir`, la sección `🧠 Memoria breve`, el contenido de
`lead.memory_summary` (crudo o reformulado), ni `Temperatura`.

#### Scenario: Sin interés en pago
- **WHEN** se genera la nota privada
- **THEN** la nota no contiene `Interés en pago/compensación`

#### Scenario: Sin labels en el cuerpo
- **WHEN** se genera la nota privada con cualquier conjunto de labels calculadas
- **THEN** la nota no contiene la sección `🏷️ Labels` ni la lista de labels
- **AND** las labels se sincronizan únicamente mediante el label sync de Chatwoot

#### Scenario: Sin disponibilidad
- **WHEN** se genera la nota privada y `candidate.availability_status` está vacío o presente
- **THEN** la nota no contiene `Disponibilidad actual` ni `Disponibilidad para acudir`

#### Scenario: Sin memory_summary
- **GIVEN** `lead.memory_summary` contiene texto (posiblemente generado por LLM)
- **WHEN** se genera la nota privada
- **THEN** la nota no contiene la sección `🧠 Memoria breve`
- **AND** el texto de `memory_summary` no aparece en la nota

### Requirement: Siguiente acción única

El sistema SHALL renderizar `next_best_action` exactamente una vez, dentro de la sección
`⏭️ Siguiente acción`. La nota SHALL NOT contener la línea `Acción:` en la cabecera ni
ninguna segunda aparición del mismo valor.

#### Scenario: Una sola aparición
- **GIVEN** `lead.next_best_action = "Confirmar tipo de unidad"`
- **WHEN** se genera la nota privada
- **THEN** el texto `Confirmar tipo de unidad` aparece exactamente una vez
- **AND** aparece después del encabezado `⏭️ Siguiente acción`

#### Scenario: Sin Acción en cabecera
- **WHEN** se genera la nota privada
- **THEN** no existe la línea `Acción:` antes de la sección `👤 Contacto`

### Requirement: Renderer determinístico sin facts inventados

`render_candidate_note` SHALL ser una función pura de presentación: mismas entradas →
misma salida, sin llamadas a LLM, DB ni Chatwoot. Los campos del perfil SHALL provenir
exclusivamente de los facts persistidos (`rh_lead_facts_v2` vía context) y de los campos
del lead calculados por el planner (`funnel_stage`, `risk_level`, `requires_human`,
`next_best_action`). Un fact vacío SHALL mostrarse como `Pendiente`; el sistema SHALL NOT
inventar valores. Multimedia sin OCR SHALL NOT producir facts visibles en la nota.

#### Scenario: Campo vacío muestra Pendiente
- **GIVEN** facts sin `candidate.city`
- **WHEN** se genera la nota privada
- **THEN** `Ciudad` muestra `Pendiente`
- **AND** la nota no contiene ninguna ciudad inventada

#### Scenario: Multimedia no produce facts
- **GIVEN** el último mensaje es `<Multimedia omitido>` y no hay facts de unidad
- **WHEN** se genera la nota privada
- **THEN** `Tipo de unidad` muestra `Pendiente`

#### Scenario: Determinismo
- **WHEN** se llama dos veces al renderer con el mismo context y labels
- **THEN** produce exactamente el mismo texto

### Requirement: Vigencia de licencia usa el campo de licencia

La línea `Licencia` SHALL mostrar la vigencia desde `license.expiration_text`
(`license_exp_text`) y SHALL NOT mostrar `medical.apto_expiration_text`
(`apto_exp_text`) como vigencia de licencia. La vigencia del apto médico SHALL
mostrarse únicamente en la línea `Apto médico`.

#### Scenario: Vigencias no se cruzan
- **GIVEN** `license.expiration_text = "vigente hasta 2027"` y
  `medical.apto_expiration_text = "vence en 2 meses"`
- **WHEN** se genera la nota privada
- **THEN** la línea `Licencia` contiene `vigente hasta 2027`
- **AND** la línea `Licencia` no contiene `vence en 2 meses`
- **AND** la línea `Apto médico` contiene `vence en 2 meses`

#### Scenario: Licencia sin vigencia conocida
- **GIVEN** `license.expiration_text` vacío y `medical.apto_expiration_text` presente
- **WHEN** se genera la nota privada
- **THEN** la línea `Licencia` no muestra ninguna vigencia

### Requirement: Sección condicional de pendientes o conflictos

La sección `⚠️ Pendientes o conflictos` SHALL renderizarse únicamente cuando exista al
menos un pendiente o conflicto que bloquee el avance del perfil. Con el perfil núcleo
completo y sin conflictos, la sección SHALL estar ausente. El bloqueo principal SHALL
indicarse siempre en `Bloqueo actual` dentro de `📍 Embudo`.

#### Scenario: Perfil completo sin sección condicional
- **GIVEN** facts núcleo completos y sin conflicto
- **WHEN** se genera la nota privada
- **THEN** la nota no contiene `⚠️`
- **AND** `Bloqueo actual` indica que no hay bloqueo o el siguiente paso de validación

#### Scenario: Perfil incompleto indica bloqueo
- **GIVEN** facts sin tipo de unidad confirmado
- **WHEN** se genera la nota privada
- **THEN** `Bloqueo actual:` está presente con el faltante principal

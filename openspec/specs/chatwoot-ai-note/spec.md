# chatwoot-ai-note Specification

## Purpose

Contrato de la Nota IA privada en Chatwoot: formato canónico, secciones permitidas/prohibidas,
una sola "siguiente acción", renderer determinístico sin facts inventados y sección condicional
de pendientes/conflictos.
## Requirements
### Requirement: Formato canónico de la Nota IA

El sistema SHALL generar la nota privada de Chatwoot en **lenguaje administrativo** para Capital
Humano (no técnico): SHALL NOT usar `Canal`, `Embudo`, `Etapa`, `Bloqueo`, `Riesgo` (salvo
`riesgo_alto`), `Requiere humano`, ni nombres de labels. La cabecera SHALL describir el **escenario
operativo** del candidato. El formato base es:

```
🤖 Nota IA: <escenario operativo>

Último mensaje: "<literal del candidato, máx 500 chars>"

👤 Contacto
Nombre: <nombre | No disponible>
Teléfono: <teléfono | No disponible>

📌 Estado del candidato
<estado operativo en lenguaje simple>

✅ Lo que ya sabemos
<solo los datos relevantes al escenario, confirmados>

⚠️ Falta confirmar              ← CONDICIONAL: solo si hay pendientes
<lo que falta, en lenguaje simple>

👥 Para Capital Humano
<qué debe hacer Capital Humano>
Requiere Agente: <Sí | No>

⏭️ Siguiente acción
<una única acción, dinámica según el último pendiente resuelto>
```

`Riesgo` SHALL aparecer únicamente cuando la label `riesgo_alto` esté activa. `Requiere Agente`
SHALL reemplazar a `Requiere humano`. La sección `👤 Contacto` SHALL NOT incluir `Canal`.

#### Scenario: Sin lenguaje técnico
- **WHEN** se genera la nota privada
- **THEN** la nota no contiene `Embudo`, `Etapa`, `Bloqueo actual`, `Canal` ni `Requiere humano`
- **AND** no contiene nombres de labels técnicas

#### Scenario: Cabecera por escenario
- **WHEN** el candidato corresponde a un escenario operativo (escuelita, perfil listo local, etc.)
- **THEN** la cabecera describe ese escenario (p. ej. `🤖 Nota IA: Candidato para Escuelita Transmontes`)

#### Scenario: Riesgo solo si alto
- **WHEN** el candidato no tiene `riesgo_alto`
- **THEN** la nota no muestra ninguna línea de `Riesgo`

#### Scenario: Requiere Agente reemplaza Requiere humano
- **WHEN** un escenario requiere intervención de Capital Humano
- **THEN** la nota muestra `Requiere Agente: Sí` y nunca `Requiere humano`

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

### Requirement: Cabecera y contenido de la nota por escenario operativo

El sistema SHALL seleccionar el escenario operativo de la nota desde facts/labels/estado
(determinista, no LLM) y SHALL mostrar solo los campos relevantes a ese escenario. Escenarios
mínimos: nuevo/interesado, objetivo en captura, perfil listo local, perfil listo foráneo,
unidad ambigua, escuelita, escuelita sin licencia B/E (no aplica), CECATI (sin experiencia),
B1/EUA, reingreso, edad fuera de perfil, riesgo/sensible, pendiente por licencia/apto, y
licencia/apto vencidos en trámite con comprobante.

#### Scenario: Escuelita muestra solo lo mínimo
- **WHEN** el candidato es escuelita (experiencia no objetivo)
- **THEN** `Lo que ya sabemos` muestra la experiencia no objetivo y la licencia si existe
- **AND** no lista apto, cartas, ciudad ni edad como pendientes principales

#### Scenario: No aplica no ofrece continuar
- **WHEN** el escenario es "no aplica" (escuelita sin B/E, CECATI, edad fuera)
- **THEN** la nota indica el cierre y no propone continuar el flujo automático

#### Scenario: Perfil listo local muestra ciudad exacta
- **WHEN** el candidato es perfil listo local
- **THEN** `Ciudad` muestra la ciudad exacta de la ZM Laguna (Torreón, Gómez Palacio, Lerdo o Matamoros), no "La Laguna"

### Requirement: Documento laboral mostrado según residencia

El sistema SHALL mostrar el requisito de documento laboral según la residencia: para candidato
local de la ZM Laguna, "cartas laborales o semanas cotizadas del IMSS"; para foráneo, "2 cartas
laborales membretadas". SHALL NOT mostrar Infonavit ni mezclar ambos requisitos.

#### Scenario: Documento local
- **WHEN** el candidato es local de la ZM Laguna
- **THEN** la nota describe el documento como "cartas laborales o semanas cotizadas del IMSS"

#### Scenario: Documento foráneo
- **WHEN** el candidato es foráneo
- **THEN** la nota describe el documento como "2 cartas laborales membretadas"

### Requirement: Siguiente acción dinámica según el pendiente resuelto

La `⏭️ Siguiente acción` SHALL reflejar el siguiente pendiente del núcleo del perfil y SHALL
actualizarse cuando el candidato resuelve uno (al enviar/confirmar un dato, la acción avanza al
siguiente pendiente). Con el núcleo completo, SHALL indicar el cierre del escenario: local →
"Validar documentos y continuar proceso"; foráneo → "Validar traslado, documentos y continuidad".

#### Scenario: Avance al resolver un pendiente
- **GIVEN** la siguiente acción pedía la licencia
- **WHEN** el candidato confirma/envía la licencia y queda pendiente el apto
- **THEN** la siguiente acción pasa a pedir el apto médico

#### Scenario: Núcleo local completo
- **GIVEN** un candidato local con todo el núcleo confirmado
- **WHEN** se genera la nota
- **THEN** la siguiente acción es "Validar documentos y continuar proceso"

#### Scenario: Núcleo foráneo completo
- **GIVEN** un candidato foráneo con todo el núcleo confirmado
- **WHEN** se genera la nota
- **THEN** la siguiente acción es "Validar traslado, documentos y continuidad"


# chatwoot-sync Specification

## Purpose

Reflejar el resultado de cada turno en Chatwoot para que el reclutador vea un perfil
accionable: enviar la respuesta pública al candidato, publicar una nota privada con el
estado operativo del candidato, y aplicar las labels del **catálogo oficial** (ver
`chatwoot-label-taxonomy`). La nota privada es display-only y Chatwoot solo refleja el
estado calculado en Postgres.

## Requirements

### Requirement: Respuesta pública al candidato

El sistema SHALL enviar la respuesta generada como mensaje público a la conversación de
Chatwoot del candidato, por el mismo canal de entrada.

#### Scenario: Respuesta generada
- **WHEN** un turno produce una respuesta para el candidato
- **THEN** el sistema la envía como mensaje público a la conversación correspondiente

### Requirement: Nota privada display-only

El sistema SHALL publicar una nota privada en Chatwoot con el estado operativo del
candidato siguiendo el formato objetivo limpio. La nota privada NUNCA SHALL usarse
como fuente de verdad. El renderer SHALL derivar toda la información de facts
confirmados, estado del embudo, bloqueos y planner result desde Postgres — no de
texto narrativo generado por LLM.

Este contrato supersede el formato de "Nota privada simplificada" definido en el change
`multi-intent-migration` (`specs/chatwoot-sync/spec.md`) en los puntos donde divergen:

- la línea `Acción:` superior SHALL NOT renderizarse — `next_best_action` aparece una
  única vez, en `⏭️ Siguiente acción`;
- la sección `🧠 Memoria breve` SHALL NOT renderizarse en v1 (`lead.memory_summary`
  puede contener texto LLM no auditado; el resumen determinístico desde facts canónicos
  es trabajo futuro — `multi-intent-migration` 10c.5);
- `Disponibilidad para acudir` / `Disponibilidad actual` SHALL NOT renderizarse (no es
  campo núcleo del perfil; la label `disponible_acudir` está deprecada);
- la sección de perfil SHALL titularse `📋 Perfil confirmado` (no `Perfil detectado`).

El contrato canónico completo del formato vive en la capability `chatwoot-ai-note`.

#### Scenario: Nota no muestra texto LLM crudo
- **WHEN** se genera la nota privada
- **THEN** el cuerpo de la nota no contiene `memory_summary` ni ningún texto de origen LLM
- **AND** la sección `🧠 Memoria breve` no existe en el output

#### Scenario: Sincronización de nota con formato limpio
- **WHEN** se actualiza el perfil de un lead
- **THEN** el sistema construye la nota privada sin `Interés en pago/compensación`, sin `Labels`, sin sección `Acción:` duplicada y sin `Disponibilidad actual: Pendiente`

#### Scenario: Nota no es fuente de verdad
- **WHEN** el bot decide la siguiente acción o respuesta
- **THEN** lo hace a partir de Postgres/lead_memory/turno actual, nunca leyendo la nota privada

### Requirement: Labels del catálogo oficial

El sistema SHALL aplicar únicamente labels del catálogo oficial definido en
`chatwoot-label-taxonomy`, calculadas desde Postgres (no desde el LLM). El estado base es
`bot_activo`; el campo objetivo de experiencia se expresa con `objetivo_full_sencillo`
(mutuamente excluyente con `cecati_sugerido` y `considerar_escuelita_transmontes`); la
ubicación con `local_laguna` o `foraneo` (mutuamente excluyentes, `foraneo` puede sumar
`validar_traslado`); los campos faltantes con `falta_*`; y el cierre/handoff con
`perfil_listo`, `requiere_agente`, `requiere_revision_ch`, `riesgo_alto` o
`reingreso_verificar` (que remueven `bot_activo`).
NO SHALL usarse labels legacy fuera del catálogo ni labels deprecadas (`cecati`,
`escuelita`, `disponible_acudir`, `lead_nuevo`, `operador_sencillo`/`operador_full`,
`revisar_licencia`).

#### Scenario: Avance de completitud
- **WHEN** el candidato completa campos del núcleo del perfil
- **THEN** se retiran las `falta_*` correspondientes y, al completar todo el núcleo sin conflicto, se aplica `perfil_listo` (que remueve `bot_activo`)

#### Scenario: Estado especial
- **WHEN** el lead dispara un estado especial (foráneo, no objetivo, handoff)
- **THEN** se aplica la label oficial correspondiente (`foraneo`+`validar_traslado`, `cecati_sugerido`/`considerar_escuelita_transmontes`, `requiere_agente`/`requiere_revision_ch`) respetando las exclusividades del catálogo

#### Scenario: No usar labels legacy
- **WHEN** se calcula el conjunto de labels
- **THEN** no se aplica ninguna label fuera del catálogo oficial (sin `lead_nuevo`, `operador_full`, `revisar_licencia`, etc.)


### Requirement: El renderer de la Nota IA SHALL ser determinístico

El sistema SHALL producir la Nota IA exclusivamente desde facts confirmados en Postgres,
resultado del planner y estado del embudo. SHALL NOT reclasificar con LLM, SHALL NOT
renderizar `lead.memory_summary` directamente ni inventar valores ausentes.

#### Scenario: Mismas entradas producen misma nota
- **GIVEN** el mismo contexto de facts, embudo y planner result
- **WHEN** `render_candidate_note` se invoca dos veces
- **THEN** produce exactamente el mismo string

#### Scenario: Facts vacíos muestran Pendiente
- **GIVEN** un fact de perfil no confirmado (ej. licencia sin valor)
- **WHEN** se genera la nota
- **THEN** el campo muestra `Pendiente`, no un valor inventado

#### Scenario: Multimedia no produce facts en la nota
- **GIVEN** el perfil no tiene facts derivados de imágenes o archivos
- **WHEN** se genera la nota
- **THEN** los campos correspondientes muestran `Pendiente`, sin inferencia desde multimedia

### Requirement: La Nota IA SHALL seguir el formato objetivo

El sistema SHALL generar la nota privada con exactamente estas secciones en este orden:
cabecera, Último mensaje, Contacto, Perfil confirmado, Pendientes o conflictos
(condicional), Embudo y Siguiente acción. SHALL NOT incluir: Interés en pago/compensación,
Labels en cuerpo, sección Acción duplicada ni Disponibilidad actual/para acudir.

El formato objetivo es:

```
🤖 Nota IA: Seguimiento de candidato

Último mensaje: "<último mensaje literal del candidato>"

👤 Contacto
Nombre: <nombre | No disponible>
Teléfono: <teléfono | No disponible>
Canal: <canal | Chatwoot>

📋 Perfil confirmado
Tipo de unidad: <Full | Sencillo | Quinta rueda/tráiler por aclarar | Camión local/no objetivo | Pendiente>
Experiencia: <valor | Pendiente>
Licencia: <tipo/estado | Pendiente>
Apto médico: <vigente/renovado/vencido/pendiente>
Cartas/documentos: <estado | Pendiente>
Ciudad: <valor | Pendiente>

⚠️ Pendientes o conflictos          [solo cuando hay bloqueo o conflicto]
<descripción del bloqueo principal>

📍 Embudo
Etapa: <etapa calculada desde Postgres>
Bloqueo actual: <bloqueo principal | Sin bloqueo>
Riesgo: <Bajo | Medio | Alto>
Requiere humano: <Sí | No>

⏭️ Siguiente acción
<acción calculada por el planner determinista>
```

#### Scenario: Nota sin Interés en pago/compensación
- **WHEN** se genera la nota privada para cualquier candidato
- **THEN** el cuerpo de la nota no contiene `Interés en pago/compensación`
- **AND** el cuerpo de la nota no contiene `interest.payment` ni su valor renderizado

#### Scenario: Nota sin sección Labels
- **WHEN** se genera la nota privada
- **THEN** el cuerpo de la nota no contiene `🏷️ Labels`
- **AND** los nombres de labels no aparecen listados en el cuerpo de la nota

#### Scenario: Nota sin Acción duplicada
- **WHEN** se genera la nota privada
- **THEN** `next_best_action` aparece una única vez, en la sección `⏭️ Siguiente acción`
- **AND** no existe una sección separada `Acción:` antes de `👤 Contacto`

#### Scenario: Nota sin Disponibilidad actual
- **WHEN** `candidate.availability_status` no está confirmado
- **THEN** la nota no muestra `Disponibilidad actual: Pendiente`
- **AND** la nota no muestra ninguna sección de disponibilidad por defecto

#### Scenario: Nota sin Memoria breve
- **WHEN** se genera la nota privada
- **THEN** el cuerpo de la nota no contiene `🧠 Memoria breve`
- **AND** `memory_summary` no aparece en el output

#### Scenario: Secciones operativas conservadas
- **WHEN** se genera la nota privada
- **THEN** el output contiene `👤 Contacto`
- **AND** el output contiene `📋 Perfil confirmado`
- **AND** el output contiene `📍 Embudo`
- **AND** el output contiene `⏭️ Siguiente acción`

### Requirement: La sección Pendientes o conflictos SHALL ser condicional

El sistema SHALL incluir `⚠️ Pendientes o conflictos` solo cuando el planner
haya determinado un bloqueo activo o existan facts en conflicto.
SHALL NOT mostrar esta sección cuando el perfil está completo o sin bloqueos.

#### Scenario: Sin bloqueo — sección omitida
- **GIVEN** el perfil está completo y sin conflictos
- **WHEN** se genera la nota
- **THEN** el output no contiene `⚠️ Pendientes o conflictos`

#### Scenario: Con bloqueo activo — sección presente
- **GIVEN** el planner determinó un bloqueo (ej. falta confirmar tipo de unidad)
- **WHEN** se genera la nota
- **THEN** el output contiene `⚠️ Pendientes o conflictos`

### Requirement: Revisión humana SHALL mostrarse condicionalmente

El sistema SHALL mostrar una indicación de revisión humana cuando `requires_human=True`
o cuando las labels incluyan `considerar_operador_b1` o `reingreso_verificar`. El campo
`Requiere humano: Sí` en la sección Embudo cumple esta función; no es necesaria una
sección separada salvo para indicar el motivo específico (B1, reingreso).

#### Scenario: B1 — nota indica canalización humana
- **GIVEN** las labels incluyen `considerar_operador_b1`
- **WHEN** se genera la nota
- **THEN** `Requiere humano: Sí` aparece en la sección Embudo

#### Scenario: Reingreso — nota indica revisión humana
- **GIVEN** las labels incluyen `reingreso_verificar`
- **WHEN** se genera la nota
- **THEN** `Requiere humano: Sí` aparece en la sección Embudo

### Requirement: Labels deprecadas SHALL NOT aparecer en la nota

El sistema SHALL NOT mostrar `cecati`, `escuelita` ni `disponible_acudir` en ninguna
sección del cuerpo de la nota.

#### Scenario: Labels deprecadas ausentes
- **WHEN** se genera la nota para cualquier perfil
- **THEN** el cuerpo de la nota no contiene las strings `cecati\n`, `escuelita\n` ni `disponible_acudir`

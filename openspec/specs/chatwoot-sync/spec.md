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

El sistema SHALL publicar/actualizar una nota privada en Chatwoot con el estado operativo
del candidato (datos conocidos, faltantes, siguiente acción) calculado desde Postgres. La
nota privada NUNCA SHALL usarse como fuente de verdad para decisiones del bot, y NO incluye
`Temperatura`, `Interés en pago/compensación` ni la lista de labels (ver el contrato
simplificado en el change `multi-intent-migration`).

#### Scenario: Sincronización de nota
- **WHEN** se actualiza el perfil de un lead
- **THEN** el sistema construye y publica la nota privada con el estado actual calculado desde Postgres

#### Scenario: Nota no es fuente de verdad
- **WHEN** el bot decide la siguiente acción o respuesta
- **THEN** lo hace a partir de Postgres/lead_memory/turno actual, nunca leyendo la nota privada

### Requirement: Labels del catálogo oficial

El sistema SHALL aplicar únicamente labels del catálogo oficial definido en
`chatwoot-label-taxonomy`, calculadas desde Postgres (no desde el LLM). El estado base es
`bot_activo`; el campo objetivo de experiencia se expresa con `objetivo_full_sencillo`
(mutuamente excluyente con `cecati` y `escuelita`); la ubicación con `local_laguna` o
`foraneo` (mutuamente excluyentes, `foraneo` puede sumar `validar_traslado`); los campos
faltantes con `falta_*`; y el cierre/handoff con `perfil_listo`, `requiere_agente`,
`requiere_revision_ch`, `riesgo_alto` o `reingreso_verificar` (que remueven `bot_activo`).
NO SHALL usarse labels legacy fuera del catálogo (`lead_nuevo`, `lead_en_proceso`,
`operador_sencillo`/`operador_full`/`operador_ambos`, `revisar_licencia`).

#### Scenario: Avance de completitud
- **WHEN** el candidato completa campos del núcleo del perfil
- **THEN** se retiran las `falta_*` correspondientes y, al completar todo el núcleo sin conflicto, se aplica `perfil_listo` (que remueve `bot_activo`)

#### Scenario: Estado especial
- **WHEN** el lead dispara un estado especial (foráneo, no objetivo, handoff)
- **THEN** se aplica la label oficial correspondiente (`foraneo`+`validar_traslado`, `cecati`/`escuelita`, `requiere_agente`/`requiere_revision_ch`) respetando las exclusividades del catálogo

#### Scenario: No usar labels legacy
- **WHEN** se calcula el conjunto de labels
- **THEN** no se aplica ninguna label fuera del catálogo oficial (sin `lead_nuevo`, `operador_full`, `revisar_licencia`, etc.)

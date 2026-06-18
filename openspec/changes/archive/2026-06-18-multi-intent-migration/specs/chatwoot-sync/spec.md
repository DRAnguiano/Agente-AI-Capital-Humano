## MODIFIED Requirements

### Requirement: Nota privada display-only

El sistema SHALL publicar/actualizar una nota privada en Chatwoot con el estado operativo
del candidato, siguiendo el contrato simplificado (ver "Nota privada simplificada"). La
nota privada NUNCA SHALL usarse como fuente de verdad: no decide facts, labels, etapa ni la
siguiente pregunta. Ya NO incluye `Temperatura`, `Interés en pago/compensación` ni la lista
de `Labels` (las labels se muestran visualmente en Chatwoot).

#### Scenario: Sincronización de nota
- **WHEN** se actualiza el perfil de un lead
- **THEN** el sistema construye y publica la nota privada con el estado actual calculado desde Postgres, sin secciones de temperatura, pago ni labels

#### Scenario: Nota no es fuente de verdad
- **WHEN** el bot decide la siguiente acción, etapa, facts o labels
- **THEN** lo hace a partir de Postgres/lead_memory, nunca leyendo la nota privada

## ADDED Requirements

### Requirement: Nota privada simplificada

El sistema SHALL generar una nota privada de Chatwoot con secciones operativas mínimas y
sin repetir información que ya vive en labels visuales de Chatwoot. La nota SHALL incluir
únicamente: Acción, Último mensaje literal, Contacto, Memoria breve, Perfil detectado,
Embudo y Siguiente acción. La nota SHALL NOT incluir: Interés en pago/compensación,
Temperatura ni lista de labels.

El formato objetivo es:

```
🤖 Nota IA: Seguimiento de candidato

Acción: <acción calculada por el planner>
Último mensaje: "<último mensaje literal del candidato>"

👤 Contacto
Nombre: <nombre | No disponible>
Teléfono: <teléfono | No disponible>
Canal: <canal>

🧠 Memoria breve
<resumen breve basado solo en facts confirmados o eventos auditados; si no hay evidence, memoria neutra>

📋 Perfil detectado
Tipo de unidad: <Full | Sencillo | Quinta rueda/tráiler por aclarar | Camión local/no objetivo | Pendiente | Requiere aclaración>
Experiencia: <valor | Pendiente | Requiere aclaración>
Licencia: <tipo/estado | Pendiente | Requiere aclaración>
Apto médico: <vigente/renovado/vencido/pendiente/requiere aclaración>
Cartas/documentos: <Sí | No | Pendiente | Requiere aclaración>
Ciudad: <valor | Pendiente | Requiere aclaración>
Disponibilidad para acudir: <valor | Pendiente | Requiere aclaración>

📍 Embudo
Etapa: <etapa calculada desde Postgres>
Bloqueo actual: <faltante/conflicto principal | Sin bloqueo>
Riesgo: <Bajo | Medio | Alto>
Requiere humano: <Sí | No>

⏭️ Siguiente acción
<siguiente acción calculada por el planner determinista>
```

#### Scenario: Nota sin labels duplicadas
- **WHEN** se genera una nota privada
- **THEN** el cuerpo de la nota no contiene la sección `Labels`
- **AND** las labels se sincronizan únicamente mediante Chatwoot label sync

#### Scenario: Nota sin temperatura
- **WHEN** se genera una nota privada
- **THEN** el cuerpo de la nota no contiene la sección `Temperatura`

#### Scenario: Nota sin interés en pago
- **WHEN** se genera una nota privada
- **THEN** el perfil detectado no contiene el campo `Interés en pago/compensación`

### Requirement: Nota privada derivada de Postgres

El sistema SHALL generar la nota privada usando facts confirmados, facts pendientes,
conflicts, `missing_fields`, `completed_fields`, `stage`, `risk_level`, `requires_human` y
`next_action` calculados desde Postgres/lead_memory. El LLM SHALL NOT inventar valores del
perfil, etapa, bloqueo, riesgo ni siguiente acción.

#### Scenario: Vehicle type confirmado
- **GIVEN** Postgres contiene `vehicle_type=full` con evidence válido
- **WHEN** se genera la nota privada
- **THEN** `Tipo de unidad` muestra `Full`
- **AND** no muestra `Pendiente`

#### Scenario: Campo faltante
- **GIVEN** Postgres no contiene licencia confirmada
- **WHEN** se genera la nota privada
- **THEN** `Licencia` muestra `Pendiente`

#### Scenario: Campo en conflicto
- **GIVEN** existe conflicto entre dos valores del mismo campo
- **WHEN** se genera la nota privada
- **THEN** el campo muestra `Requiere aclaración`
- **AND** el `Bloqueo actual` menciona la aclaración requerida

### Requirement: Último mensaje literal

El sistema SHALL mostrar el último mensaje real del candidato de forma literal en la nota
privada.

#### Scenario: Último mensaje corto
- **WHEN** el candidato escribe `full`
- **THEN** la nota muestra `Último mensaje: "full"`

### Requirement: Siguiente acción determinista

Las secciones `Acción` y `Siguiente acción` SHALL derivarse del planner determinista, no
del LLM.

#### Scenario: Falta apto médico
- **GIVEN** el bloqueo principal es `falta_apto`
- **WHEN** se genera la nota
- **THEN** `Acción` y `Siguiente acción` indican seguimiento o confirmación de apto médico

#### Scenario: Reingreso
- **GIVEN** el candidato activa `reingreso_verificar`
- **WHEN** se genera la nota
- **THEN** `Acción` indica verificar reingreso con Capital Humano
- **AND** el bot automático no continúa el funnel

### Requirement: Labels fuera del cuerpo de la nota

El sistema SHALL sincronizar labels en Chatwoot mediante `label_planner` y `chatwoot_sync`,
pero SHALL NOT repetirlas dentro del cuerpo de la nota privada.

#### Scenario: Labels sincronizadas visualmente
- **GIVEN** `label_planner` calcula `labels_to_add` y `labels_to_remove`
- **WHEN** se sincroniza Chatwoot
- **THEN** las labels se actualizan en la conversación/contacto de Chatwoot
- **AND** la nota privada no imprime la lista de labels

### Requirement: Auditoría de nota y labels

El sistema SHALL registrar eventos auditables para la generación de la nota privada y para
la sincronización de labels.

El evento de nota privada SHALL incluir: `lead_id`, `conversation_id`, `note_version`,
`facts_snapshot`, `missing_fields`, `completed_fields`, `conflicts`, `next_action`,
`source_event_id` y `generated_at`.

El evento de sincronización de labels SHALL incluir: `lead_id`, `conversation_id`,
`labels_before`, `labels_after`, `labels_to_add`, `labels_to_remove`, `reason`,
`facts_source` y `event_id`.

#### Scenario: Evento de nota privada
- **WHEN** se genera la nota privada
- **THEN** se registra un evento con `lead_id`, `conversation_id`, `note_version`, `facts_snapshot`, `missing_fields`, `completed_fields`, `conflicts`, `next_action`, `source_event_id` y `generated_at`

#### Scenario: Evento de sincronización de labels
- **WHEN** se sincronizan labels en Chatwoot
- **THEN** se registra un evento con `lead_id`, `conversation_id`, `labels_before`, `labels_after`, `labels_to_add`, `labels_to_remove`, `reason`, `facts_source` y `event_id`

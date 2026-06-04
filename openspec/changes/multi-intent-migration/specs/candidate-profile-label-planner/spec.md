## ADDED Requirements

### Requirement: Clasificación objetivo de experiencia por tipo de unidad

El sistema SHALL distinguir si el candidato tiene experiencia objetivo para la vacante
principal: full o sencillo. La conversión de facts a labels es determinista;
el LLM no decide labels. `objetivo_full_sencillo` SHALL aplicarse SOLO cuando
`vehicle_type` esté confirmado como `full` o `sencillo`; mientras `vehicle_type` sea
`needs_clarification` se aplica `falta_unidad` (+ `aclaracion_pendiente` si corresponde) y
NO `objetivo_full_sencillo`.

#### Scenario: Experiencia objetivo full
- **WHEN** el candidato dice "10 años de full"
- **THEN** el sistema registra `experience_years=10`
- **AND** registra `vehicle_type=full`
- **AND** aplica label `objetivo_full_sencillo`
- **AND** no vuelve a preguntar si la experiencia es full o sencillo

#### Scenario: Experiencia objetivo sencillo
- **WHEN** el candidato dice "manejo sencillo"
- **THEN** el sistema registra `vehicle_type=sencillo`
- **AND** aplica label `objetivo_full_sencillo`

#### Scenario: Quinta rueda/tractocamión sin especificar configuración
- **WHEN** el candidato dice "soy operador de quinta rueda" (o "tractocamión")
- **THEN** el sistema marca `target_experience=true` y `vehicle_type=needs_clarification` (NO lo convierte a sencillo ni full)
- **AND** NO aplica `objetivo_full_sencillo` todavía
- **AND** aplica `falta_unidad` y, si corresponde, `aclaracion_pendiente`
- **AND** pregunta si maneja full o sencillo

### Requirement: Clasificación no objetivo

El sistema SHALL distinguir candidatos sin experiencia y candidatos con experiencia no
objetivo.

#### Scenario: Sin experiencia
- **WHEN** el candidato indica que no tiene experiencia en full, sencillo ni quinta rueda
- **THEN** el sistema aplica label `cecati`
- **AND** no marca `objetivo_full_sencillo`

#### Scenario: Experiencia no objetivo
- **WHEN** el candidato indica experiencia en torton, rabón, reparto, carga local o unidad no objetivo
- **THEN** el sistema aplica label `escuelita` o la ruta definida para validación
- **AND** responde que la vacante principal requiere full o sencillo
- **AND** sugiere comunicarse a los números de Transmontes para validar si hay otra opción disponible

### Requirement: Unidad ambigua requiere aclaración

El sistema SHALL NOT convertir términos genéricos en `vehicle_type` sin aclaración (ver
`normalize_domain_values`). `camión` es genérico ambiguo (puede ser full/sencillo/torton/
rabón/reparto/local). `tráiler`/`traila`/`tractocamión`/`quinta rueda` indican experiencia
compatible pero NO determinan full vs sencillo.

#### Scenario: Camión genérico
- **GIVEN** la última pregunta fue "¿Qué tipo de unidad manejabas?"
- **WHEN** el candidato responde "camión"
- **THEN** el sistema no actualiza `vehicle_type`
- **AND** pregunta: "Para registrarlo bien, ¿era full, sencillo o camión de reparto/local como torton o rabón?"

#### Scenario: Tráiler no determina configuración
- **WHEN** el candidato responde "manejo tráiler" (o "traila")
- **THEN** el sistema marca `vehicle_domain=trailer` y `vehicle_type=needs_clarification`, sin convertirlo a full ni sencillo
- **AND** NO aplica `objetivo_full_sencillo`; aplica `falta_unidad` (+ `aclaracion_pendiente` si corresponde)
- **AND** pregunta si maneja full o sencillo

### Requirement: Número aislado requiere aclaración

El sistema SHALL NOT persistir números aislados como experiencia confirmada si no puede
inferir el campo y la unidad con alta confianza usando `last_bot_question`.

#### Scenario: Número aislado
- **WHEN** el candidato responde "10"
- **AND** no hay última pregunta clara esperando años de experiencia
- **THEN** el sistema no guarda experiencia, edad, días ni meses
- **AND** pregunta: "¿Te refieres a 10 años de experiencia?"

#### Scenario: Número con contexto de experiencia
- **GIVEN** la última pregunta fue "¿Cuántos años tienes manejando full o sencillo?"
- **WHEN** el candidato responde "10"
- **THEN** el sistema interpreta `experience_years=10`
- **AND** `unit=years`
- **AND** guarda el fact si supera el umbral de confianza

### Requirement: Clasificación local/foráneo

El sistema SHALL clasificar la ubicación como local o foránea usando el catálogo de
ciudades/zonas.

#### Scenario: Candidato en ZM Laguna
- **WHEN** la ciudad del candidato pertenece a la Zona Metropolitana de La Laguna
- **THEN** el sistema aplica label `local_laguna`

#### Scenario: Candidato foráneo
- **WHEN** la ciudad del candidato no pertenece a la ZM Laguna
- **THEN** el sistema aplica label `foraneo`
- **AND** si aplica, label `validar_traslado`

### Requirement: Disponibilidad para acudir

Después de clasificar local/foráneo, el sistema SHALL preguntar cuándo tiene
disponibilidad para acudir, salvo que ya exista disponibilidad confirmada.

#### Scenario: Local o foráneo sin disponibilidad
- **GIVEN** el candidato ya tiene ciudad clasificada
- **AND** no existe `availability_to_attend`
- **WHEN** el sistema calcula el siguiente paso
- **THEN** pregunta cuándo tiene disponibilidad para acudir

#### Scenario: Disponibilidad confirmada
- **WHEN** el candidato confirma fecha o disponibilidad para acudir
- **THEN** el sistema registra `availability_to_attend`
- **AND** aplica label `disponible_acudir`

### Requirement: Pipeline de faltantes hasta perfil listo

El sistema SHALL calcular en cada turno qué campos faltan para llegar a `perfil_listo`.
Campos mínimos sugeridos: ciudad/ubicación; tipo de unidad (full o sencillo);
años de experiencia; licencia federal y tipo; apto médico; documentos/cartas;
disponibilidad para acudir.

#### Scenario: Perfil incompleto
- **WHEN** faltan campos del perfil núcleo
- **THEN** el sistema aplica las labels de faltantes correspondientes
- **AND** pregunta solo el siguiente campo faltante
- **AND** no repite campos ya contestados

#### Scenario: Perfil listo
- **WHEN** todos los campos núcleo están completos y sin conflicto
- **THEN** el sistema aplica label `perfil_listo`
- **AND** elimina label `bot_activo`
- **AND** no emite más preguntas automáticas de perfilamiento

### Requirement: No modificar labels sin evidencia

El sistema SHALL NOT modificar facts ni labels de Chatwoot cuando no exista evidencia
suficiente.

#### Scenario: Dato insuficiente
- **WHEN** el mensaje no permite confirmar un campo
- **THEN** el sistema responde sin inventar
- **AND** no actualiza lead_memory
- **AND** no modifica labels en Chatwoot

### Requirement: Reingreso requiere verificación humana

El sistema SHALL detectar intención de reingreso y detener el flujo automático.

#### Scenario: Reingreso
- **WHEN** el candidato dice "sería reingreso", "ya trabajé ahí", "quiero regresar" o equivalente
- **THEN** el sistema aplica label `reingreso_verificar`
- **AND** elimina label `bot_activo`
- **AND** deriva a humano/verificación
- **AND** no continúa preguntando el funnel automáticamente

### Requirement: Label planner determinista

El sistema SHALL calcular las labels a partir de facts confirmados y del estado del
perfil, de forma determinista. El LLM NO SHALL crear, quitar ni decidir labels; tampoco
SHALL marcar el perfil como listo, eliminar `bot_activo` ni afirmar datos sin evidencia.

#### Scenario: Cálculo determinista de labels
- **WHEN** el planner procesa los facts confirmados de un turno
- **THEN** produce `labels_to_add` y `labels_to_remove` derivados solo de facts confirmados y del estado del perfil
- **AND** registra los logs `facts_before`, `facts_after`, `completed_fields`, `missing_fields`, `labels_to_add`, `labels_to_remove`, `next_question` y `reason`
- **AND** el LLM no crea, quita ni decide labels

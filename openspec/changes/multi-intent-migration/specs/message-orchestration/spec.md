## MODIFIED Requirements

### Requirement: Resolución de ruta vía contrato de conocimiento

El sistema SHALL resolver cada mensaje a un contrato con `route`, `intent`, `risk_level`
y banderas (`requires_rag`, `requires_human`, `requires_clarification`). Cuando el flag de
cutover del pipeline multi-intent esté desactivado (estado actual), la resolución usa
Neo4j para reconocer términos y luego aplica guardas de perfil y overrides deterministas.
Cuando el flag esté activado, la resolución SHALL derivarse del pipeline multi-intent
(`classify → enrich → plan`): el `primary_intent`/`questions` enriquecidas determinan la
ruta y `requires_human`/`risk_level`. En ambos modos el LLM no decide políticas de ruteo.

#### Scenario: Pregunta informativa durante una etapa de perfil
- **WHEN** hay una etapa de perfil pendiente y el candidato pregunta por pago/rutas/documentos
- **THEN** el contrato resuelve `route=rag` (responder la pregunta) y la etapa de perfil sigue pendiente, sin forzar la siguiente pregunta del formulario

#### Scenario: Respuesta directa a la pregunta de perfil pendiente
- **WHEN** el candidato responde directamente el dato pendiente del perfil
- **THEN** el contrato resuelve hacia perfil y el dato se registra

#### Scenario: Tema sensible o admisión
- **WHEN** el mensaje toca sustancias/antidoping o admite conducta inhabilitante
- **THEN** el contrato marca `requires_human` y la conversación se rutea a revisión humana, sin continuar extracción de perfil en ese turno

#### Scenario: Cutover al pipeline multi-intent
- **WHEN** el flag de cutover está activado y llega un mensaje compuesto (respuesta + pregunta)
- **THEN** la ruta y la pregunta de perfil se derivan del plan del pipeline multi-intent (answer persistido en silencio + question contestada), no de la lógica monolítica de Neo4j

#### Scenario: Rollback por flag
- **WHEN** el flag de cutover se desactiva
- **THEN** el sistema vuelve a resolver con Neo4j + guardas deterministas, sin cambios en el contrato HTTP externo

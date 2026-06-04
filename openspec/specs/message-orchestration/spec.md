# message-orchestration Specification

## Purpose

Resolver cada mensaje de candidato en una respuesta. Es el "cerebro" actual
(`app/orchestrators/knowledge_orchestrator.handle_message`): clasifica el mensaje vía
Neo4j, aplica guardas deterministas, elige cómo responder (RAG / LLM amistoso /
plantilla controlada / acuse de perfil), agrega una pregunta del funnel cuando
corresponde, y persiste el resultado. Respeta la prioridad de fuentes de verdad y la
política de conversación (`app/policies/conversation_policy.md`).

## Requirements

### Requirement: Resolución de ruta vía contrato de conocimiento

El sistema SHALL resolver cada mensaje a un contrato con `route`, `intent`, `risk_level`
y banderas (`requires_rag`, `requires_human`, `requires_clarification`), usando Neo4j
para reconocer términos y luego aplicar guardas de perfil y overrides deterministas. El
LLM no decide políticas de ruteo.

#### Scenario: Pregunta informativa durante una etapa de perfil
- **WHEN** hay una etapa de perfil pendiente y el candidato pregunta por pago/rutas/documentos
- **THEN** el contrato resuelve `route=rag` (responder la pregunta) y la etapa de perfil sigue pendiente, sin forzar la siguiente pregunta del formulario

#### Scenario: Respuesta directa a la pregunta de perfil pendiente
- **WHEN** el candidato responde directamente el dato pendiente del perfil
- **THEN** el contrato resuelve hacia perfil y el dato se registra

#### Scenario: Tema sensible o admisión
- **WHEN** el mensaje toca sustancias/antidoping o admite conducta inhabilitante
- **THEN** el contrato marca `requires_human` y la conversación se rutea a revisión humana, sin continuar extracción de perfil en ese turno

### Requirement: Selección de modo de respuesta

El sistema SHALL elegir exactamente un modo de respuesta por turno según el contrato, en
este orden: hora local (template), RAG (`requires_rag`), LLM amistoso (smalltalk seguro),
acuse de señal de perfil, o respuesta controlada por plantilla.

#### Scenario: Ruta RAG
- **WHEN** el contrato tiene `requires_rag=true`
- **THEN** el sistema recupera contexto de ChromaDB y genera la respuesta con el LLM acotada a ese contexto

#### Scenario: Smalltalk seguro
- **WHEN** el contrato es smalltalk/amistoso y el mensaje es seguro para el LLM
- **THEN** el sistema responde con el LLM amistoso (voz de equipo), sin inventar facts del candidato

#### Scenario: Sin generación aplicable
- **WHEN** ninguna ruta de generación aplica
- **THEN** el sistema responde con una plantilla controlada derivada del contrato

### Requirement: Pregunta del funnel agregada por el sistema

Después de una respuesta RAG, amistosa o de acuse de perfil, el sistema SHALL agregar a
lo sumo una pregunta del funnel de perfilamiento, emitida por el sistema (no por el LLM)
y solo si aún hay un campo núcleo faltante. Nunca debe encimar una pregunta de perfil en
un saludo inicial ni repetir agresivamente una pregunta pendiente.

#### Scenario: Hay campo faltante tras responder
- **WHEN** se respondió una pregunta lateral y queda un campo de perfil sin completar
- **THEN** el sistema añade una sola pregunta del funnel para el siguiente campo faltante

#### Scenario: Núcleo de perfil completo
- **WHEN** todos los campos núcleo ya están completos
- **THEN** el sistema no añade pregunta de funnel

### Requirement: Persistencia del turno y trazabilidad

El sistema SHALL persistir el turno completo: mensaje de usuario y respuesta del
asistente, actualización de etapa de conversación y de lead, facts extraídos, y un evento
`knowledge_contract_resolved` con metadata de routing, fuentes RAG, costos y timings.

#### Scenario: Turno resuelto
- **WHEN** un mensaje se resuelve en una respuesta
- **THEN** el sistema guarda mensaje+respuesta, actualiza stage y lead memory, y registra el evento con su metadata

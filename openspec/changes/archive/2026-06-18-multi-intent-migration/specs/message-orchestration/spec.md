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

## ADDED Requirements

### Requirement: Respuesta conversacional ante media sin OCR

El sistema SHALL responder, ante cualquier media del candidato (imagen, archivo, documento,
sticker, audio) y mientras no exista una capa validada de OCR/document-understanding, de la
siguiente forma: (a) agradecer el envío; (b) aclarar de forma amable que por el momento no
puede revisar la media o contenido enviado por ese medio; (c) pedir que responda en texto la
pregunta pendiente determinada por la capa de orquestación/planner aplicable. El sistema
SHALL NOT producir facts, labels, elegibilidad ni `profile_ready` a partir de la media, NI
afirmar que la revisó o validó.

> Nota de implementación: esta requirement documenta el comportamiento esperado. La
> adaptación del flujo vivo queda para una fase posterior y no se implementa en este cambio
> doc-only.

#### Scenario: Candidato envía foto en lugar de responder
- **WHEN** hay una pregunta de perfil pendiente y el candidato responde con una imagen o documento
- **THEN** el sistema agradece, aclara que por ahora no puede revisar la media o contenido enviado por ese medio, y pide el dato en texto
- **AND** no persiste facts desde la media

#### Scenario: Sticker o audio durante el perfilamiento
- **WHEN** el candidato envía un sticker o audio
- **THEN** el sistema responde brevemente sin persistir facts
- **AND** retoma una sola pregunta pendiente determinada por la capa de orquestación/planner aplicable, sin afirmar que validó nada

### Requirement: Prioridad conversacional e iteración controlada de preguntas

El sistema SHALL responder primero la intención actual del candidato y, solo si corresponde,
retomar UNA sola pregunta pendiente determinada por la capa de orquestación/planner
aplicable. Ante evasión, smalltalk o media no interpretable, sin contradecir las reglas de
media sin OCR, el sistema SHALL NOT persistir facts nuevos, SHALL responder humanamente
cuando aplique y SHALL retomar o reformular UNA pregunta pendiente. El sistema SHALL NOT
repetir de forma indefinida la misma pregunta sin control: tras reiteraciones sin avance
SHALL reformular, pausar la insistencia o escalar según la política aplicable, en lugar de
insistir. Esta requirement NO obliga a repreguntar siempre.

> Nota de implementación: esta requirement documenta el comportamiento esperado. La
> adaptación del flujo vivo queda para una fase posterior y no se implementa en este cambio
> doc-only.

#### Scenario: Intención actual antes de pregunta pendiente
- **WHEN** el candidato hace una pregunta válida y queda un campo de perfil pendiente
- **THEN** el sistema responde primero esa intención
- **AND** retoma a lo sumo una sola pregunta pendiente

#### Scenario: Evasión repetida no repregunta indefinidamente
- **WHEN** el candidato evade la misma pregunta de forma reiterada sin avanzar
- **THEN** el sistema no repite idéntica la misma pregunta una y otra vez
- **AND** reformula, pausa la insistencia o escala según la política aplicable

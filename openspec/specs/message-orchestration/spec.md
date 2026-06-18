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

### Requirement: Grounding del comentario conversacional

El comentario conversacional del sistema (modo friendly/reacción corta) SHALL basarse
únicamente en lo que el candidato expresó en su mensaje. El sistema SHALL NOT introducir
números, años, experiencia, ciudad, licencia, apto médico, documentos ni condiciones que el
candidato no haya dicho, ni reutilizar valores de ejemplos internos del prompt.

> Nota de implementación: requirement doc-only. La adaptación del flujo vivo
> (`_answer_friendly_message`, few-shots del prompt) queda para una fase posterior y no se
> implementa en este cambio.

#### Scenario: Candidato pide esperar y el sistema no inventa cifras
- **WHEN** el candidato dice "ahorita le respondo", "espéreme" o "luego le digo"
- **THEN** el sistema responde sin mencionar años ni ninguna cifra
- **AND** no afirma datos de experiencia que el candidato no dio

### Requirement: Respuesta de cara al candidato sin instrucciones internas

El sistema SHALL responder al candidato con lenguaje de cara al usuario y SHALL NOT exponer
reglas o instrucciones internas de operación (p. ej. "Mundo debe...", "Si no conoce el
circuito... debe pedir... antes de dar una cifra").

> Nota de implementación: requirement doc-only; no se implementa en este cambio.

#### Scenario: Pregunta de pago no expone reglas internas
- **WHEN** el candidato pregunta por pago o circuitos
- **THEN** el sistema responde con información de cara al candidato, o pide ciudad/circuito de forma natural
- **AND** la respuesta no incluye frases de instrucción interna

### Requirement: Respuesta enfocada sin mezcla de temas

Ante una pregunta específica, el sistema SHALL responder enfocado en ese tema y SHALL NOT
ensamblar contenido de temas no relacionados (p. ej. mezclar pago con paradas autorizadas o
con el proceso documental de una ciudad).

> Nota de implementación: requirement doc-only; no se implementa en este cambio.

#### Scenario: Pregunta de pago para sencillo no mezcla temas
- **WHEN** el candidato pregunta "¿por ejemplo para sencillo?" en el contexto de pago/circuito
- **THEN** la respuesta se mantiene en pago/tipo de unidad
- **AND** no incluye paradas autorizadas ni el proceso documental de otra ciudad

### Requirement: Confirmación de datos sin duplicaciones

La confirmación (ack) que el sistema emite al registrar datos SHALL usar un solo prefijo de
confirmación y SHALL NOT repetir el mismo fact en dos formas (p. ej. "20 años, 20 años de
experiencia") ni duplicar palabras como "Perfecto".

> Nota de implementación: requirement doc-only; no se implementa en este cambio.

#### Scenario: Ack de ciudad y licencia
- **WHEN** el sistema confirma ciudad y tipo de licencia y agrega la siguiente pregunta
- **THEN** la respuesta contiene un solo "Perfecto"
- **AND** no repite el mismo dato dos veces

### Requirement: Reconocimiento de correcciones explícitas

El sistema SHALL reconocer una corrección explícita del candidato sobre un dato previo (por
ejemplo "en realidad es sencillo" o "me equivoqué, son 10 años"), SHALL actualizar el valor
corregido y SHALL NOT repetir el valor anterior ni una interpretación que el candidato ya
rechazó.

> Nota de implementación: la mecánica de detección/persistencia de correcciones está cubierta
> por tasks pendientes de `multi-intent-migration` (6.3, 7.2, 7.4, 9.3.3, 9.3.11). Esta
> requirement fija el comportamiento conversacional esperado en el camino vivo, sin duplicar
> esa lógica; doc-only.

#### Scenario: Corrección de tipo de unidad
- **WHEN** el candidato dice "creo que le había dicho full, en realidad es sencillo"
- **THEN** el sistema registra `experience.vehicle_type=sencillo`
- **AND** no vuelve a afirmar full ni etiquetar "(escuelita)"

#### Scenario: Corrección de años de experiencia
- **WHEN** el candidato dice "no quiero escuelita, sé manejar sencillo, y tengo 10 años"
- **THEN** el sistema toma 10 años y sencillo
- **AND** no reintroduce "escuelita"

### Requirement: Cierre de perfil y política de seguimiento por llamada

Al completar el perfil o cuando el candidato declara documentos listos, el sistema SHALL
indicar un siguiente paso claro y, ante una solicitud de llamada, SHALL fijar el estado/label
de lead correspondiente. La política de contacto SHALL evaluarse contra el horario de oficina
documentado **8:00–17:30, lunes a viernes**, en la zona canónica **`America/Mexico_City`**:
dentro del horario, el sistema SHALL indicar que el equipo puede dar seguimiento; fuera del
horario, SHALL indicar que el perfil quedó tomado en cuenta y ofrecer seguimiento dentro del
horario. El sistema SHALL NOT prometer una agenda real mientras no exista sistema de
agendación: SHALL usar "lo dejo registrado para que el equipo te contacte en horario de
atención" y SHALL NOT afirmar "ya quedó agendada tu llamada".

> Nota de implementación: doc-only. El horario operativo (8:00–17:30) vive hoy en
> `current_turn._profile_complete_closing` y en `app/knowledge/business_hours.py`. La ventana de
> `followup/ventana.py` (08:30–20:30, lunes–sábado) es para el **envío async de seguimientos**
> y NO debe confundirse con el horario de oficina. El label `llamada_pendiente` ya existe en
> el catálogo oficial; lo pendiente es emitirlo desde una decisión determinista y registrar
> `scheduling.call_requested`, `scheduling.call_status`, `scheduling.call_window_text` y
> `scheduling.call_window_valid`. El sistema NO debe afirmar que la llamada ya quedó agendada.

#### Scenario: Solicitud de llamada en horario de oficina
- **WHEN** el perfil está completo y el candidato pide una llamada dentro de 8:00–17:30 (`America/Mexico_City`, lunes a viernes)
- **THEN** el sistema indica que el equipo puede dar seguimiento por llamada
- **AND** deja registrado el estado/label de lead para contacto, sin afirmar que la llamada ya quedó agendada

#### Scenario: Solicitud de llamada fuera de horario
- **WHEN** el candidato pide una llamada fuera de 8:00–17:30 (`America/Mexico_City`)
- **THEN** el sistema indica que el perfil quedó tomado en cuenta y ofrece seguimiento dentro del horario
- **AND** no promete una hora agendada

### Requirement: Registro de documentos sin OCR

Cuando el candidato declara que ya subió o enviará documentos, el sistema SHALL agradecer y
registrar para revisión humana, SHALL dejar claro que la validación final la realiza el
equipo, y SHALL NOT afirmar que verificó o validó documentos de forma automática.

> Nota de implementación: requirement doc-only; consistente con la regla de media sin OCR.

#### Scenario: Candidato dice que ya subió todo
- **WHEN** el candidato dice "ya subí todo"
- **THEN** el sistema agradece y registra para revisión humana
- **AND** no afirma haber verificado los documentos automáticamente

### Requirement: No solicitar pagos ni datos sensibles fuera de flujo autorizado

El sistema SHALL NOT solicitar al candidato pagos, depósitos, números de cuenta bancaria,
CURP o NSS completos, comprobantes de pago ni otros datos administrativos sensibles fuera de
un flujo oficial autorizado, y SHALL NOT inventar trámites ni costos. Ante preguntas sobre
trámites con costo, comprobantes, cuentas o datos sensibles, el sistema SHALL derivar a
revisión humana o indicar que el equipo lo confirma por el canal autorizado.

> Nota de implementación: requirement doc-only; no se implementa en este cambio.

#### Scenario: Candidato pregunta por trámite con costo o datos sensibles
- **WHEN** el candidato pregunta por un trámite con costo, comprobante de pago, cuenta bancaria o CURP/NSS
- **THEN** el sistema no pide depósitos ni datos sensibles ni inventa trámites
- **AND** deriva a revisión humana o indica que el equipo lo confirma por el canal autorizado

### Requirement: Decisión operativa unificada (respuesta, nota y labels)

El sistema SHALL derivar la respuesta visible, la nota interna y las labels de una misma
decisión operativa por turno, calculada desde Postgres/lead_memory. La decisión SHALL
considerar el estado del perfil, la intención del candidato, el horario operativo, la
necesidad de llamada, la necesidad de humano y el bloqueo actual. La respuesta visible, la
acción sugerida, el bloqueo actual y las labels SHALL NOT contradecirse entre sí.

> Nota de implementación: doc-only; consistente con `postgres-truth-and-label-sync` y
> `candidate-profile-label-planner` de `multi-intent-migration`.

#### Scenario: Respuesta corta no desalinea la nota ni los labels
- **WHEN** el último mensaje es "5" y el campo pendiente era experiencia
- **THEN** la nota interna no dice "preguntó por documentos"
- **AND** la acción sugerida, el bloqueo actual y las labels son consistentes con "registró experiencia"

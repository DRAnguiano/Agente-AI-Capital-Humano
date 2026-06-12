# message-orchestration (delta)

## ADDED Requirements

### Requirement: Edad temprana con descarte por mayor de 56

El funnel vivo SHALL preguntar la edad inmediatamente después de la ciudad. Si
el candidato declara más de 56 años, el sistema SHALL responder el guion de
descarte cortés aprobado y NO SHALL continuar el perfilamiento.

#### Scenario: Mayor de 56 se descarta
- **WHEN** el candidato responde "tengo 58 años"
- **THEN** el bot responde el guion de descarte y no emite más preguntas del funnel

#### Scenario: 56 o menos continúa
- **WHEN** el candidato responde "tengo 45 años"
- **THEN** el funnel continúa con la siguiente pregunta (tipo de unidad)

### Requirement: Preguntas de vencimiento en lugar de vigencia

El funnel SHALL preguntar "¿Cuándo vence su licencia?" y "¿Cuándo vence su apto
médico?" (no "¿está vigente?"), en turnos SEPARADOS: una pregunta de vigencia
por turno, nunca dos documentos en la misma pregunta. Un "sí" del candidato
NO SHALL validar más de un documento. Si el candidato afirma vigencia sin dar
fecha, el sistema SHALL repreguntar "¿En cuánto tiempo se le vence?" referida
al documento en cuestión.

#### Scenario: Vigente sin fecha provoca repregunta
- **WHEN** el bot preguntó cuándo vence la licencia y el candidato responde "sí, está vigente"
- **THEN** el bot repregunta "¿En cuánto tiempo se le vence su licencia?"

#### Scenario: Un sí no valida dos documentos
- **WHEN** el candidato responde "sí" a una pregunta que mencionara licencia y apto a la vez
- **THEN** el sistema no marca vigente ninguno de los dos sin su fecha/confirmación individual
  (el paso doble queda eliminado: la pregunta de apto llega en el turno siguiente)

### Requirement: Guion fijo de trámite para vencimiento corto

El sistema SHALL preguntar "¿Ya tiene el papel donde lo tramitó?" cuando la
licencia o el apto vence en menos de 3 meses o está vencido. Regla de negocio
(2026-06-12): con la renovación YA en proceso (papel de trámite), el documento
puede considerarse apto y el proceso continúa con `aclaracion_pendiente` para
validación de Capital Humano; SIN trámite en proceso, el documento NO es válido
y el sistema SHALL responder el guion fijo "Por el momento no podemos seguir
con su solicitud; en cuanto tenga el papel de trámite, continuamos", sin
desviarse ante la insistencia del candidato. La regla aplica igual a licencia
y a apto médico, cada uno evaluado por separado.

#### Scenario: Vence pronto sin trámite
- **WHEN** el apto vence en 18 días y el candidato dice que no ha tramitado la renovación
- **THEN** el bot responde el guion fijo y no avanza el funnel

#### Scenario: Vence pronto con trámite
- **WHEN** el candidato confirma que tiene el papel del trámite
- **THEN** el funnel continúa y se marca `aclaracion_pendiente`

#### Scenario: Insistencia no rompe el guion
- **WHEN** el candidato insiste en continuar sin documentos vigentes ni trámite
- **THEN** el bot repite el guion fijo sin ofrecer alternativas

### Requirement: Puente suave tras responder dudas

Cuando el candidato hace preguntas a media precalificación, el sistema SHALL
responder la duda completa y retomar el funnel con un puente suave ("Cuando
guste continuamos con su registro — me decía, ¿...?"), con máximo una pregunta
de funnel por turno.

#### Scenario: Duda de pago no interrumpe con brusquedad
- **WHEN** el candidato pregunta cuánto pagan en medio del perfilamiento
- **THEN** la respuesta resuelve la duda y retoma la pregunta pendiente con puente suave

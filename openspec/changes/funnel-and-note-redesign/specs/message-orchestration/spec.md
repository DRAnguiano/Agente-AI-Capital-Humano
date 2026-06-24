## ADDED Requirements

### Requirement: Funnel como ciclo sobre la request completa

El sistema SHALL tratar el funnel como un ciclo: cada turno SHALL re-evaluar TODA la información
provista por el candidato (incluido lo enviado de golpe o fuera de orden) contra los campos
núcleo, y SHALL emitir únicamente la siguiente pregunta de un campo **no respondido o ambiguo**,
respetando lo ya confirmado y los turnos previos. SHALL NOT re-preguntar un dato ya dado ni
re-saludar. El orden de los campos es una guía, no una secuencia estricta.

#### Scenario: Mensaje con varios datos de golpe
- **WHEN** el candidato escribe "soy Juan, 35 años, operador full 10 años, todo en regla"
- **THEN** el sistema no re-pregunta nombre, edad, unidad ni experiencia
- **AND** pregunta solo lo pendiente/ambiguo (tipo de licencia, ciudad y la vigencia)

#### Scenario: No re-saludar
- **WHEN** el candidato saluda de nuevo en un turno posterior al primero
- **THEN** el sistema no repite la bienvenida y continúa con el campo pendiente

### Requirement: "Todo en regla" marca la vigencia como ambigua

El sistema SHALL tratar afirmaciones globales no específicas ("tengo todo en regla", "todo bien")
como **ambiguas** respecto a la vigencia de licencia y apto: SHALL NOT confirmar vigencia y SHALL
emitir la pregunta de vencimiento correspondiente.

#### Scenario: Afirmación global no confirma vigencia
- **WHEN** el candidato dice "tengo todo en regla"
- **THEN** el sistema no marca licencia ni apto como vigentes
- **AND** pregunta cuándo vence la licencia (o el apto) en turnos separados

### Requirement: Inferencia de unidad desde el tipo de licencia

El sistema SHALL usar el tipo de licencia para orientar la vacante: con licencia **B** SHALL
ofrecer sencillo ("¿quiere una vacante de sencillo?"); con licencia **E** SHALL ofrecer ambas
("¿le interesa una vacante de full o sencillo?"). Si el candidato pide full teniendo solo licencia
B, el sistema SHALL aclarar amablemente que con licencia B la vacante aplicable es sencillo.

#### Scenario: Licencia B ofrece sencillo
- **WHEN** el candidato confirma licencia tipo B
- **THEN** el sistema pregunta si quiere una vacante de sencillo

#### Scenario: Licencia E ofrece ambas
- **WHEN** el candidato confirma licencia tipo E
- **THEN** el sistema pregunta si le interesa full o sencillo

#### Scenario: B pidiendo full se aclara
- **WHEN** el candidato con licencia B dice que quiere full
- **THEN** el sistema aclara que con licencia B la vacante aplicable es sencillo

### Requirement: Documento laboral solicitado según residencia

El sistema SHALL ajustar la pregunta de documento laboral según la ciudad: para candidato local de
la ZM Laguna SHALL aceptar "cartas laborales o semanas cotizadas del IMSS"; para foráneo SHALL
exigir "2 cartas laborales membretadas". SHALL NOT pedir Infonavit. En la etapa de perfilamiento
SHALL pedir solo el documento laboral (INE/RFC/CURP/NSS se piden después de la validación).

#### Scenario: Local acepta IMSS
- **WHEN** el candidato es local de la ZM Laguna y se pregunta el documento
- **THEN** el sistema acepta cartas laborales o semanas cotizadas del IMSS

#### Scenario: Foráneo exige cartas membretadas
- **WHEN** el candidato es foráneo y se pregunta el documento
- **THEN** el sistema exige 2 cartas laborales membretadas

### Requirement: Bienvenida en la primera interacción

El sistema SHALL, solo en la primera interacción del candidato, dar la bienvenida, resolver una
duda si la trae, explicar que se hará una serie de preguntas para evaluar su candidatura (SHALL
NOT pedir documentación en este punto) y pedir el nombre por cortesía. Si el candidato trae una
duda, SHALL resolverla antes de iniciar el perfilamiento; resuelta, SHALL ofrecer continuar
("si le interesa la vacante, ¿podría…?").

#### Scenario: Primera interacción pide nombre
- **WHEN** es el primer mensaje del candidato
- **THEN** el sistema da la bienvenida, anuncia que hará preguntas y pide el nombre
- **AND** no pide documentación

#### Scenario: Duda inicial se resuelve antes de perfilar
- **WHEN** el primer mensaje del candidato es una duda del empleo
- **THEN** el sistema responde la duda y luego ofrece continuar con el perfilamiento

### Requirement: Cierre suave por vencimiento sin trámite

El sistema SHALL, cuando la licencia o el apto están vencidos y el candidato no cuenta con
comprobante de trámite/cita, dar un mensaje amable invitando a retomar cuando tenga el trámite,
detener el perfilamiento automático y canalizar a Capital Humano. El bot SHALL dejar de responder
sin anunciarlo, y la nota SHALL reflejar el motivo. Con comprobante de trámite, SHALL continuar
con `aclaracion_pendiente`.

#### Scenario: Vencido sin trámite cierra suave
- **WHEN** el candidato indica que su licencia está vencida y no la está tramitando
- **THEN** el sistema da el mensaje de retomar a futuro, deja de responder y canaliza a Capital Humano

#### Scenario: Vencido en trámite continúa
- **WHEN** el candidato indica licencia vencida pero con comprobante de cita/trámite
- **THEN** el sistema continúa el perfilamiento con `aclaracion_pendiente`

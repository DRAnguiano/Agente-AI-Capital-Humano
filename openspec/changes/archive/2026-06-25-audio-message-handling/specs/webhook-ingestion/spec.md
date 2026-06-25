## MODIFIED Requirements

### Requirement: Filtrado de eventos procesables

El sistema SHALL procesar únicamente eventos `message_created` de tipo `incoming` con
`account_id` + `conversation_id` presentes. Para mensajes con adjuntos, el sistema SHALL
distinguir el tipo de adjunto:

- **Audio** (`file_type: "audio"`): el sistema SHALL descargar el archivo, transcribirlo
  con Groq Whisper, y encolar el texto resultante como si fuera un mensaje de texto. Si la
  transcripción falla o produce texto vacío, SHALL responder con un mensaje específico de
  audio no procesable y NO encolar.
- **No-audio** (imagen, documento, sticker, video u otro adjunto): el sistema SHALL
  responder con el reply genérico actual de media guard y NO encolar.
- **Sin adjuntos**: el sistema SHALL requerir contenido de texto no vacío para continuar;
  si está vacío, ignora el evento.

#### Scenario: Nota de voz transcrita y encolada

- **WHEN** el payload contiene un adjunto de tipo audio y la transcripción devuelve texto válido
- **THEN** el sistema encola el texto transcrito como `content` del mensaje; el pipeline de
  extracción y orquestación lo procesa igual que cualquier mensaje de texto

#### Scenario: Audio no procesable (transcripción fallida)

- **WHEN** el payload contiene audio pero la descarga o transcripción falla, o el texto
  resultante tiene menos de 3 caracteres
- **THEN** el sistema envía un reply específico ("recibí tu audio pero no pude entenderlo,
  escríbeme en texto") y responde `{"status": "audio_guard", "transcribed": false}`

#### Scenario: Adjunto no-audio (imagen, documento, sticker)

- **WHEN** el payload contiene adjuntos de tipo no-audio
- **THEN** el sistema envía el reply genérico de media guard y responde
  `{"status": "media_guard", ...}` (comportamiento actual sin cambios)

#### Scenario: Evento no procesable

- **WHEN** el evento no es `message_created`, o el `message_type` no es `incoming`, o el
  contenido está vacío y no hay adjuntos
- **THEN** el sistema responde `{"status":"ignored", "reason": <motivo>}` sin encolar nada

#### Scenario: Faltan identificadores obligatorios

- **WHEN** falta `account_id` o `conversation_id`
- **THEN** el sistema responde HTTP 400 con `error: missing_account_or_conversation_id`

#### Scenario: Mensaje entrante válido de texto

- **WHEN** el evento es `message_created`, `incoming`, con texto no vacío e identificadores
- **THEN** el sistema deriva `channel_user_id` y continúa (comportamiento actual sin cambios)

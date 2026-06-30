## MODIFIED Requirements

### Requirement: Filtrado de eventos procesables

El sistema SHALL procesar únicamente eventos `message_created` de tipo `incoming` con
`account_id` + `conversation_id` presentes. Para mensajes con adjuntos, el sistema SHALL
distinguir el tipo de adjunto:

- **Audio** (`file_type: "audio"`): el sistema SHALL descargar el archivo, transcribirlo
  con Groq Whisper, y encolar el texto resultante como si fuera un mensaje de texto. Si la
  transcripción falla o produce texto vacío, SHALL responder con un mensaje específico de
  audio no procesable y NO encolar.
- **Imagen** (`file_type: "image"`): el sistema SHALL descargar el archivo y procesarlo con
  el modelo de visión Groq para extraer datos relevantes de perfilamiento. Si la visión
  devuelve texto, SHALL encolarlo como `content` y continuar el pipeline normal; si no
  devuelve nada útil, SHALL aplicar el fallback acotado y NO encolar.
- **Sticker** (`file_type: "sticker"` o imagen `.webp` reconocida como sticker): el sistema
  SHALL inferir la intención del usuario con visión y traducirla a texto que se encola como
  `content`; si no se puede inferir, SHALL aplicar el fallback acotado y NO encolar.
- **Otro adjunto** (documento, video u otro no soportado): el sistema SHALL aplicar el
  fallback acotado y NO encolar.
- **Sin adjuntos**: el sistema SHALL requerir contenido de texto no vacío para continuar;
  si está vacío, ignora el evento.

El reply enlatado genérico de rechazo de media ("no puedo revisar documentos, imágenes,
audios o stickers… escríbame en texto") SHALL ser eliminado para imágenes y stickers; el
fallback acotado solo SHALL emitirse cuando la visión falla o no produce texto útil.

#### Scenario: Nota de voz transcrita y encolada

- **WHEN** el payload contiene un adjunto de tipo audio y la transcripción devuelve texto válido
- **THEN** el sistema encola el texto transcrito como `content` del mensaje; el pipeline de
  extracción y orquestación lo procesa igual que cualquier mensaje de texto

#### Scenario: Audio no procesable (transcripción fallida)

- **WHEN** el payload contiene audio pero la descarga o transcripción falla, o el texto
  resultante tiene menos de 3 caracteres
- **THEN** el sistema envía un reply específico ("recibí tu audio pero no pude entenderlo,
  escríbeme en texto") y responde `{"status": "audio_guard", "transcribed": false}`

#### Scenario: Imagen con dato de perfilamiento encolada

- **WHEN** el payload contiene un adjunto de tipo imagen y la visión devuelve texto con un
  dato relevante del funnel
- **THEN** el sistema encola ese texto como `content` y el pipeline lo procesa como un
  mensaje de texto, sin enviar el reply enlatado de rechazo

#### Scenario: Sticker convertido en intención encolada

- **WHEN** el payload contiene un adjunto de tipo sticker y la visión infiere una intención
- **THEN** el sistema encola el texto de intención como `content` y el pipeline lo procesa,
  sin enviar el reply enlatado de rechazo

#### Scenario: Imagen/sticker no procesable (fallback acotado)

- **WHEN** el payload contiene imagen o sticker pero la visión falla o no produce texto útil
- **THEN** el sistema emite el fallback acotado y responde `{"status": "media_guard", ...}`
  sin encolar

#### Scenario: Adjunto no soportado (documento/video)

- **WHEN** el payload contiene un adjunto que no es audio, imagen ni sticker
- **THEN** el sistema emite el fallback acotado y responde `{"status": "media_guard", ...}`
  sin encolar

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

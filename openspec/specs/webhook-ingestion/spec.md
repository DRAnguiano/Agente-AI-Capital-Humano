# webhook-ingestion Specification

## Purpose

Recibir mensajes entrantes de Chatwoot (WhatsApp/Telegram) en `POST /chatwoot/webhook`,
autenticarlos y filtrarlos de forma segura, protegerlos contra abuso por volumen, y
encolarlos para procesamiento asíncrono. Es la única puerta de entrada de mensajes de
candidatos al sistema.

## Requirements

### Requirement: Autenticación fail-closed del webhook

El endpoint `POST /chatwoot/webhook` SHALL rechazar toda petición cuyo token no coincida
exactamente con `CHATWOOT_WEBHOOK_TOKEN`, incluyendo el caso en que el token esperado no
esté configurado. El token se acepta vía header `X-Chatwoot-Webhook-Token` o query `token`.

#### Scenario: Token ausente o inválido
- **WHEN** llega una petición sin token o con un token distinto al esperado
- **THEN** el sistema responde HTTP 401 con `{"status":"error","error":"unauthorized"}` y no procesa el mensaje

#### Scenario: Token esperado no configurado
- **WHEN** `CHATWOOT_WEBHOOK_TOKEN` está vacío en el entorno
- **THEN** toda petición es rechazada con 401 (fail-closed), aunque traiga un token

#### Scenario: Token válido
- **WHEN** el token recibido coincide exactamente con el esperado
- **THEN** el sistema continúa con el filtrado del evento

### Requirement: Filtrado de eventos procesables

El sistema SHALL procesar únicamente eventos `message_created` de tipo `incoming` con
`account_id` + `conversation_id` presentes. Para mensajes con adjuntos, el sistema SHALL
distinguir el tipo de adjunto:

- **Audio** (`file_type: "audio"`): el sistema SHALL descargar el archivo, transcribirlo
  con Groq Whisper, y encolar el texto resultante como si fuera un mensaje de texto. Si la
  transcripción falla o produce texto vacío, SHALL responder con un mensaje específico de
  audio no procesable y NO encolar.
- **No-audio** (imagen, documento, sticker, video u otro adjunto): el sistema SHALL
  responder con el reply genérico de media guard y NO encolar.
- **Sin adjuntos**: el sistema SHALL requerir contenido de texto no vacío para continuar;
  si está vacío, ignora el evento.

#### Scenario: Nota de voz transcrita y encolada

- **WHEN** el payload contiene un adjunto de tipo audio y la transcripción devuelve texto válido
- **THEN** el sistema encola el texto transcrito como `content` del mensaje; el pipeline de
  extracción y orquestación lo procesa igual que cualquier mensaje de texto

#### Scenario: Audio no procesable (transcripción fallida)

- **WHEN** el payload contiene audio pero la descarga o transcripción falla, o el texto
  resultante tiene menos de 3 caracteres
- **THEN** el sistema envía `_AUDIO_GUARD_REPLY` y responde `{"status": "audio_guard", "transcribed": false}`

#### Scenario: Adjunto no-audio (imagen, documento, sticker)

- **WHEN** el payload contiene adjuntos de tipo no-audio
- **THEN** el sistema envía el reply genérico de media guard y responde
  `{"status": "media_guard", ...}` (comportamiento previo sin cambios)

#### Scenario: Evento no procesable
- **WHEN** el evento no es `message_created`, o el `message_type` no es `incoming`, o el contenido está vacío y no hay adjuntos
- **THEN** el sistema responde `{"status":"ignored", "reason": <motivo>}` sin encolar nada

#### Scenario: Faltan identificadores obligatorios
- **WHEN** falta `account_id` o `conversation_id`
- **THEN** el sistema responde HTTP 400 con `error: missing_account_or_conversation_id`

#### Scenario: Mensaje entrante válido de texto
- **WHEN** el evento es `message_created`, `incoming`, con texto no vacío e identificadores
- **THEN** el sistema deriva `channel_user_id` (teléfono → contact_id → conversation_id) y continúa

### Requirement: Rate limiting por usuario

Cuando `WEBHOOK_RATE_LIMIT_ENABLED` no esté desactivado, el sistema SHALL limitar a
`WEBHOOK_RATE_LIMIT_MAX_PER_MINUTE` (default 30) los mensajes por `channel_user_id` en
una ventana de 60 segundos, usando un contador en Redis (db 2). Un fallo de Redis nunca
debe bloquear el webhook.

#### Scenario: Dentro del límite
- **WHEN** el usuario envía menos mensajes que el máximo en 60s
- **THEN** el mensaje se procesa normalmente

#### Scenario: Límite excedido
- **WHEN** el contador supera el máximo permitido en la ventana
- **THEN** el sistema responde HTTP 429 con `{"status":"rate_limited","retry_after":60}` y registra `[RATE_LIMITED]`

#### Scenario: Redis no disponible
- **WHEN** el contador de Redis falla
- **THEN** el sistema ignora el error y deja pasar el mensaje (nunca bloquea por el rate limit)

### Requirement: Encolado asíncrono con debounce

Cuando `INBOUND_DEBOUNCE_ENABLED` esté activo, el sistema SHALL encolar el mensaje en
Celery (queue `inbound`) en lugar de procesarlo en el request del webhook, de modo que
el webhook responda rápido y el worker aplique el guard de turno actual y la
deduplicación de mensajes rápidos.

#### Scenario: Debounce activo
- **WHEN** `INBOUND_DEBOUNCE_ENABLED=true` y llega un mensaje válido
- **THEN** el sistema encola el payload (account/conversation/inbox/message/channel_user_id/contenido) y responde sin haber generado la respuesta todavía

#### Scenario: Debounce inactivo
- **WHEN** `INBOUND_DEBOUNCE_ENABLED` está desactivado
- **THEN** el mensaje se procesa de forma síncrona en el mismo request, sin pasar por el worker

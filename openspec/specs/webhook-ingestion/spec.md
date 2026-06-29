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

El sistema SHALL procesar los mensajes entrantes de forma asíncrona vía Celery (queue
`inbound`) **por defecto**: `INBOUND_DEBOUNCE_ENABLED` SHALL tener valor por defecto `true`,
de modo que el webhook responda rápido y el worker aplique el guard de turno actual y la
deduplicación de mensajes rápidos. El path síncrono SHALL quedar reservado únicamente como
modo de diagnóstico explícito (`INBOUND_DEBOUNCE_ENABLED=false`).

#### Scenario: Debounce activo (default)
- **WHEN** llega un mensaje válido y `INBOUND_DEBOUNCE_ENABLED` no está explícitamente en `false`
- **THEN** el sistema encola el payload (account/conversation/inbox/message/channel_user_id/contenido) y responde sin haber generado la respuesta todavía

#### Scenario: Debounce desactivado explícitamente (modo diagnóstico)
- **WHEN** `INBOUND_DEBOUNCE_ENABLED=false`
- **THEN** el mensaje se procesa de forma síncrona en el mismo request, sin pasar por el worker

### Requirement: Ingesta idempotente de mensajes

El sistema SHALL garantizar que un mismo mensaje entrante recibido más de una vez (p. ej.
un reintento del webhook de Chatwoot tras un timeout) no se persista dos veces ni genere
una segunda respuesta al candidato. La persistencia de mensajes (`save_message`) SHALL ser
idempotente: una inserción cuyo mensaje ya exista no debe crear una fila duplicada.

#### Scenario: Reintento del mismo mensaje en el path síncrono
- **WHEN** Chatwoot reintrega el mismo mensaje (mismo identificador / mismo contenido y clave de conversación) y el path síncrono lo procesa por segunda vez
- **THEN** no se inserta una segunda fila en `rh_messages` y no se reenvía el reply al candidato

#### Scenario: Mensajes rápidos duplicados en el worker
- **WHEN** el worker recibe dos payloads con el mismo `message_id`
- **THEN** la deduplicación conserva exactamente una ejecución y descarta la repetida

### Requirement: Durabilidad de la cola de mensajes

El sistema SHALL garantizar entrega al-menos-una-vez de los mensajes encolados: si un
worker muere durante el procesamiento de una tarea, el mensaje SHALL reencolarse para
reintento en lugar de descartarse silenciosamente. La configuración de Celery SHALL usar
`task_acks_late=true` y `task_reject_on_worker_lost=true`.

#### Scenario: Worker cae a media tarea
- **WHEN** el worker termina abruptamente (OOM/restart) mientras procesa un mensaje encolado
- **THEN** el broker reencola el mensaje y otro worker lo procesa, sin pérdida del candidato

#### Scenario: Reintento sin duplicar efectos
- **WHEN** un mensaje se reencola y se vuelve a procesar tras la caída del worker
- **THEN** la ingesta idempotente evita una segunda fila persistida o un reply duplicado


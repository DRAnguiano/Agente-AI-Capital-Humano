## ADDED Requirements

### Requirement: Transcripción de notas de voz vía Groq Whisper

El sistema SHALL transcribir mensajes de audio de WhatsApp usando `client.audio.transcriptions.create`
de Groq (modelo configurable via `GROQ_WHISPER_MODEL`, default `whisper-large-v3-turbo`). La
función `call_groq_transcribe(audio_bytes, filename)` en `app/indexer.py` SHALL aplicar el mismo
patrón de fallback a `GROQ_API_KEY_BACKUP` que el resto de las funciones Groq. Devuelve el
texto transcrito como string, o string vacío si falla.

#### Scenario: Transcripción exitosa

- **WHEN** se recibe un archivo de audio válido (bytes no vacíos, extensión reconocible)
- **THEN** `call_groq_transcribe` devuelve el texto transcrito como string no vacío

#### Scenario: Fallback a clave de respaldo en cuota agotada

- **WHEN** la clave primaria de Groq devuelve `RateLimitError` durante la transcripción
- **THEN** el sistema reintenta con `GROQ_API_KEY_BACKUP` y devuelve el texto transcrito

#### Scenario: Audio vacío o no procesable

- **WHEN** el archivo de audio tiene 0 bytes, o Whisper devuelve texto con menos de 3 caracteres
- **THEN** `call_groq_transcribe` devuelve string vacío; el caller trata el audio como no procesable

### Requirement: Detección de adjunto de audio en el webhook

El sistema SHALL identificar si un payload de Chatwoot contiene un adjunto de tipo audio
inspeccionando `file_type == "audio"` en `payload.attachments` o `payload.message.attachments`.
La función `_detect_audio_url(payload)` SHALL devolver la `data_url` del primer audio encontrado,
o `None` si no hay audio.

#### Scenario: Payload con nota de voz de WhatsApp

- **WHEN** el payload de Chatwoot incluye `attachments: [{file_type: "audio", data_url: "..."}]`
- **THEN** `_detect_audio_url` devuelve la URL del audio

#### Scenario: Payload con imagen u otro adjunto no-audio

- **WHEN** el payload incluye `attachments: [{file_type: "image", ...}]`
- **THEN** `_detect_audio_url` devuelve `None`

#### Scenario: Payload sin adjuntos

- **WHEN** el payload no contiene ningún adjunto
- **THEN** `_detect_audio_url` devuelve `None`

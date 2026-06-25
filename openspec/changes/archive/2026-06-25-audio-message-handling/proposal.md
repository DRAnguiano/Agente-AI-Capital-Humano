## Why

Los operadores de camión en WhatsApp envían notas de voz con frecuencia — es su modo natural
de comunicación. El bot actualmente rechaza todo attachment con un reply genérico
("no puedo revisar imágenes, audios o stickers"), causando abandono cuando el candidato
responde hablando en lugar de escribir. Transcribir el audio con Groq Whisper convierte
cada nota de voz en texto y lo procesa por el pipeline existente, sin cambiar nada del
funnel ni de la lógica de extracción.

## What Changes

- `app/app.py`: el `media_guard` (G4) distingue audio de otros adjuntos.
  - **Audio** (`file_type: "audio"`): descarga el archivo desde la URL de Chatwoot,
    transcribe con `client.audio.transcriptions.create` (modelo `whisper-large-v3-turbo`),
    y encola el texto transcrito como si fuera un mensaje de texto normal.
  - **No-audio** (imagen, documento, sticker, video): conserva el reply genérico actual.
- Si la transcripción falla (timeout, audio corrupto, archivo vacío): responde con un
  mensaje específico de audio no procesable y NO encola (evitar mensajes vacíos).
- Se añade la función `call_groq_transcribe(audio_bytes, filename)` en `app/indexer.py`
  como punto único de llamada a Whisper, con el mismo patrón de fallback a backup key.
- Nueva variable de entorno opcional `GROQ_WHISPER_MODEL` (default: `whisper-large-v3-turbo`).

## Capabilities

### New Capabilities

- `audio-transcription`: Descarga y transcripción de notas de voz vía Groq Whisper,
  integrada en el path de ingesta del webhook de Chatwoot antes del debounce.

### Modified Capabilities

- `webhook-ingestion`: el guard G4 (`media_guard`) pasa a ser tipo-aware; audio toma
  un camino distinto (transcripción + encolar) en lugar del reject genérico.

## Impact

- `app/app.py` — función `_chatwoot_has_media` / bloque `media_guard` en el webhook handler.
- `app/indexer.py` — nueva función `call_groq_transcribe`.
- `.env` — nueva var `GROQ_WHISPER_MODEL` (opcional, con default).
- Sin cambios en Neo4j, Chroma, PostgreSQL, `tasks_chatwoot.py` ni en el pipeline de
  extracción/orquestación: el texto transcrito entra por el mismo camino que cualquier
  mensaje de texto.

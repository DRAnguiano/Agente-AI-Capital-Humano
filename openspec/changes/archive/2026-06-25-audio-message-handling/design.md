## Context

Chatwoot expone los adjuntos en `payload.attachments[].file_type`. Para notas de voz de
WhatsApp el valor es `"audio"` (también `"sticker"` para stickers, `"image"`, `"document"`,
etc.). El campo `data_url` dentro del mismo objeto es la URL desde la que se puede descargar
el archivo de audio (accesible desde el servidor sin autenticación adicional, ya que el token
de Chatwoot está en la URL o se pasa con el header).

El SDK de Groq ya instalado expone `client.audio.transcriptions.create(file=..., model=...)`.
El endpoint acepta un file-like object (bytes + nombre de archivo con extensión reconocible)
y devuelve un objeto con `.text` (string transcrito). Modelos disponibles en Groq:
`whisper-large-v3` (mayor calidad) y `whisper-large-v3-turbo` (más rápido, menor costo).

## Goals / Non-Goals

**Goals:**
- Detectar notas de voz (`file_type: "audio"`) y procesarlas como texto transcrito.
- Usar el mismo pipeline de extracción/orquestación/debounce existente, sin modificarlo.
- Aplicar el patrón de fallback a `GROQ_API_KEY_BACKUP` también en transcripción.
- Responder con mensaje específico si la transcripción falla (no mensaje genérico de media).

**Non-Goals:**
- Transcribir imágenes, documentos, stickers o videos.
- Almacenar los archivos de audio en disco ni en S3.
- Generar respuestas de voz (text-to-speech).
- Detección de idioma o traducción automática.

## Decisions

### D1 — `whisper-large-v3-turbo` como modelo default

Más rápido y suficientemente preciso para español coloquial de México. El español de un
camionero ("llevo 10 años de operador", "manejo full") es vocabulario simple — no requiere
el modelo mayor. `GROQ_WHISPER_MODEL` en `.env` permite sobrescribir.

### D2 — Descarga síncrona del audio dentro del webhook handler

El webhook de Chatwoot es `async def`. La descarga se hace con `httpx.AsyncClient` dentro
del mismo handler (no en Celery), antes de encolar el texto. Esto mantiene la arquitectura
actual: el worker solo recibe texto, no URLs ni bytes.

**Alternativa descartada**: pasar la URL al worker y descargar+transcribir allí — complica el
contrato de la tarea Celery (`tasks_chatwoot.py`) y requiere que el worker tenga acceso de red
a Chatwoot, que puede no estar garantizado en todos los deployments.

### D3 — `call_groq_transcribe` en `app/indexer.py`

Sigue el patrón establecido por `call_groq_json` / `call_groq_with_system`: función pública
que lee `GROQ_API_KEY`, aplica fallback a backup, y devuelve string (texto transcrito o
string vacío si falla). La llamada es síncrona; el caller async usa `asyncio.to_thread`.

### D4 — Reutilizar el campo `content` del evento para pasar el texto transcrito

El webhook handler ya construye `content` (texto del mensaje) antes de encolar. Si hay audio
y la transcripción es exitosa, se sobreescribe `content` con el texto transcrito. El encolado
y todo lo que sigue es idéntico. No se añade metadata especial al mensaje encolado — la fuente
(voz vs texto) no es relevante para el pipeline de extracción.

## Risks / Trade-offs

- [Audio con mucho ruido o silencio] → Whisper puede devolver texto vacío o incorrecto.
  Mitigación: si el texto transcrito tiene menos de 3 caracteres, tratar como fallo y enviar
  el reply de audio no procesable.
- [Latencia extra] La descarga + transcripción añade ~1-3s al path del webhook.
  Aceptable: el debounce del worker ya introduce delay; el candidato espera la respuesta.
- [Costo de tokens Whisper] Whisper en Groq se cobra por segundo de audio, no por token.
  Para notas de voz cortas (<30s) el costo es marginal.
- [URL de Chatwoot con auth] Si `data_url` requiere header `api_access_token`, añadir el
  header en la descarga. Verificar en smoke test.

## Migration Plan

1. Añadir `call_groq_transcribe` en `app/indexer.py`.
2. Añadir helper `_detect_audio_attachment(payload)` en `app/app.py` que devuelve la URL
   del primer audio encontrado, o `None`.
3. Modificar el bloque `media_guard` en `app/app.py`: si hay audio → transcribir y encolar;
   si no-audio → reply genérico actual.
4. Añadir `GROQ_WHISPER_MODEL=whisper-large-v3-turbo` en `.env`.
5. Rebuild worker + API: `docker compose build worker api && docker compose up -d worker api`.
6. Rollback: revertir el bloque `media_guard` a la versión actual — comportamiento idéntico
   al estado previo.

## Open Questions

- ¿El `data_url` de Chatwoot para audios de WhatsApp es público o requiere autenticación?
  → Verificar en el primer smoke test; si requiere auth añadir `api_access_token` header.
- ¿Se quiere loggear el texto transcrito para auditoría? Por ahora no (privacidad).

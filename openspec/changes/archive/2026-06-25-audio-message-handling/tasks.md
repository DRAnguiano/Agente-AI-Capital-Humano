## 1. `app/indexer.py` — función `call_groq_transcribe`

- [x] 1.1 Añadir `call_groq_transcribe(audio_bytes: bytes, filename: str) -> str` en `app/indexer.py`; usa `client.audio.transcriptions.create(file=(filename, audio_bytes), model=GROQ_WHISPER_MODEL)` y devuelve `.text` o `""` si falla
- [x] 1.2 Aplicar el patrón fallback de `_groq_with_fallback`: capturar `GroqRateLimitError` y reintentar con `GROQ_API_KEY_BACKUP`
- [x] 1.3 Añadir constante `GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")` en la sección de config de `app/indexer.py`

## 2. `app/app.py` — detección y transcripción en el webhook

- [x] 2.1 Añadir función `_detect_audio_url(payload: dict) -> str | None` que devuelve `data_url` del primer adjunto con `file_type == "audio"`, o `None`
- [x] 2.2 Añadir reply canned `_AUDIO_GUARD_REPLY` para cuando el audio no pudo procesarse ("Recibí tu audio, pero no pude entenderlo bien. ¿Podrías escribirme en texto lo que me quieres decir?")
- [x] 2.3 Modificar el bloque `media_guard` en el webhook handler: antes del check `_chatwoot_has_media`, llamar a `_detect_audio_url`; si devuelve una URL → rama de transcripción; si devuelve `None` pero `_chatwoot_has_media` → rama de media guard actual
- [x] 2.4 Implementar la rama de transcripción: descargar el audio con `httpx.AsyncClient` desde la URL, llamar `asyncio.to_thread(call_groq_transcribe, audio_bytes, "audio.ogg")`, y si el texto resultante tiene ≥ 3 caracteres → sobreescribir `content` con el texto y continuar el flujo normal
- [x] 2.5 Si la transcripción falla o devuelve texto vacío: enviar `_AUDIO_GUARD_REPLY` al candidato y retornar `{"status": "audio_guard", "transcribed": False, ...}`

## 3. Variables de entorno

- [x] 3.1 Añadir `GROQ_WHISPER_MODEL=whisper-large-v3-turbo` en `.env`

## 4. Tests y verificación

- [x] 4.1 Verificar imports: `docker compose run --rm worker python3 -c "from app.indexer import call_groq_transcribe; print('OK')"`
- [x] 4.2 Rebuild y restart de los servicios: `docker compose build worker api && docker compose up -d worker api`
- [ ] 4.3 Smoke test manual: enviar una nota de voz desde WhatsApp y verificar en logs que `[CHATWOOT_AUDIO_TRANSCRIBE]` aparece y el texto se procesa por el pipeline

## 5. Sync OpenSpec

- [x] 5.1 Actualizar `openspec/specs/webhook-ingestion/spec.md` con el Requirement modificado de filtrado (merge del delta)
- [x] 5.2 Crear `openspec/specs/audio-transcription/spec.md` con los requirements nuevos

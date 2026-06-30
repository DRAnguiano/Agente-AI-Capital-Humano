## 1. Config y modelo de visión

- [x] 1.1 Añadir `GROQ_VISION_MODEL` (default a un modelo de visión Groq vigente) en `app/indexer.py`, leído de env como `GROQ_WHISPER_MODEL`
- [x] 1.2 Documentar `GROQ_VISION_MODEL` en `.env`/`.env.example` y `docker-compose.yml`

## 2. Función de visión en indexer

- [x] 2.1 Implementar `call_groq_vision(image_bytes_or_url, system_prompt, *, ...)` en `app/indexer.py` usando `chat.completions.create` con contenido multimodal (`image_url`)
- [x] 2.2 Encaminar la llamada por el wrapper de fallback de claves existente (primaria → `GROQ_API_KEY_BACKUP` → ORG2)
- [x] 2.3 Devolver string vacío ante fallo, imagen no procesable o respuesta sin contenido útil
- [x] 2.4 Definir los dos system prompts: imagen (solo datos de funnel, vacío si no hay) y sticker (inferir intención → texto corto en español)

## 3. Detección de imagen/sticker en el webhook

- [x] 3.1 Añadir `_detect_image_url(payload)` en `app/app.py` (análogo a `_detect_audio_url`): distinguir `file_type` imagen vs sticker, top-level y `message.attachments`
- [x] 3.2 Helper para clasificar adjunto: audio / imagen / sticker / otro (doc, video)

## 4. Rama de visión en media_guard

- [x] 4.1 Subdividir la rama no-audio del `media_guard`: imagen/sticker → visión; otro → fallback acotado
- [x] 4.2 Imagen: descargar bytes (mismo patrón que audio: headers con `CHATWOOT_API_TOKEN`, timeout) y llamar `call_groq_vision` con el prompt de imagen
- [x] 4.3 Sticker: descargar y llamar `call_groq_vision` con el prompt de intención
- [x] 4.4 Si la visión devuelve texto ≥3 chars → sobreescribir `content` y continuar el pipeline; si no → fallback acotado y `{"status":"media_guard", ...}` sin encolar
- [x] 4.5 Añadir log estructurado `[CHATWOOT_VISION]` (sin almacenar la imagen): tipo, longitud del texto, error

## 5. Eliminar el reply enlatado de rechazo

- [x] 5.1 Eliminar el uso de `_MEDIA_GUARD_REPLY` para imagen y sticker; conservar solo un fallback acotado para fallo de visión y adjuntos no soportados
- [x] 5.2 Verificar que el reply de audio (`_AUDIO_GUARD_REPLY`) queda intacto

## 6. Pruebas

- [x] 6.1 Test unit: `_detect_image_url` distingue imagen, sticker, audio y sin-adjunto
- [x] 6.2 Test unit: `call_groq_vision` aplica fallback de clave en `RateLimitError` (mock)
- [x] 6.3 Test de integración del webhook: imagen con dato de funnel → encola `content` derivado, sin enlatado
- [x] 6.4 Test de integración del webhook: sticker afirmativo → encola texto de intención
- [x] 6.5 Test de integración del webhook: imagen/sticker no procesable → fallback acotado, no encola
- [x] 6.6 Test: adjunto no soportado (doc/video) → fallback acotado

## 7. Validación y despliegue

- [x] 7.1 Validar `openspec` (specs del cambio sin errores) y correr la suite de tests
- [x] 7.2 Probar en staging con imágenes reales (licencia/credencial) y stickers comunes de WhatsApp — INE en vivo (conv 151): `[CHATWOOT_VISION] vision_text_len=64`, extrajo nombre/edad/ciudad
- [x] 7.3 Confirmar en logs que no se emite el enlatado para imagen/sticker exitosos — sin `_MEDIA_GUARD_REPLY`, content derivado encolado

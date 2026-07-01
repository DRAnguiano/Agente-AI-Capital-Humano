## Why

Hoy el bot transcribe notas de voz (Groq Whisper) pero rechaza imágenes y stickers
con un mensaje enlatado ("no puedo revisar documentos, imágenes, audios o stickers…").
Los candidatos suelen mandar fotos (de su licencia, una credencial, un domicilio) o
stickers que expresan intención (sí/no, saludo, pulgar arriba) en lugar de texto. Cada
rechazo es fricción que enfría el lead y obliga al candidato a re-teclear. Queremos que
una imagen o sticker se convierta en datos de perfilamiento o señal de intención que
entren al mismo pipeline del funnel, igual que ya ocurre con el audio.

## What Changes

- Nueva rama de visión en el `media_guard` (G4) del webhook de Chatwoot: cuando el
  adjunto es **imagen** o **sticker** (no audio), en vez de rechazar, se descarga el
  media y se procesa con un modelo de visión de Groq.
- **Imágenes** → se extrae únicamente texto/datos **relevantes al perfilamiento del
  funnel** (ciudad, licencia, apto médico, experiencia, documentos, edad, vehículo).
  El resultado se inyecta como `content` y continúa por el extractor unificado
  (`extract_turn`), exactamente como hace hoy el audio transcrito. Lo no relevante al
  perfilamiento se ignora (es trabajo del reclutador, no del bot).
- **Stickers** → se infiere **intención** del usuario (afirmación, negación, saludo,
  agradecimiento, despedida, emoción) y se traduce a un texto corto en español que
  alimenta el pipeline (p. ej. un pulgar arriba como respuesta a un sí/no del funnel).
- **BREAKING (comportamiento):** se elimina el reply enlatado de rechazo
  `_MEDIA_GUARD_REPLY` ("Por favor… no puedo ver/escuchar"). Solo se conserva un
  fallback acotado cuando la visión falla o no devuelve nada útil.
- Nueva función `call_groq_vision(...)` en `app/indexer.py` con el mismo patrón de
  fallback de claves (primaria → backup → ORG2) que el resto de llamadas Groq.
- Modelo de visión configurable vía env (`GROQ_VISION_MODEL`), análogo a
  `GROQ_WHISPER_MODEL` / `GROQ_MODEL`.

## Capabilities

### New Capabilities
- `image-sticker-vision`: descarga y procesamiento de adjuntos imagen/sticker con un
  modelo de visión Groq para (a) extraer datos relevantes de perfilamiento del funnel y
  (b) inferir intención del usuario, normalizando el resultado a texto que entra al
  pipeline de extracción/orquestación. Incluye fallback de claves y manejo de fallo.

### Modified Capabilities
- `webhook-ingestion`: el ruteo de media en `media_guard` deja de rechazar imágenes y
  stickers; ahora los deriva a la rama de visión y elimina el reply enlatado de rechazo,
  conservando solo un fallback cuando la visión no produce texto útil.

## Impact

- `app/app.py`: rama no-audio del `media_guard` (líneas ~1145-1184), constante
  `_MEDIA_GUARD_REPLY`, nuevos helpers `_detect_image_url` / clasificación
  imagen-vs-sticker sobre `attachments`.
- `app/indexer.py`: nueva `call_groq_vision(...)` y constante `GROQ_VISION_MODEL`;
  reutiliza el wrapper de fallback de claves existente.
- Variables de entorno / `.env` y `docker-compose.yml`: `GROQ_VISION_MODEL`.
- Specs: nueva `image-sticker-vision`, delta de `webhook-ingestion`.
- Dependencias: ninguna nueva (Groq ya disponible; modelos de visión soportados por la
  cuenta). Costo/latencia adicional por llamada de visión solo cuando llega media.

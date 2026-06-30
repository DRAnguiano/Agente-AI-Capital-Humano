## Context

El webhook de Chatwoot (`app/app.py`) ya tiene un `media_guard` (G4) que ramifica por tipo
de adjunto antes de `empty_content`. Hoy:

- **Audio** → descarga + `call_groq_transcribe` (Groq Whisper) → si hay texto ≥3 chars
  sobreescribe `content` y sigue el pipeline; si no, emite `_AUDIO_GUARD_REPLY` y corta.
- **No-audio** (imagen, doc, sticker, video) → emite `_MEDIA_GUARD_REPLY` enlatado y corta.

Los helpers existentes son `_chatwoot_has_media(payload)` y `_detect_audio_url(payload)`,
ambos agnósticos al canal e inspeccionando `attachments` top-level y `message.attachments`
con `file_type`/`data_url`. El extractor unificado (`extract_turn` → `TurnExtraction`) es la
única pasada LLM de perfilamiento, y Groq se invoca vía un wrapper con fallback de claves
(primaria → `GROQ_API_KEY_BACKUP` → ORG2) en `app/indexer.py`.

Este cambio reutiliza ese andamiaje: añade una rama de visión paralela a la de audio, que
convierte imagen/sticker en `content` textual y deja correr el pipeline existente sin
tocar la extracción ni la orquestación.

## Goals / Non-Goals

**Goals:**
- Convertir imágenes en texto de **datos de perfilamiento del funnel** y stickers en
  **texto de intención**, inyectándolos como `content` para el pipeline existente.
- Reutilizar el patrón de fallback de claves Groq y el flujo de descarga de media del audio.
- Eliminar el reply enlatado de rechazo para imagen/sticker, dejando solo un fallback
  acotado para fallo de visión.
- Mantener visión detrás de env config (`GROQ_VISION_MODEL`) para poder apagarla/cambiar
  modelo sin redeploy de código.

**Non-Goals:**
- OCR documental exhaustivo o validación legal de documentos (eso es trabajo del reclutador).
- Cambiar el extractor unificado, los catálogos de validación o la orquestación del funnel.
- Procesar video o documentos PDF (siguen al fallback acotado).
- Almacenar las imágenes; solo se procesan en memoria para derivar texto.

## Decisions

**1. Rama de visión dentro del `media_guard`, no un módulo nuevo de ingreso.**
Se añade un `_detect_image_url(payload)` (análogo a `_detect_audio_url`) que distingue
`file_type in {"image","file"}` y stickers (`file_type == "sticker"` o `.webp`). La rama
no-audio actual se subdivide: imagen/sticker → visión; resto → fallback. Alternativa
descartada: un pre-procesador separado antes del webhook — añade superficie sin beneficio,
y el `media_guard` ya tiene los IDs y el cliente HTTP a mano.

**2. `call_groq_vision` en `app/indexer.py` reusando el wrapper de fallback.**
Misma firma de estilo que `call_groq_transcribe`/`call_groq_json`: recibe bytes o URL de la
imagen + un prompt de sistema, llama `chat.completions.create` con contenido multimodal
(`image_url`), y pasa por el mismo helper de fallback de claves. Modelo vía
`GROQ_VISION_MODEL` (default un modelo de visión Groq vigente). Alternativa descartada: un
proveedor de visión externo — rompe el patrón de claves único y agrega dependencia/secreto.

**3. Dos prompts de sistema distintos: imagen vs sticker.**
- Imagen: "extrae SOLO datos del funnel (ciudad, vehículo, licencia, apto, experiencia,
  documentos, edad/nombre); si no hay, responde vacío". Devuelve frase en español que el
  extractor unificado ya sabe parsear.
- Sticker: "infiere intención (sí/no/saludo/gracias/despedida/emoción) y devuélvela como
  texto corto en español". Esto permite que un pulgar arriba responda un sí/no del funnel.
Mantener prompts separados evita que el modelo invente facts a partir de un sticker.

**4. Reutilizar el umbral y el patrón del audio para decidir "útil".**
Si `call_groq_vision` devuelve texto ≥3 chars → sobreescribe `content` y sigue el pipeline
(idéntico al audio). Si vacío/falla → fallback acotado y corta. Así el comportamiento es
simétrico y testeable con los mismos escenarios.

**5. Eliminar `_MEDIA_GUARD_REPLY` enlatado solo cuando la visión esté viva.**
Se conserva una sola línea de fallback acotado (puede ser el mismo texto reducido) emitida
únicamente en fallo de visión o adjunto no soportado (doc/video). El borrado del enlatado
para imagen/sticker es el cambio de comportamiento BREAKING declarado en la propuesta.

## Risks / Trade-offs

- [Latencia/costo: cada imagen añade una llamada LLM de visión] → solo ocurre cuando llega
  media (poco frecuente vs texto); timeout acotado en la descarga y la llamada, igual que
  audio.
- [El modelo de visión alucina un fact que no está en la imagen] → el prompt restringe a
  campos del funnel y pide vacío si no hay; además todo pasa por la validación determinista
  del extractor unificado (catálogos/rangos), que descarta valores inválidos.
- [Sticker mal interpretado responde algo no deseado al funnel] → intención se traduce a
  texto y entra al pipeline normal, que ya maneja respuestas ambiguas; si no hay confianza,
  devuelve vacío y cae al fallback.
- [Modelo de visión Groq cambia de nombre/disponibilidad] → `GROQ_VISION_MODEL` configurable
  por env; si falla, fallback acotado (degradación equivalente al estado actual de rechazo).
- [Imágenes grandes / formatos raros] → límite de tamaño y manejo de excepción en la
  descarga; cualquier error cae al fallback sin romper el webhook.

## Migration Plan

1. Añadir `GROQ_VISION_MODEL` a `.env`/compose (con default seguro).
2. Implementar `call_groq_vision` y helpers de detección; mantener el enlatado vigente
   detrás de la nueva rama hasta validar.
3. Validar en staging con imágenes reales (licencia, credencial) y stickers comunes.
4. Eliminar `_MEDIA_GUARD_REPLY` para imagen/sticker una vez confirmada la visión.
5. Rollback: revertir a la rama no-audio actual (reactivar enlatado) si la visión degrada;
   no hay migración de datos.

## Open Questions

- ¿Qué modelo de visión Groq fijar como default vigente al implementar? (confirmar el id
  soportado por la cuenta al momento del apply).
- ¿Stickers animados (.webp multi-frame) requieren extraer un solo frame antes de enviar?
- ¿Conviene loggear (sin almacenar la imagen) el texto derivado por visión para auditoría,
  igual que `[CHATWOOT_AUDIO_TRANSCRIBE]`?

## ADDED Requirements

### Requirement: Procesamiento de imágenes con modelo de visión Groq

El sistema SHALL procesar adjuntos de tipo imagen recibidos vía Chatwoot enviándolos a un
modelo de visión de Groq (configurable vía `GROQ_VISION_MODEL`). La función
`call_groq_vision(image_bytes_or_url, prompt, ...)` en `app/indexer.py` SHALL aplicar el
mismo patrón de fallback de claves (primaria → `GROQ_API_KEY_BACKUP` → ORG2) que el resto
de las funciones Groq. El prompt de visión SHALL pedir únicamente datos **relevantes al
perfilamiento del funnel** (ciudad, tipo de vehículo sencillo/full, licencia A/B/E, apto
médico, experiencia, documentos, edad/nombre) y SHALL descartar todo lo demás, devolviendo
texto en español listo para el extractor unificado, o string vacío si falla o no hay nada
relevante.

#### Scenario: Imagen con dato de perfilamiento

- **WHEN** se recibe una imagen legible que contiene un dato relevante del funnel
  (p. ej. la foto de una licencia tipo E)
- **THEN** `call_groq_vision` devuelve un texto en español con ese dato
  (p. ej. "licencia tipo E") que entra al pipeline de extracción como `content`

#### Scenario: Imagen sin datos de perfilamiento

- **WHEN** la imagen no contiene información relevante al perfilamiento (p. ej. un paisaje)
- **THEN** `call_groq_vision` devuelve string vacío y la imagen se trata como no procesable

#### Scenario: Fallback de clave en cuota agotada

- **WHEN** la clave primaria de Groq devuelve `RateLimitError` durante la llamada de visión
- **THEN** el sistema reintenta con `GROQ_API_KEY_BACKUP` (y ORG2 si aplica) y devuelve el
  resultado, igual que las demás funciones Groq

### Requirement: Inferencia de intención desde stickers

El sistema SHALL interpretar adjuntos de tipo sticker (típicamente `.webp` de WhatsApp)
infiriendo la **intención del usuario** (afirmación, negación, saludo, agradecimiento,
despedida, emoción positiva/negativa) y traduciéndola a un texto corto en español que
alimenta el pipeline de orquestación, de modo que un sticker pueda responder a una pregunta
del funnel. Si la intención no puede inferirse, SHALL devolver string vacío.

#### Scenario: Sticker afirmativo como respuesta al funnel

- **WHEN** el sistema acaba de hacer una pregunta sí/no del funnel y el candidato responde
  con un sticker de pulgar arriba o de "sí"
- **THEN** la intención se traduce a un texto afirmativo (p. ej. "sí") que el pipeline
  procesa como la respuesta del candidato

#### Scenario: Sticker de saludo/emoción sin dato

- **WHEN** llega un sticker de saludo o emoción sin relación con una pregunta pendiente
- **THEN** la intención se traduce a un texto breve acorde que entra al pipeline normal de
  conversación (no fuerza un fact de perfilamiento)

#### Scenario: Sticker no interpretable

- **WHEN** la intención del sticker no puede inferirse con confianza
- **THEN** la función devuelve string vacío y el adjunto se trata como no procesable

### Requirement: Solo se capturan datos de perfilamiento, no trabajo de reclutador

El procesamiento de visión SHALL limitarse a extraer datos del **funnel de perfilamiento**.
Cualquier contenido que corresponda al trabajo posterior de un agente de reclutamiento
(p. ej. validación documental detallada, decisiones de contratación, datos no incluidos en
el perfil canónico) SHALL ser ignorado por el sistema y NO SHALL convertirse en facts.

#### Scenario: Imagen con información mixta

- **WHEN** una imagen contiene tanto un dato del funnel como información ajena al
  perfilamiento
- **THEN** el sistema extrae solo el dato del funnel e ignora el resto

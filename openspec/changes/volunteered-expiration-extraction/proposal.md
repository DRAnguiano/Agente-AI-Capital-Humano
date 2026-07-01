## Why

Cuando el candidato **ofrece la vigencia de su licencia o apto médico antes de que el funnel la pregunte** (p. ej. "tengo licencia tipo E y vence en un año"), el dato se **descarta** y el funnel la vuelve a pedir — una re-pregunta molesta observada en producción. La causa es la regla D3 del extractor: `license.expiration_text` y `medical.apto_expiration_text` son campos de texto libre que solo se persisten si el LLM marcó `explicit_marker` o si el candidato respondía una pregunta directa (`answered_direct_question`). El extractor **sí extrae el valor** ("un año") pero deja `explicit_marker=False`, así que una vigencia voluntariada temprano se pierde. Es independiente del modelo (70b y qwen igual).

## What Changes

- **Conservar vigencias claramente enunciadas aunque se ofrezcan antes de preguntarlas.** Cuando el mensaje del candidato expresa de forma inequívoca la vigencia de licencia o apto (verbo/sustantivo de vencimiento — "vence", "vigencia", "vencimiento", "caduca" — junto a un plazo o fecha), el fact `license.expiration_text` / `medical.apto_expiration_text` SHALL persistirse aunque `answered_direct_question` sea falso, tratándolo como enunciado explícito.
- La detección de "vigencia claramente enunciada" es **determinista** (patrón sobre el texto), no depende de que el LLM marque `explicit_marker` (que es inconsistente).
- No cambia el manejo de no-respuestas/evasivas (siguen inválidas) ni el de otros campos de texto libre (`candidate.name` conserva su guarda actual).

## Capabilities

### New Capabilities
- (Ninguna)

### Modified Capabilities
- `unified-turn-extraction`: los campos de vigencia (`license.expiration_text`, `medical.apto_expiration_text`) se persisten cuando el candidato enuncia claramente la vigencia, aunque no estuviera respondiendo una pregunta directa del funnel.

## Impact

- **Código afectado**: `app/knowledge/turn_extractor.py` (`validate_extraction`, regla D3 para los campos de vigencia). Posible helper determinista de detección de vigencia enunciada.
- **Efecto**: se elimina la re-pregunta de licencia/apto cuando el candidato ya dio la vigencia de forma voluntaria en un turno compuesto o temprano.
- **Riesgo**: bajo; solo relaja D3 para vigencias claramente enunciadas (patrón acotado), sin tocar la validación de no-respuestas ni otros campos.
- **Sin cambio de modelo ni proveedor LLM.**

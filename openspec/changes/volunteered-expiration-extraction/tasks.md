## 1. Detección determinista de vigencia enunciada

- [x] 1.1 Añadir helper puro `_states_expiration(text)` en `turn_extractor.py`: True si el texto normalizado contiene un marcador de vencimiento inequívoco ("vence", "vencí", "vigencia", "vencimiento", "caduca", "caducidad") — sin exigir que el LLM marque `explicit_marker`.

## 2. Relajar D3 para campos de vigencia

- [x] 2.1 En `extract_turn` (Capa 1, donde SÍ está el mensaje): helper `_mark_stated_expirations(fields, message)` fija `explicit_marker=True` en las vigencias con valor cuando `_states_expiration(message)`; así D3 (en `validate_extraction`) las conserva sin cambiar su firma.
- [x] 2.2 Mantener `is_valid_expiration_text` sobre el valor (no-respuestas/evasivas siguen fuera).
- [x] 2.3 No tocar la guarda de `candidate.name`.

## 3. Pruebas

- [x] 3.1 Test: "tengo licencia tipo E y vence en un año" con last_bot = pregunta de nombre → persiste `license.expiration_text`.
- [x] 3.2 Test: "mi apto médico vence en 8 meses y tengo cartas" → persiste `medical.apto_expiration_text`.
- [x] 3.3 Test: "no sé cuándo vence" → NO persiste vigencia.
- [x] 3.4 Test: `candidate.name` sin marcador/pregunta → sin cambio (regresión).

## 4. Validación y verificación

- [x] 4.1 `openspec validate volunteered-expiration-extraction` sin errores; suite en verde en contenedor.
- [x] 4.2 Verificación en vivo (número nuevo): dar "licencia E, vence en un año" antes de que lo pregunten → el funnel avanza sin re-preguntar la vigencia.

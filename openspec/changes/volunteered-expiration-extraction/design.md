## Context

`validate_extraction` (`turn_extractor.py`) aplica la regla D3: un campo en `_FREE_TEXT_FIELDS` (`candidate.name`, `license.expiration_text`, `medical.apto_expiration_text`) solo se promueve si `fv.explicit_marker or fv.answered_direct_question`. `explicit_marker` lo decide el LLM y es inconsistente para vigencias; `answered_direct_question` es verdadero solo si el último mensaje del bot preguntó ese campo. Por eso una vigencia ofrecida antes de tiempo ("tengo licencia E y vence en un año" cuando el bot preguntó el nombre) se descarta pese a que el valor sí se extrajo.

Verificado: mismo mensaje con `last_bot`=pregunta de nombre → `value='un año', explicit=False, answered=False` → descartado; con `last_bot`=pregunta de licencia/vigencia → `answered=True` → conservado.

## Goals / Non-Goals

**Goals:**
- Persistir `license.expiration_text` / `medical.apto_expiration_text` cuando el candidato **enuncia claramente** la vigencia, aunque no se le haya preguntado.
- Detección determinista y model-agnostic (no depender de `explicit_marker`).

**Non-Goals:**
- NO relajar D3 para `candidate.name` (mantiene su guarda: nombres sueltos ambiguos no deben colarse).
- NO aceptar no-respuestas/evasivas como vigencia (siguen inválidas vía `is_valid_expiration_text`).
- NO cambiar el orden del funnel ni la política de vigencia mínima (>3 meses).

## Decisions

**D1 — Guarda determinista de "vigencia enunciada".** En `validate_extraction`, para los dos campos de vigencia, tratar el valor como explícito si el texto del turno contiene un marcador de vencimiento inequívoco ("vence", "vigencia", "vencimiento", "caduca", "venc*") acompañado del valor extraído (plazo/fecha). Se implementa como helper puro `_states_expiration(text)` sobre el mensaje normalizado. *Alternativa descartada*: instruir al LLM para que marque `explicit_marker` — ya se probó inconsistente (qwen 53%, y hasta el 70b deja explicit_marker=False aquí).

**D2 — Reusar la validación de valor existente.** El valor debe seguir pasando `is_valid_expiration_text` (no-respuestas siguen fuera). La guarda nueva solo sustituye la condición `explicit_marker or answered_direct_question` para estos dos campos cuando hay marcador de vencimiento en el texto.

**D3 — Alcance acotado a los campos de vigencia.** El cambio toca solo `license.expiration_text` y `medical.apto_expiration_text`; `candidate.name` conserva su comportamiento.

## Risks / Trade-offs

- **Falsos positivos** (capturar una vigencia que el candidato no afirmó) → Mitigación: exigir el marcador de vencimiento textual + valor válido; sin marcador, sigue la regla D3 original.
- **Frases ambiguas** ("no sé cuándo vence") → Mitigación: `is_valid_expiration_text` ya rechaza no-respuestas; el marcador sin valor válido no promueve nada.

## Migration Plan

1. Añadir helper `_states_expiration(text)` (patrón determinista de vencimiento).
2. En `validate_extraction`, para los dos campos de vigencia, promover si `explicit_marker or answered_direct_question or _states_expiration(mensaje)`.
3. Tests: vigencia voluntariada temprano → se persiste; no-respuesta → sigue fuera; nombre suelto → sin cambio.
4. Verificación en vivo: dar "licencia E, vence en un año" antes de que lo pregunten → no re-pregunta.

## Open Questions

- (Ninguna; alcance acotado y mecanismo verificado.)

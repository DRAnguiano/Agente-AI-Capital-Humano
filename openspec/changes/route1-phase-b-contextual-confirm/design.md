## Context

Route-1 ya tiene toda la lógica de resolución contextual funcionando en shadow. El flujo vivo en `handle_message` (knowledge_orchestrator.py) llama a `resolve_route1` después de generar la respuesta, solo para logguear. El cambio es mínimo: mover esa llamada antes del `_build_funnel_nudge` y usar su resultado.

Flujo actual:
```
1. classify intent → friendly_smalltalk
2. _answer_friendly_message → "Eso es lo que necesitamos..."
3. _build_funnel_nudge(lead_memory_before) → "¿Cuenta con cartas?" (repite)
4. [después] resolve_route1 → confirmed=cartas  ← demasiado tarde
```

Flujo nuevo:
```
1. classify intent → friendly_smalltalk
2. resolve_route1(message, fresh_keys) → confirmed=documents.proof=cartas
3. _build_funnel_nudge(lead_memory + route1_fact) → siguiente campo ✓
4. reply = ack_route1 + nudge → "Cartas anotadas. ¿Cuándo vence su apto médico?"
5. [log] ROUTE1_ACTIVE (antes era ROUTE1_SHADOW)
```

## Goals / Non-Goals

**Goals:**
- El campo confirmado por route-1 nunca se vuelve a preguntar en el mismo turno.
- La respuesta incluye un ack determinista del dato confirmado antes del siguiente nudge.
- Sin LLM extra: el ack es un string fijo por campo (`"Cartas anotadas."`, `"6 años de experiencia, anotado."`, etc.).

**Non-Goals:**
- No cambiar el clasificador de intención — puede seguir diciendo `friendly_smalltalk`.
- No expandir el allowlist de route-1 (quedan fuera `license.type`, `medical.apto_status`, `candidate.city`, `candidate.name`).
- No persistir el hecho confirmado por route-1 al DB en este cambio — eso ya lo hace el `guard_context` de `tasks_chatwoot` (actual_turn). Solo se inyecta en `active_facts` para el nudge de este turno.

## Decisions

**D1: Inyección vía `pre_validated_facts` existente**
`_build_funnel_nudge` ya acepta `pre_validated_facts: list | None` que se mezcla en `active_facts`. Pasar el hecho de route-1 en ese formato `[{"fact_group": "documents", "fact_key": "proof", "fact_value": "cartas"}]` es el cambio más pequeño posible — sin tocar la firma de la función.

**D2: Ack strings deterministas por campo en `route1_contextual.py`**
Definir un dict `ROUTE1_ACK` en `route1_contextual.py`:
```python
ROUTE1_ACK = {
    "documents.proof":        "Cartas anotadas.",
    "experience.years":       "{value} años de experiencia, anotado.",
    "experience.vehicle_type": "Entendido, {value}.",
}
```
El orquestador usa `ROUTE1_ACK[field].format(value=value)` para construir el prefijo. Si el campo no tiene ACK (no debería ocurrir dado el allowlist), usa `"Entendido."` como fallback.

**D3: El ack reemplaza el friendly_result si route-1 confirma**
Si route-1 confirma un campo, el prefijo del ack ya cumple la función del comentario amistoso. Suprimir la llamada a `_answer_friendly_message` en ese caso evita respuestas redundantes. El candidato recibe: `"Cartas anotadas. ¿Cuándo vence su apto médico?"` — directo, sin el canned "Eso es lo que necesitamos...".

## Risks / Trade-offs

- [Riesgo] route-1 confirma un campo incorrecto (falso positivo). → Mitigación: el allowlist es conservador (3 campos), el clasificador ya distingue negación, y `classify_short_answer` tiene umbrales altos. En caso de falso positivo, el candidato puede corregir en el siguiente mensaje.
- [Riesgo] El candidato responde "Es correcto señor" a algo que NO era la pregunta del funnel. → Mitigación: `read_current_asked_field_keys` solo lee la metadata persistida del último mensaje del bot que tuvo un nudge — si el último turno no tuvo nudge, `fresh_keys` es None y route-1 no actúa.

## Migration Plan

1. Agregar `ROUTE1_ACK` dict en `route1_contextual.py`.
2. En `handle_message`, mover la llamada a `resolve_route1` al bloque donde se calcula `_build_funnel_nudge` (antes de él).
3. Si `r1["status"] == "confirmed"` y el campo está en el allowlist:
   a. Construir `route1_extra_fact` en formato `pre_validated_facts`.
   b. Pasar `route1_extra_fact` a `_build_funnel_nudge` (merge con `_pre_validated`).
   c. Reemplazar `friendly_result` por el ack string de `ROUTE1_ACK`.
4. Renombrar log de `[ROUTE1_SHADOW]` a `[ROUTE1_ACTIVE]` cuando actúa.
5. Reiniciar `api` y `worker`.
6. Rollback: comentar el bloque de inyección route-1 — sin cambio de esquema.

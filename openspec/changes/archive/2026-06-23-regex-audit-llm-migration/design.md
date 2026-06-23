## Context

El bot ya migró los extractores principales de perfil a LLM T=0 (`llm-first-extraction`). Quedaron ~12 patrones regex "MIGRABLE" en el grafo de conocimiento que intentan extraer significado del lenguaje natural. Estos patrones:

1. Son frágiles ante typos y variantes coloquiales nuevas.
2. Fallan silenciosamente (no lanzan excepción, devuelven un resultado incorrecto).
3. Generan deuda acumulativa: cada typo nuevo requiere un cambio de código.

El audit completo (2026-06-23) categorizó cada regex en LEGÍTIMO / MIGRABLE / AMBIGUO. Esta spec implementa los MIGRABLE.

**Invariante consolidada:** `normalize_text()` es puramente estructural (Contrato A). Los llamados LLM siempre reciben `message` (original con ñ/acentos), nunca `text` (normalizado). `text` solo se usa para guardas de contexto y búsquedas en catálogo.

## Goals / Non-Goals

**Goals:**
- Migrar los ~12 patrones MIGRABLE a clasificadores/extractores LLM T=0
- Eliminar typo-lists hardcodeadas de código operativo (`"bacante"`, `"sensillo"`)
- Mantener cobertura de tests: cada comportamiento migrado tiene test con `skipif(_NO_GROQ)` donde sea LLM-dependiente
- Suite verde (Groq-free) sin regresiones

**Non-Goals:**
- No tocar patrones LEGÍTIMO (enums de dominio, guardas estructurales, output cleanup)
- No migrar lógica de Neo4j ni RAG
- No cambiar el contrato de hechos de negocio (`candidate.city`, `experience.vehicle_type`, etc.)

## Decisions

### D1: Orden de migración por riesgo

Prioridad P1 (impacto en producción frecuente):
1. `_EMBEDDED_QUESTION_RE` en `current_turn.py` — el patrón más complejo y frágil
2. `_MEMORY_CLAIM_PATTERNS` en `memory_guard.py` — 6 patrones de speech-act
3. `_has_renewal_proof` en `profile_extractor.py` — polaridad de renovación

Prioridad P2 (baja frecuencia o bajo impacto):
4. `_expiry_within_three_months` en `current_turn.py`
5. `_CALL_REQUEST_RE` / `_CALL_NEG_RE` en `profile_extractor.py`
6. `_ya_reclamo` guard en `current_turn.py`
7. `_NO_ROAD_EXPERIENCE_RE` / `_PAID_SENSITIVE_RE` en `knowledge_orchestrator.py`

### D2: El guard `_conditional_si` permanece como regex

La regex `r"^si\s+(?:me|te|...)\s+(?:cuenta|cuentas|...)\b"` en `current_turn.py` es un guard de baja latencia que previene que el ack más frecuente ("sí") dispare mal la confirmación contextual. Migrarla a LLM añadiría latencia en cada turno. **Permanece como regex** hasta que haya evidencia de falsos positivos en producción.

### D3: Typos en catálogos se eliminan DESPUÉS de migrar el extractor correspondiente

`"sensillo"/"censillo"` en `VEHICLE_TERMS` y `"bacante"/"vancate"` en `CAMPAIGN_INTEREST_TERMS` se eliminan solo cuando el extractor correspondiente haya sido migrado a LLM y los tests sean verdes. El catálogo actúa como red de seguridad temporal.

### D4: `_EMBEDDED_QUESTION_RE` migra a clasificador LLM binario

El patrón detecta si el mensaje contiene una pregunta de negocio embebida (sin "?"). Se migra a un prompt clasificador:
```
¿El candidato hace una pregunta sobre condiciones laborales (rutas, pago, requisitos, boletos)?
Responde SOLO JSON: {"has_business_question": true | false}
```
La guarda de contexto (palabras como "rutas", "pagan") sigue siendo necesaria para activar el LLM y evitar llamadas innecesarias.

### D5: Pattern de migración estándar

```python
# ANTES (regex)
if re.search(_SOME_PATTERN, text):
    facts["key"] = "value"

# DESPUÉS (LLM T=0)
_GUARD_HINTS = ("palabra_clave_1", "palabra_clave_2")
if any(h in text for h in _GUARD_HINTS):
    try:
        raw = call_groq_json(message, _SOME_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
        val = json.loads(raw).get("field")
        if val:
            facts["key"] = val
    except Exception:
        pass  # fail-safe: no fact
```

## Risks / Trade-offs

| Riesgo | Mitigación |
|--------|------------|
| Latencia: cada LLM call añade ~200-400ms | Guardas de contexto (keyword hints) antes de cada call; solo se invoca si hay señal |
| No-determinismo T=0 vs regex determinista | Prompts con ejemplos explícitos + tests de contrato (no del literal del mensaje) |
| `_GROQ_API_KEY` ausente en test CI | `@pytest.mark.skipif(_NO_GROQ, ...)` en todos los tests LLM-dependientes |
| `_PAID_SENSITIVE_RE` es guardia de seguridad | Mantener la regex como primera línea; LLM como segunda verificación (no reemplazar) |

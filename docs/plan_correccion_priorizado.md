# Plan de Corrección Priorizado — READ ONLY

**Basado en:** Auditoría de Incongruencias 2026-06-17 (`docs/auditoria_incongruencias_2026-06-17.md`)  
**Propósito:** Documentar el orden y enfoque recomendado para resolver cada hallazgo  
**Tipo:** READ ONLY — este documento no modifica ningún archivo del proyecto

---

## Criterios de Priorización

Cada corrección se clasifica por:

| Factor | Peso |
|---|---|
| **Impacto funcional** (¿produce errores visibles al candidato?) | Alto |
| **Impacto en datos** (¿corrompe o pierde datos del lead?) | Alto |
| **Esfuerzo** (líneas a cambiar, riesgo de regresión) | Variable |
| **Dependencia** (¿bloquea otras correcciones?) | Variable |

Orden de ejecución recomendado:
1. **Fase 1 — Bugs funcionales activos** (producen errores ahora)
2. **Fase 2 — Contradicciones semánticas** (comportamiento impredecible)
3. **Fase 3 — Inconsistencias arquitectónicas** (diseño frágil/deuda técnica)
4. **Fase 4 — Refinamientos** (mejora continua)

---

## FASE 1 — Bugs funcionales activos

### 1.1 🔴 Alinear `license.type` ↔ `license.category` (Hallazgo #4)

**Problema:** `memory_guard.py` y `intent_orchestrator.py` chequean `license.type` para determinar si la licencia está completa. `profile_extractor.py` escribe `license.category`. El funnel NUNCA encuentra la licencia → pregunta eternamente.

**Opción A — Unificar hacia `license.type` (recomendada):**
| Archivo | Cambio |
|---|---|
| `app/lead_memory/profile_extractor.py` | En lugar de escribir `license.category`, escribir `license.type` con el mismo valor |
| `app/*` | Buscar referencias a `license.category` y cambiarlas a `license.type` |
| `app/knowledge/current_turn.py` | Si usa `license.category`, actualizar a `license.type` |
| `app/chatwoot_note_sync.py` | Si usa `license_category` en SQL/lectura, actualizar |

**Opción B — Alinear el funnel hacia `license.category`:**
| Archivo | Cambio |
|---|---|
| `app/knowledge/memory_guard.py` | Cambiar `FUNNEL_FIELD_FACT_KEYS["license"]` a `("license.category", "license.status")` |
| `app/knowledge/intent_orchestrator.py` | Cambiar `complete` lambda a `_has(f, "license.category")` |
| `app/knowledge/intent_classifier.py` | Cambiar `ANSWER_FIELDS` de `"license.type"` a `"license.category"` |

**Riesgo de regresión:** Alto — afecta el pipeline completo. Probar con leads reales.

---

### 1.2 🔴 Unificar criterio de "perfil_listo" (Hallazgo #3)

**Problema:** Tres módulos usan criterios distintos para decidir si un perfil está completo.

**Acciones recomendadas:**

| Archivo | Cambio |
|---|---|
| `app/chatwoot_note_sync.py` — `calculate_candidate_labels()` | Cambiar criterio a `core_completeness() >= 6` (o delegar a `intent_orchestrator.core_completeness()`) |
| `app/app.py` — rutas que usan `current_stage == "PROFILE_READY"` | Eliminar stage literal como criterio; usar `core_completeness()` |
| `app/orchestrators/knowledge_orchestrator.py` — `_fallback_chatwoot_labels()` | Idem, centralizar criterio |

**Resultado esperado:** Una sola función `core_completeness(known_facts)` en `intent_orchestrator.py` es la autoridad para "perfil listo". Labels y stages se derivan de ella.

**Riesgo de regresión:** Medio — hay que verificar que `calculate_candidate_labels()` se usa para labels de Chatwoot y que el cambio no afecta el marcado visual.

---

### 1.3 🔴 Resolver contradicción "Capital Humano" en SYSTEM_PROMPT (Hallazgo #1)

**Problema:** El prompt prohíbe "Capital Humano" como tercero pero lo usa ~9 veces en ejemplos e instrucciones.

**Acciones:**

| Archivo | Cambio |
|---|---|
| `app/persona_config.py` | Reemplazar TODAS las ocurrencias de `"Capital Humano"` en instrucciones y ejemplos por frases de "voz de equipo": `"nuestro equipo"`, `"aquí lo revisamos"`, `"los compañeros en oficina"`, etc. |

**Casos concretos a cambiar:**

| Texto actual (en el prompt) | Texto propuesto |
|---|---|
| *"Capital Humano confirma el esquema final"* | *"nuestro equipo confirma el esquema final"* |
| *"Capital Humano lo valida"* | *"aquí lo validamos"* |
| *"Capital Humano confirma la condición final"* | *"nuestro equipo confirma la condición final"* |
| *"debe revisarla Capital Humano"* | *"lo revisamos aquí en el equipo"* |
| *"Capital Humano debe validar"* | *"nosotros validamos"* |
| *"Capital Humano valida si aplica"* | *"nuestro equipo valida si aplica"* |
| *"Capital Humano lo revisará"* | *"aquí lo revisamos"* |
| *"Capital Humano la revisará y corroborará"* | *"nuestro equipo la revisará y corroborará"* |
| *"seguimiento por Capital Humano"* | *"seguimiento de nuestro equipo"* |

Además: actualizar `context_builder.py:build_generation_prompt()` — ya dice "jamás 'Capital Humano'", solo asegurar que esté sincronizado con el cambio.

**Riesgo de regresión:** Bajo — es solo texto de prompt. Verificar que los ejemplos de respuesta sigan sonando naturales.

---

### 1.4 🔴 Centralizar default de GROQ_MODEL (Hallazgo #5)

**Problema:** `settings.py` usa `"llama3-8b-8192"` como default. `indexer.py` y `intent_classifier.py` tienen sus propios defaults. No hay un único source of truth.

**Acción recomendada — Unificar todo hacia un modelo:**

| Archivo | Cambio |
|---|---|
| `app/settings.py` | Cambiar default a `"llama-3.3-70b-versatile"` (el modelo usado por el pipeline principal) |
| `app/indexer.py` | Eliminar default redundante en `call_llm()` y `call_groq_json()` — leer siempre de `settings.GROQ_MODEL` |
| `app/knowledge/intent_classifier.py` | Cambiar `CLASSIFIER_MODEL` default a `"llama-3.1-8b-instant"` si se desea mantener modelo chico para clasificación. Documentar explícitamente por qué es distinto. |

O alternativa más limpia:

| Archivo | Cambio |
|---|---|
| `app/settings.py` | `GROQ_MODEL` (para respuestas) y `CLASSIFIER_MODEL` (para clasificación) como dos variables separadas |
| `app/indexer.py` | Leer `settings.GROQ_MODEL` y `settings.CLASSIFIER_MODEL` respectivamente |
| `app/*.py` | Eliminar todos los defaults inline; solo leer de `settings` |

**Riesgo de regresión:** Bajo si se verifica que las variables de entorno `.env` sigan funcionando.

---

## FASE 2 — Contradicciones semánticas

### 2.1 🟡 Alinear ejemplos de cifras con "no inventes" (Hallazgo #6)

**Problema:** Los ejemplos del SYSTEM_PROMPT enseñan al LLM a dar cifras específicas, contradiciendo la instrucción de no inventar.

**Acción:** En la sección de ejemplos, modificar los que contienen cifras para usar referencias al contexto en lugar de números fijos, o añadir una nota explícita: *"Estos ejemplos muestran el tono correcto. Las cifras son ilustrativas; en producción, responde solo con cifras del contexto RAG."*

Alternativamente: eliminar las cifras de los ejemplos y reemplazarlas con marcadores como `[contexto: rango salarial según ruta]`.

**Riesgo de regresión:** Bajo — solo texto de prompt.

---

### 2.2 🟡 Desbloqueo de HUMAN_REVIEW_REQUIRED (Hallazgo #8)

**Problema:** `update_stage()` nunca permite salir de `HUMAN_REVIEW_REQUIRED`.

**Acción recomendada en `app/db.py`:**

```sql
-- Actual: el WHEN del CASE nunca permite cambiar
WHEN current_stage = 'HUMAN_REVIEW_REQUIRED' THEN 'HUMAN_REVIEW_REQUIRED'

-- Propuesto: añadir excepción para desbloqueo explícito
WHEN current_stage = 'HUMAN_REVIEW_REQUIRED' 
     AND stage_to = 'HUMAN_REVIEW_UNLOCKED' THEN 'ACTIVE'
WHEN current_stage = 'HUMAN_REVIEW_REQUIRED' THEN 'HUMAN_REVIEW_REQUIRED'
```

O crear un endpoint separado `POST /admin/unlock/{conversation_id}` que ejecute un UPDATE directo con autorización.

**Riesgo de regresión:** Bajo si se añade un stage transicional y se verifica que solo admins puedan usarlo.

---

### 2.3 🟡 Hacer merge de guards en vez de replace (Hallazgo #7)

**Problema:** `_apply_deterministic_overrides` → `_apply_profile_guards` → `_apply_business_rule_overrides` se sobrescriben completamente el contrato cada vez.

**Acción recomendada:** Convertir cada guard para que haga merge inteligente:

```python
# En lugar de:
updated = dict(contract)
updated.update({"route": "human_handoff", "intent": "business_route_us", ...})

# Hacer:
if contract.get("route") != "rag":
    # Si ya hay una ruta determinada, añadir como sub_intent en lugar de sobrescribir
    sub_intents = contract.get("sub_intents", [])
    if "business_route_us" not in sub_intents:
        sub_intents.append("business_route_us")
    contract["sub_intents"] = sub_intents
else:
    contract["route"] = "human_handoff"
```

**Caso concreto:** "gracias, ya trabajé aquí antes, cuánto pagan" debería producir:
- `route: "human_handoff"` (por reingreso)
- `questions: ["pay_question"]` (no perder la pregunta)
- `response_text: "Los reingresos..." + "Para el dato de pago..."`

**Riesgo de regresión:** Medio — cambios en lógica central del orquestador. Probar con mensajes compuestos.

---

## FASE 3 — Inconsistencias arquitectónicas

### 3.1 🟡 Estandarizar pipeline: deprecar un endpoint o unificar (Hallazgo #9)

**Problema:** `/orchestrate/message` vs `/classify` — dos pipelines incompatibles.

**Opción A — Migración completa al nuevo pipeline (recomendada si multi-intent está maduro):**
1. Mover la lógica de persistencia del pipeline legacy al nuevo
2. Redirigir `/orchestrate/message` a `intent_orchestrator.plan_and_respond()`
3. Mantener `/classify` como endpoint de testing/debug
4. Deprecar `/orchestrate/message` con warning header

**Opción B — Mantener ambos pero con tabla unificada de intents:**
1. Crear un mapping en `app/knowledge/intent_catalog.py` que traduzca intents legacy ↔ nuevos
2. Usar el mapping en `_stage_for_contract()` y `_apply_business_rule_overrides()`

**Riesgo de regresión:** Alto — cambios en el flujo principal del chatbot. Requiere pruebas integrales.

---

### 3.2 🟡 Cablear `is_correction` y `certainty` en el clasificador (Hallazgo #17)

**Problema:** `fact_corrections.py` espera `is_correction` y `certainty` en los answers. El clasificador no produce esos campos.

**Acción en `app/knowledge/intent_classifier.py`:**

1. Añadir al JSON de salida del clasificador:
```json
{
  "field": "...",
  "value": "...",
  "evidence": "...",
  "confidence": 0.0-1.0,
  "is_correction": true|false,
  "certainty": "high"|"medium"|"low"
}
```

2. Actualizar `ANSWER_FIELDS` schema validation para incluir estos campos

3. Añadir ejemplos few-shot de correcciones al CLASSIFIER_SYSTEM:
```
Mensaje: "me equivoqué, son 10 años no 5"
{"message_type":"compound","primary_intent":"candidate_answer",
 "answers":[{"field":"experience.years","value":"10","evidence":"10 años",
   "confidence":0.9,"is_correction":true,"certainty":"high"}],
 "questions":[]}
```

4. En `app/knowledge/fact_corrections.py`: validar que `is_correction` y `certainty` tengan valores antes de usarlos

**Riesgo de regresión:** Medio — cambiar el schema de salida del clasificador puede afectar el enricher y el memory guard.

---

### 3.3 🟡 Centralizar defaults de RAG (Hallazgo #14)

**Problema:** `indexer.py` lee `TOP_K` de `settings.py`. `context_builder.py` lee `RAG_TOP_K` de env var con default 3. No están sincronizados.

**Acción:**

| Archivo | Cambio |
|---|---|
| `app/settings.py` | Añadir `RAG_TOP_K`, `RAG_MIN_SCORE`, `RAG_MAX_CONTEXT_CHARS`, `RAG_MAX_CHARS_PER_DOC` |
| `app/knowledge/context_builder.py` | Leer todos los defaults de `settings.py` en lugar de env vars directas |
| `app/*` que usen RAG | Asegurar que todos lean del mismo source de verdad |

**Riesgo de regresión:** Bajo.

---

### 3.4 🟡 Unificar `_clean_reply()` en un solo lugar (Hallazgo #13)

**Problema:** `app.py` y `knowledge_orchestrator.py` tienen su propia versión de `_clean_reply()` con ligeras diferencias.

**Acción:** Mover la función a un módulo compartido (ej. `app/text_utils.py` o `app/llm_utils.py`) y que ambos archivos la importen. Incluir la funcionalidad de ambas versiones (bucle `while changed` + `_strip_wrapping_quotes`).

**Riesgo de regresión:** Bajo — cambios localizados en funciones de limpieza de texto.

---

### 3.5 🟡 Añadir timezone fallback explícito (Hallazgo #15)

**Problema:** `_TZ_CENTRO = None` si `zoneinfo` falla → hora incorrecta.

**Acción en `app/knowledge/current_turn.py`:**

```python
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _TZ_CENTRO = _ZoneInfo("America/Mexico_City")
except Exception:
    import warnings
    warnings.warn("zoneinfo no disponible — usando UTC como fallback para hora CDMX")
    _TZ_CENTRO = datetime.timezone(datetime.timedelta(hours=-6))  # UTC-6 fijo
```

**Riesgo de regresión:** Muy bajo.

---

### 3.6 🟡 Alinear 17 datos del prompt con 6 del funnel (Hallazgo #20)

**Problema:** SYSTEM_PROMPT lista 17 datos recolectables; el funnel real solo tiene 6.

**Acción en `app/persona_config.py`:** Separar la lista en:
- "Datos principales que iremos registrando" (6 del funnel)
- "Datos adicionales que se pueden solicitar más adelante" (los otros 11)

O eliminar la lista numérica y reemplazarla con: *"El sistema guía la recolección de datos paso a paso según el perfil del candidato."*

**Riesgo de regresión:** Muy bajo.

---

## FASE 4 — Refinamientos

### 4.1 🟢 Quitar condición redundante en memory_guard (Hallazgo #11)

**Archivo:** `app/knowledge/memory_guard.py`

```python
# Línea ~78: quitar el `or` redundante
if field in FUNNEL_FIELD_FACT_KEYS:  # sin el `or field == "experience.vehicle_type"`
```

`experience.vehicle_type` ya está en `FUNNEL_FIELD_FACT_KEYS`. La condición `or` es código muerto.

---

### 4.2 🟢 Ajustar INTENT_CONFIDENCE_THRESHOLD (Hallazgo #16)

**Archivo:** `app/knowledge/intent_enricher.py`

Cambiar default de `0.85` a `0.75` o `0.70` para no perder datos moderadamente seguros. O usar un threshold relativo: mantener el top-2 answers por campo en lugar de un umbral fijo.

---

### 4.3 🟢 Reemplazar carácter corrupto en `_JOKE_BRIDGE` (Hallazgo #19)

**Archivo:** `app/orchestrators/knowledge_orchestrator.py`

```python
# Actual: "Ys> Ahora s, seguimos con su registro."
# Propuesto: "✅ Ahora sí, seguimos con su registro."
# O eliminar el emoji: "Ahora sí, seguimos con su registro."
```

---

### 4.4 🟢 Añadir variantes de pregunta de hora (Hallazgo #22)

**Archivo:** `app/orchestrators/knowledge_orchestrator.py`

Añadir a `_is_time_question()`:
```python
"me puede decir la hora", "qué horas son", "qué hora es en México", 
"a qué hora", "dime la hora", "tienes la hora"
```

---

## Resumen por archivo

| Archivo | Cambios propuestos | Fase |
|---|---|---|
| `app/persona_config.py` | Reemplazar 9+ ocurrencias de "Capital Humano" por voz de equipo; alinear lista de 17 datos | F1, F3 |
| `app/lead_memory/profile_extractor.py` | Cambiar `license.category` → `license.type` (O usar el nombre inverso) | F1 |
| `app/knowledge/memory_guard.py` | Alinear `FUNNEL_FIELD_FACT_KEYS["license"]`; quitar redundancia | F1, F4 |
| `app/knowledge/intent_orchestrator.py` | Alinear `FUNNEL_STEPS["license"].complete` con el nombre real del campo | F1 |
| `app/knowledge/intent_classifier.py` | Añadir `is_correction`/`certainty` al schema; añadir ejemplos few-shot | F3 |
| `app/knowledge/intent_enricher.py` | Ajustar `INTENT_CONFIDENCE_THRESHOLD` de 0.85 a 0.70-0.75 | F4 |
| `app/chatwoot_note_sync.py` | Unificar criterio `perfil_listo` con `core_completeness()` | F1 |
| `app/db.py` | Añadir desbloqueo de `HUMAN_REVIEW_REQUIRED` | F2 |
| `app/indexer.py` | Centralizar default de GROQ_MODEL; eliminar defaults inline | F1 |
| `app/settings.py` | Añadir `RAG_TOP_K`, `RAG_MIN_SCORE`, `RAG_MAX_CONTEXT_CHARS` | F3 |
| `app/knowledge/context_builder.py` | Leer defaults de `settings.py`; actualizar build_generation_prompt() | F1, F3 |
| `app/orchestrators/knowledge_orchestrator.py` | Merge inteligente de guards; reemplazar carácter corrupto; unificar `_clean_reply()`; añadir variantes de hora | F2, F3, F4 |
| `app/knowledge/current_turn.py` | Añadir timezone fallback explícito | F3 |
| `app/app.py` | Deprecar un endpoint o unificar pipelines; quitar `_clean_reply()` duplicada | F3 |
| `app/knowledge/fact_corrections.py` | Validar existencia de campos `is_correction`/`certainty` antes de usar | F3 |

---

## Orden de ejecución sugerido

```
F1.3 → F1.1 → F1.2 → F1.4 → F2.1 → F2.2 → F2.3 → F3.1 → F3.2 → F3.3 → F3.4 → F3.5 → F3.6 → F4.1 → F4.2 → F4.3 → F4.4
```

Donde:
- **F1.3** (Capital Humano) y **F1.4** (modelo) son cambios rápidos y aislados — se pueden hacer en paralelo
- **F1.1** (license.type/category) requiere alinear todos los módulos que usan el campo — hacer con cuidado
- **F3.1** (unificar endpoints) es el cambio más riesgoso — dejarlo para cuando el pipeline multi-intent esté estable
- Las fases 4 se pueden hacer en cualquier momento

---

*Documento generado el 2026-06-17. READ ONLY — no se modificó ningún archivo del proyecto.*
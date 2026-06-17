# Auditoría de Incongruencias y Fallas Semánticas

**Proyecto:** Agente AI Capital Humano Transmontes  
**Fecha:** 2026-06-17  
**Tipo:** READ-ONLY — sin modificación de archivos

---

## 🔴 CRÍTICO (Impacto funcional — produce errores en producción)

### #1 — CONTRADICCIÓN CENTRAL: "Voz de Equipo" vs "Capital Humano como tercero"

**Archivo:** `app/persona_config.py` (SYSTEM_PROMPT completo, 305 líneas)  
**Naturaleza:** Contradicción auto-referencial en el prompt

**El problema:** El SYSTEM_PROMPT establece una regla severa y explícita:

> *"VOZ DE EQUIPO – REGLA CRÍTICA: Hablas como parte del equipo de reclutamiento, no como un sistema externo. Nunca uses **'Capital Humano'** como si fuera un tercero separado de ti. En su lugar usa siempre: 'llámenos' / 'nuestro equipo' / 'aquí lo revisamos' / 'los compañeros en oficina'."*

Sin embargo, el MISMO prompt viola esta regla en **múltiples secciones** usando "Capital Humano" como entidad separada:

| Ubicación en SYSTEM_PROMPT | Texto exacto |
|---|---|
| Sección "CONTEXTO DE LA VACANTE" | *"aclarar que **Capital Humano** confirma el esquema final"* |
| Sección "CONTEXTO DE LA VACANTE" (2) | *"di que **Capital Humano** lo valida para no darle información incorrecta"* |
| Sección "USO DEL CONTEXTO RECUPERADO / RAG" | *"aclara que **Capital Humano** confirma la condición final"* |
| Sección "USO DEL CONTEXTO RECUPERADO / RAG" (2) | *"usa la más específica y aclara que **Capital Humano** confirma"* |
| Sección "SUSTANCIAS, ALCOHOL, FATIGA Y MEDICAMENTOS" | *"debe revisarla **Capital Humano**"* |
| Sección "SUSTANCIAS..." (respuesta segura) | *"**Capital Humano** debe validar cualquier situación antes de continuar"* |
| Sección "PERFILAMIENTO" | *"aclara que **Capital Humano** valida si aplica para su perfil"* |
| Sección "DOCUMENTOS" | *"di que **Capital Humano** lo revisará"* |
| Sección "CIERRE" | *"explica que **Capital Humano** la revisará y corroborará"* |

Además, `context_builder.py` genera prompts que **refuerzan la regla**:
```python
# context_builder.py build_generation_prompt():
"Habla como parte del equipo, nunca como un tercero. Usa 'nuestro equipo' o 
'llámenos de 8:00 a 17:30 hrs', jamás 'Capital Humano'."
```

**Impacto concreto:** El LLM recibe instrucciones contradictorias:
1. "NUNCA uses 'Capital Humano' como tercero" (varias secciones lo enfatizan)
2. "Ejemplos que usan 'Capital Humano' como tercero" (repetidamente)

El LLM (Groq, 70B parameters) está entrenado para seguir patrones establecidos. Los ejemplos con "Capital Humano" tienen más peso que la instrucción abstracta "no lo uses", porque los LLMs aprenden más efectivamente de ejemplos que de reglas. Resultado: respuestas inconsistentes donde a veces dice "nuestro equipo" y a veces "Capital Humano".

---

### #2 — DOS FUNNELS DE PERFILAMIENTO ACTIVOS SIMULTÁNEAMENTE

**Archivos:** `app/knowledge/current_turn.py` vs `app/knowledge/intent_orchestrator.py`  
**Naturaleza:** Arquitectura paralela con pipelines incompatibles

Existen **dos pipelines de preguntas** completamente distintos, cada uno con su propio orden, campos y criterios de completitud:

#### Funnel Legacy (en `current_turn.py`):
```python
def next_question_from_missing_facts(facts):
    # 1. candidate.city
    # 2. candidate.age           ← ¡Edad! (no existe en el nuevo)
    # 3. experience.vehicle_type
    # 4. license.category        ← ¡category! (no type)
    # 5. license.expiration_text ← ¡vencimiento específico!
    # 6. medical.apto_expiration_text ← ¡vencimiento específico!
    # 7. experience.years
    # 8. documents (cartas laborales)
    # → 8 preguntas + sub-chequeo de renewal
```

#### Funnel Multi-intent (en `intent_orchestrator.py`):
```python
FUNNEL_STEPS = [
    {"field": "candidate.city",          ...},  # 1. ciudad
    {"field": "experience.vehicle_type", ...},  # 2. tipo unidad
    {"field": "license",                 ...},  # 3. license.type + status
    {"field": "medical.apto_status",     ...},  # 4. apto_status (binario)
    {"field": "experience.years",        ...},  # 5. años exp
    {"field": "documents.proof",         ...},  # 6. cartas/semanas_imss
    # → 6 preguntas, SIN edad, SIN expiration_text
]
```

**Diferencias críticas:**

| Aspecto | Funnel Legacy (`current_turn.py`) | Funnel Multi-intent (`intent_orchestrator.py`) |
|---|---|---|
| Número de pasos | 8 | 6 |
| Pregunta edad | ✅ Sí (paso 2) | ❌ No |
| Vencimiento licencia | ✅ Sí (paso 5) | ❌ No (solo status binario) |
| Vencimiento apto | ✅ Sí (paso 6) | ❌ No (solo status binario) |
| Campo de licencia | `license.category` (B, E, etc.) | `license.type` + `license.status` |
| Criterio documentos | `labor_letters` o `proof` | `documents.proof` exacto |
| Sub-chequeo renewal | ✅ Sí (`_renewal_question_for_short_expiry`) | ❌ No |
| Gate de edad ≥50 | ✅ Sí | ❌ No |

**¿Cómo se activan?** 
- El funnel legacy corre desde `tasks_chatwoot.py` (tareas asíncronas de seguimiento) y desde el guard de `app.py`
- El funnel multi-intent corre en el pipeline nuevo (`intent_orchestrator.plan_and_respond`)
- Ambos pueden ejecutarse sobre el MISMO lead en distintos momentos

**Impacto:** Si ambos pipelines se activan para el mismo candidato, el bot puede:
1. Preguntar por edad en un turno
2. NO preguntar por edad en otro
3. Escribir `license.category` desde el extractor legacy
4. Chequear `license.type` desde el funnel nuevo → no lo encuentra → vuelve a preguntar

---

### #3 — TRES CRITERIOS DISTINTOS PARA "PERFIL LISTO"

**Archivos:** `app/chatwoot_note_sync.py`, `app/knowledge/intent_orchestrator.py`, `app/orchestrators/knowledge_orchestrator.py`  
**Naturaleza:** Definiciones inconsistentes del mismo concepto

Cada módulo decide si un perfil está "completo" usando criterios diferentes:

| Módulo | Función | Criterio | Etiqueta generada |
|---|---|---|---|
| `chatwoot_note_sync.py:calculate_candidate_labels()` | Label sync | `vehicle_confirmed AND has_license AND has_medical AND vacancy_accepted` (4 campos) | `perfil_listo` |
| `intent_orchestrator.py:core_completeness()` | Funnel nuevo | 6 campos: city + vehicle_type + license(type+status) + apto + years + documents.proof | N/A (solo conteo) |
| `knowledge_orchestrator.py:_fallback_chatwoot_labels()` | Legacy | `current_stage == "PROFILE_READY"` — stage literal de la BD | Labels varias |

Incluso `app.py` documenta esta deuda:
```python
# app.py (línea ~738)
# OJO — ruta DEGRADADA: el criterio de perfil_listo aquí es 
# current_stage == "PROFILE_READY", distinto del de la ruta principal...
# Ambas comparten OFFICIAL_LABELS/TERMINAL_LABELS pero pueden discrepar 
# en cuándo emiten una label terminal.
```

**Impacto:** Un lead puede:
- Aparecer como "perfil_listo" en Chatwoot (labels) pero el funnel tener 3 campos pendientes
- Tener el funnel completo pero no tener la label `perfil_listo` porque `vacancy_accepted` no está en "sí"
- Estar en stage `PROFILE_READY` en BD pero el funnel nuevo verlo incompleto

---

### #4 — `license.type` vs `license.category`: EL FUNNEL NUNCA ENCUENTRA LA LICENCIA

**Archivos:** `app/knowledge/memory_guard.py`, `app/knowledge/intent_orchestrator.py`, `app/lead_memory/profile_extractor.py`, `app/knowledge/intent_classifier.py`  
**Naturaleza:** Bug funcional — el funnel pregunta licencia infinitamente

**El problema exacto:**

1. `memory_guard.py:FUNNEL_FIELD_FACT_KEYS` define que el campo `license` chequea:
   ```python
   "license": ("license.type", "license.status"),
   ```

2. `intent_orchestrator.py:FUNNEL_STEPS` chequea:
   ```python
   "complete": lambda f: _has(f, "license.type") and f.get("license.status") == "vigente",
   ```

3. `profile_extractor.py` (el extractor de hechos por regex) **nunca escribe `license.type`**:
   - Escribe `license.category` = "B", "B,E", "E", etc.
   - Escribe `license.status` = "vigente", "vencida"
   - **NUNCA** escribe `"license.type"`

4. `intent_classifier.py` (clasificador LLM) SÍ usa `license.type` en su catálogo de campos:
   ```python
   ANSWER_FIELDS = {
       ...
       "license.type",    # B | E | A | C
       "license.status",  # vigente | vencida | tramite
       ...
   }
   ```
   Pero el clasificador solo **produce** answers en formato JSON. Si el clasificador dice `license.type: "E"`, el enricher lo deja pasar (está en ANSWER_FIELDS), pero ningún extractor regex lo escribe.

**¿Qué significa esto en runtime?**
- El funnel pregunta por licencia
- El candidato responde "tengo licencia tipo E vigente" 
- `profile_extractor.py` escribe: `license.category="E"`, `license.status="vigente"`
- `memory_guard.py` chequea: `known_facts.get("license.type")` → **Siempre None** (nunca se escribió)
- El funnel chequea: `_has(f, "license.type")` → **Siempre False**
- Por tanto: el funnel **nunca** considera la licencia como completa → pregunta por licencia eternamente

**Ramas de código afectadas:**
- Ruta multi-intent (vía `intent_orchestrator.plan_and_respond`) — bug activo
- Ruta legacy (vía `knowledge_orchestrator._is_strong_candidate`) — usa `license.category` y funciona bien

---

### #5 — DEFAULT DE MODELO LLM DISTINTO ENTRE MÓDULOS: 8B vs 70B

**Archivos:** `app/settings.py` vs `app/indexer.py`  
**Naturaleza:** Configuración silenciosamente inconsistente

| Archivo | Default de `GROQ_MODEL` | Parámetros |
|---|---|---|
| `settings.py` | `"llama3-8b-8192"` | 8B parámetros |
| `indexer.py` | `"llama-3.3-70b-versatile"` | 70B parámetros |

El orden de importación determina qué default "gana":
```python
# En knowledge_orchestrator.py:
from app.indexer import call_llm  # ← indexer.py tiene su PROPIO default = 70B
# call_llm() en indexer.py usa:
# LLM_PROVIDER = getattr(settings, "LLM_PROVIDER", os.getenv("LLM_PROVIDER", "groq"))
# GROQ_MODEL = getattr(settings, "GROQ_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
```

Si `GROQ_MODEL` no está en env vars:
- `settings.GROQ_MODEL` = `"llama3-8b-8192"` 
- `indexer.GROQ_MODEL` = `"llama-3.3-70b-versatile"` (porque `getattr(settings, "GROQ_MODEL")` cae al default de `os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")`)

**Esto es un BUG de lógica de getattr:** `getattr(settings, "GROQ_MODEL")` llama a `settings.GROQ_MODEL`, que SÍ existe (default = llama3-8b-8192). Pero la línea en `indexer.py` es:
```python
GROQ_MODEL = getattr(settings, "GROQ_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
```
Como `settings.GROQ_MODEL` existe (es `"llama3-8b-8192"`), `getattr` devuelve `"llama3-8b-8192"`. El `os.getenv` solo se usa si `settings.GROQ_MODEL` NO existe. PERO... en `settings.py`:
```python
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")
```
Cuando NO hay env var: `settings.GROQ_MODEL` = `"llama3-8b-8192"`. `getattr(settings, "GROQ_MODEL")` = `"llama3-8b-8192"`. Por tanto `indexer.GROQ_MODEL` = `"llama3-8b-8192"`. 

**Entonces, ¿dónde está el problema?**

En que `call_llm()` en `indexer.py` usa la variable LOCAL `GROQ_MODEL` (8B), pero `call_groq_json()` tiene su propio default:
```python
def call_groq_json(..., model: str | None = None):
    completion = client.chat.completions.create(
        model=model or GROQ_MODEL,  # ← 8B por defecto
        ...
    )
```

Y el clasificador (`intent_classifier.py`) explícitamente usa otro:
```python
CLASSIFIER_MODEL = os.getenv("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")
```

**El problema real:** No hay un solo lugar donde se defina "el modelo actual". Si alguien cambia `GROQ_MODEL` en `.env`, algunos módulos lo heredan y otros no, dependiendo de su implementación específica de getattr/os.getenv.

---

## 🟡 ALTO (Problemas de diseño que causan comportamiento errático)

### #6 — SYSTEM_PROMPT: Ejemplos con cifras exactas contradicen "no inventes cifras"

**Archivo:** `app/persona_config.py`  
**Naturaleza:** Ejemplos que enseñan al LLM a hacer lo que las reglas le prohíben

El prompt dice:
> *"No inventes cifras. Si el contexto trae montos, puedes mencionarlos... Si el contexto no trae el dato exacto, di que Capital Humano lo valida."*

Pero la sección de "EJEMPLOS DE RESPUESTAS CON EL TONO CORRECTO" incluye ejemplos con **cifras muy específicas**:

| Ejemplo | Cifras incluidas |
|---|---|
| `"cuánto pagan?"` — Mundo responde | *"el rango normal está entre **$5,000 y $10,000** semanales"* |
| `"pagan por km?"` — Mundo responde | *"en tramos como Monterrey-Nuevo Laredo se paga **$850 por ida y $850 por vuelta**"* |
| `"qué incluyen de prestaciones?"` — Mundo responde | *"bono de contratación y permanencia diferido — **$15,000 para sencillo y $17,000 para full**"* |
| `"dan viáticos?"` — Mundo responde | *"Se pagan **$900 semanales** de gastos muertos diferidos"* |

**Mecanismo del problema:** Los LLMs modernos (especialmente los fine-tuneados para instrucciones) son altamente sensibles a ejemplos en el prompt — es lo que se conoce como *few-shot priming*. Los ejemplos tienen más peso instructivo que las reglas abstractas. Si el prompt dice "no inventes cifras" pero luego muestra 4 ejemplos donde el bot da cifras, el LLM tenderá a seguir los ejemplos.

**En la práctica:** Cuando el RAG no trae contexto suficiente, el LLM puede "inventar" cifras similares a las de los ejemplos (ej. "$5,000 a $10,000" es un rango genérico que podría aparecer en cualquier respuesta sin contexto).

---

### #7 — GUARDS DETERMINISTAS SE SOBRESCRIBEN ENTRE SÍ (ORDEN FRÁGIL)

**Archivo:** `app/orchestrators/knowledge_orchestrator.py`  
**Naturaleza:** Pipeline de sobrescritura donde el último gana

Tres funciones secuenciales modifican el contrato:

```python
# En knowledge_orchestrator.handle_message() - orden de ejecución:

contract = resolve_message(message, conversation_state)  # 1. Neo4j
contract = _apply_deterministic_overrides(message, contract)  # 2. greeting/farewell/time
contract = _apply_profile_guards(message, contract)  # 3. document_ack
contract = _apply_business_rule_overrides(message, contract)  # 4. B1/reingreso/non-target
```

**Problema:** Cada función reemplaza completamente los campos del contrato sin merge inteligente:

```python
def _apply_business_rule_overrides(message, contract):
    if _B1_US_RE.search(text):
        updated = dict(contract)
        updated.update({
            "route": "human_handoff",
            "intent": "business_route_us",  # ← Sobrescribe intent original
            ...
        })
        return updated
```

Un mensaje como *"gracias, ya trabajé aquí antes y quiero reingresar, cuánto pagan"* tiene:
- Intención de pregunta (pay_question)
- Intención de reingreso

Pero `_apply_business_rule_overrides` (que chequea `_REINGRESO_RE`) pisará el intent quitando la pregunta de pago. **El último guard gana**, ignorando las demás señales.

**Asimetría en guards de saludo/despedida:**

```python
def _looks_like_greeting(message):
    text = normalize_text(message).strip()
    if not text or len(text.split()) > 5:  # ← límite de 5 palabras
        return False
    ...
    
def _looks_like_farewell(message):
    text = normalize_text(message)
    ...
    # NO tiene límite de palabras ← asimétrico
```

Un mensaje de 6+ palabras que contenga "hola" no se detecta como saludo, pero uno de 6+ palabras que contenga "gracias" SÍ se detecta como despedida.

---

### #8 — HUMAN_REVIEW_REQUIRED ES IRREVERSIBLE

**Archivo:** `app/db.py` — función `update_stage()`  
**Naturaleza:** State lock permanente

```python
UPDATE rh_conversations
SET current_stage = CASE
    WHEN current_stage = 'HUMAN_REVIEW_REQUIRED' 
    THEN 'HUMAN_REVIEW_REQUIRED'   # ← NUNCA cambia
    ELSE %(stage_to)s
END
```

**Comportamiento:** Una vez que `current_stage = 'HUMAN_REVIEW_REQUIRED'`, absolutamente nada puede cambiarlo. Ni siquiera si:
- El candidato aclara que no quiere reingresar
- Un agente humano resuelve el caso
- El candidato responde correctamente todas las preguntas
- Pasa el tiempo

**Impacto funcional:** Esto puede haber sido intencional como "bloqueo de seguridad" para garantizar revisión humana, pero sin un mecanismo de desbloqueo (ej. endpoint admin, o tiempo de expiración), leads válidos quedan atrapados permanentemente.

---

### #9 — DOS ENDPOINTS CON PIPELINES INCOMPATIBLES

**Archivo:** `app/app.py`  
**Naturaleza:** Dos rutas de procesamiento activas

| Endpoint | Pipeline | Dónde persiste | Funnel usado |
|---|---|---|---|
| `/orchestrate/message` | `run_hr_graph_message()` → `knowledge_orchestrator.handle_message()` | `rh_messages`, `rh_conversations` (tablas legacy) | Legacy (current_turn.py) |
| `/classify` | `intent_classifier.classify_message()` → `intent_enricher.enrich_classification()` | SÓLO clasifica, no persiste | Multi-intent (intent_orchestrator.py) |

**Problema:** Si un sistema externo (o un desarrollador) llama al endpoint equivocado:
1. `/orchestrate/message` escribe en tablas legacy
2. `/classify` solo clasifica (no persiste)
3. La tarea `tasks_chatwoot.py` usa el pipeline legacy para labels
4. El pipeline multi-intent escribe en `rh_lead_facts_v2` (tablas nuevas)

**Ambos pipelines modifican** `rh_leads_v2` y `rh_lead_messages_v2` pero con campos y lógica distintos.

---

### #10 — INTENTS DEL ORQUESTADOR LEGACY NO MAPEAN A INTENTS DEL CLASIFICADOR NUEVO

**Archivos:** `app/orchestrators/knowledge_orchestrator.py` vs `app/knowledge/intent_classifier.py`  
**Naturaleza:** Vocabularios de intents completamente disjuntos

El orquestador legacy usa estos intents para determinar stage:
```python
# knowledge_orchestrator.py:_stage_for_contract()
"payment_compensation", "bases_routes_rest", "driving_school", 
"callback_request", "on_route_safety", "drug_testing_urine",
"requirements_documents"
```

El clasificador nuevo usa estos intents:
```python
# intent_classifier.py
QUESTION_INTENTS = {
    "pay_question",
    "logistics_question",
    "documents_question",
    "vacancy_question",
    "safety_intent",
}
```

**No hay una sola intención que coincida entre ambos.** Si el nuevo pipeline produce `"pay_question"`, `_stage_for_contract()` cae en `else: return "new"` en lugar de identificar que es una consulta de pago.

---

## 🟡 MEDIO (Problemas de consistencia, naming y defaults divergentes)

### #11 — `memory_guard.py`: condición redundante evidencia código desactualizado

```python
# memory_guard.py _claimed_answer()
if field in FUNNEL_FIELD_FACT_KEYS or field == "experience.vehicle_type":
```

`"experience.vehicle_type"` **YA está** en `FUNNEL_FIELD_FACT_KEYS`:
```python
FUNNEL_FIELD_FACT_KEYS = {
    "candidate.city": ("candidate.city",),
    "experience.vehicle_type": ("experience.vehicle_type",),  # ← aquí está
    "license": ("license.type", "license.status"),
    ...
}
```

La condición `or field == "experience.vehicle_type"` es matemáticamente redundante. Esto sugiere que originalmente no estaba en el mapa, alguien lo añadió al mapa pero olvidó quitar la condición extra.

---

### #12 — `intent_classifier.py`: Campo `license.type` según el clasificador, pero...

El clasificador usa en su catálogo:
```python
ANSWER_FIELDS = {
    "license.type",   # B | E | A | C
    ...
}
```

Pero `profile_extractor.py` (el extractor regex que corre en la ruta legacy) escribe `license.category`.  
El nuevo pipeline (clasificador → enricher) sí usa `license.type`, pero solo cuando el clasificador LLM lo extrae — y el clasificador es un modelo 8B que puede o no extraer el campo correctamente.

**Hay tres formas distintas de referirse al tipo de licencia en el proyecto:**
1. `license.category` — usado por `profile_extractor.py` y `chatwoot_note_sync.py`
2. `license.type` — usado por `intent_classifier.py` (ANSWER_FIELDS) y `memory_guard.py` (FUNNEL_FIELD_FACT_KEYS)
3. `license.type` (nuevamente) pero escrito por el LLM clasificador, no por regex

---

### #13 — `_clean_reply()` duplicada con implementaciones NO idénticas

**Archivos:** `app/app.py` y `app/orchestrators/knowledge_orchestrator.py`

| Aspecto | `app.py: _clean_reply()` | `knowledge_orchestrator.py: _clean_reply()` |
|---|---|---|
| Thinking tags | ✅ Sí | ✅ Sí |
| Generic closing patterns | ✅ Sí (bucle `while changed`) | ✅ Sí (sin bucle) |
| Wrapping quotes | ❌ No | ✅ Sí (`_strip_wrapping_quotes`) |
| Bucle iterativo | ✅ Sí (`while changed`) | ❌ No |

Ambas se llaman `_clean_reply`, ambas reciben texto LLM, pero producen resultados ligeramente distintos.

---

### #14 — `context_builder.py`: defaults de RAG independientes de `settings.py`

**Archivos:** `app/settings.py` vs `app/knowledge/context_builder.py`

| Parámetro | Default en `settings.py` (vía `indexer.py`) | Default en `context_builder.py` |
|---|---|---|
| `TOP_K` / `RAG_TOP_K` | `5` | `3` |
| `RAG_MIN_SCORE` | No existe | `0.25` |
| `RAG_MAX_CONTEXT_CHARS` | No existe | `2200` |
| `RAG_MAX_CHARS_PER_DOC` | No existe | `850` |

`context_builder.py` usa sus propios defaults:
```python
requested_k = _to_int(top_k, _to_int(os.getenv("RAG_TOP_K"), 3))
min_score = _env_float("RAG_MIN_SCORE", 0.25)
max_context_chars = _to_int(os.getenv("RAG_MAX_CONTEXT_CHARS"), 2200)
```

Mientras que `indexer.py` (usado por la ruta legacy) usa:
```python
TOP_K = int(getattr(settings, "TOP_K", os.getenv("TOP_K", "5")))
```

Si alguien configura `TOP_K=10` esperando más contexto, el pipeline nuevo (multi-intent) seguirá trayendo solo 3 chunks.

---

### #15 — `_TZ_CENTRO` falla silenciosamente → hora incorrecta para CDMX

**Archivo:** `app/knowledge/current_turn.py`

```python
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _TZ_CENTRO = _ZoneInfo("America/Mexico_City")
except Exception:
    _TZ_CENTRO = None  # ← falla silenciosa
```

Si `zoneinfo` no está disponible (Python <3.9 en Windows, o base de datos de timezone no instalada), `_profile_complete_closing()` usa `datetime.datetime.now()` que devuelve la hora local del servidor (podría ser UTC, PST, etc.), NO la hora CDMX.

```python
en_horario = (
    now.weekday() < 5 
    and datetime.time(8, 0) <= now.time() <= datetime.time(17, 30)
)
```

Si el servidor está en UTC, a las 14:00 UTC (08:00 CDMX) el check funciona, pero a las 23:00 UTC (17:00 CDMX) ya falla — diría "fuera de horario" cuando en CDMX aún son horas laborales.

---

### #16 — `INTENT_CONFIDENCE_THRESHOLD = 0.85` excluye answers válidos

**Archivo:** `app/knowledge/intent_enricher.py`

```python
CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.85"))
```

El clasificador asigna confianzas como 0.95, 0.92, 0.90, 0.85, 0.80, 0.75.  
Los valores de 0.85 **apenas pasan**.  
Un valor de 0.84 (que sigue siendo bastante seguro) pierde el dato.  
Los valores de 0.80 (inferencias moderadas) y 0.75 (débiles) nunca persisten.

- `"tengo 10 años de experiencia"` → confidence 0.85 → PASA
- `"pues unos 10 años mas o menos"` → confidence 0.80 → RECHAZADO (el dato no se guarda)

---

### #17 — `fact_corrections.py`: depende de campos que el clasificador NO produce

**Archivos:** `app/knowledge/fact_corrections.py`, `app/knowledge/intent_classifier.py`

`fact_corrections.py` espera que los answers tengan:
```python
is_correction = bool(answer.get("is_correction"))       # ← NO existe en el clasificador
certainty = (answer.get("certainty") or "high").lower() # ← NO existe en el clasificador
```

El schema JSON del clasificador (`intent_classifier.py`) produce:
```json
{
  "field": "...",
  "value": "...",
  "evidence": "...",
  "confidence": 0.0-1.0
}
```

No incluye `is_correction` ni `certainty`. Por tanto:
- `is_correction` siempre = `False`
- `certainty` siempre = `"high"`
- `_resolve_one()` NUNCA produce estado `"corrected"` — las correcciones del candidato siempre se tratan como `"conflict"`

La corrección explícita ("me equivoqué, son 10 años no 5") nunca se reconoce como tal.

---

### #18 — `app.py` llama `reindex` con lógica de reintento que puede bloquear

**Archivo:** `app/app.py` (endpoint /reindex y startup)

```python
@app.on_event("startup")
async def startup_event():
    # ... intents de reindex en startup con retry
```

El código de startup puede intentar reindexar la base de datos Chroma al arrancar. Si el reindex falla, hay reintentos. Si el warmup de Chroma/embeddings bloquea el startup, la app no arranca hasta completar la indexación (~2.4 GB de modelo de embeddings).

---

### #19 — El "joke bridge" contiene un carácter Unicode visiblemente corrupto

**Archivo:** `app/orchestrators/knowledge_orchestrator.py`

```python
_JOKE_BRIDGE = "Ys> Ahora s, seguimos con su registro."
```

El carácter `Y` (U+FFFD, REPLACEMENT CHARACTER) es un símbolo de error de codificación. Aparece donde debería haber un emoji o carácter Unicode válido. Se muestra literalmente al candidato.

---

### #20 — `persona_config.py`: Lista de 17 datos a recolectar vs funnel de 6

**Archivos:** `app/persona_config.py`, `app/knowledge/intent_orchestrator.py`

El SYSTEM_PROMPT instruye al LLM que el sistema puede recolectar **17 datos**:
> *"Datos que el sistema puede recolectar poco a poco: 1. Ciudad, 2. Edad, 3. Tipo de licencia, 4. Experiencia..., 17. Expectativa económica"*

Pero el funnel real solo contempla **6 campos** (núcleo). Hay **11 datos** que el SYSTEM_PROMPT menciona como recolectables que el funnel nunca pide:
- Edad
- Disponibilidad para rutas foráneas
- Disponibilidad para iniciar
- Última empresa
- Motivo de salida
- Teléfono de contacto
- Referencias laborales
- Retenciones Infonavit/Fonacot
- Estado civil
- Pensión alimenticia
- Expectativa económica

**Impacto:** El LLM, al leer que hay 17 datos que "el sistema puede recolectar", puede intentar preguntar por datos que el funnel no contempla, o el candidato puede esperar que le pregunten por esos datos y nunca ocurra.

---

## 🟢 BAJO (Observaciones, documentación, deuda técnica)

### #21 — La normalización de entrada usa `_WORD_RE` que elimina caracteres UTF-8 válidos

**Archivo:** `app/knowledge/text_normalizer.py`

```python
_WORD_RE = re.compile(r"[^a-z0-9ñáéíóúüÑ\s\-\.]", re.IGNORECASE)
```

Elimina cualquier carácter que no sea alfanumérico español + espacios/guiones/puntos. Esto **descarta**:
- Caracteres acentuados mayúsculos como `Á`, `É`, `Í`, `Ó`, `Ú` (el regex los deja pasar por IGNORECASE, pero revisando: `[a-z]` con IGNORECASE cubre A-Z, y los acentos están listados explícitamente)
- Emojis (pueden ser intencionales del candidato)
- Signos de puntuación como `¡`, `¿`, `á` etc. — están cubiertos explícitamente

En realidad no es un bug, pero es una observación: la normalización es muy agresiva. Elimina cualquier cosa que no sea estrictamente texto español.

### #22 — `_looks_like_farewell()` chequea `"?" in message` en raw pero `"¿"` también

```python
if "?" in message or "¿" in message:
    return False
```

El chéqueo de `"¿"` (inverted question mark) está, pero solo en ASCII `\xbf`. Si el candidato usa exclusivamente `"¿"` sin `"?"`, el chequeo funciona. Si usa solo `"?"` al final, también. Es correcto, pero vale la pena notar que este chequeo existe y es doble.

### #23 — `_is_time_question()` solo reconoce frases exactas, no variantes

```python
_phrase in text for phrase in (
    "que hora es", "qué hora es", "hora es", "me dices la hora",
    "tiene la hora", "sabes la hora",
)
```

Faltan variantes comunes: "me puede decir la hora", "qué horas son", "qué hora es en México", "a qué hora", etc.

---

## Resumen de Severidad

| # | Severidad | Hallazgo | Esfuerzo estimado de corrección |
|---|---|---|---|
| 1 | 🔴 Crítico | SYSTEM_PROMPT se contradice sobre "Capital Humano" | Bajo — editar el prompt |
| 2 | 🔴 Crítico | Dos funnels activos con campos distintos | Alto — unificar funnels |
| 3 | 🔴 Crítico | Tres criterios de "perfil_listo" diferentes | Medio — unificar criterio |
| 4 | 🔴 Crítico | `license.type` vs `license.category` — bug de campo | Bajo — alinear nombres |
| 5 | 🔴 Crítico | Default de modelo LLM inconsistente entre módulos | Bajo — unificar defaults |
| 6 | 🟡 Alto | Ejemplos con cifras contradicen "no inventes" | Bajo — editar prompt |
| 7 | 🟡 Alto | Guards se sobrescriben en orden frágil | Medio — merge en vez de replace |
| 8 | 🟡 Alto | HUMAN_REVIEW_REQUIRED es irreversible | Bajo — añadir desbloqueo |
| 9 | 🟡 Alto | Dos endpoints con pipelines incompatibles | Alto — unificar/deprecar |
| 10 | 🟡 Alto | Intents legacy no mapean a nuevos | Medio — crear mapping |
| 11 | 🟡 Medio | Condición redundante en memory_guard | Muy bajo — quitar `or` |
| 12 | 🟡 Medio | Tres formas de nombrar tipo de licencia | Medio — estandarizar |
| 13 | 🟡 Medio | `_clean_reply()` duplicada y divergente | Bajo — unificar función |
| 14 | 🟡 Medio | Defaults de RAG independientes por módulo | Bajo — centralizar defaults |
| 15 | 🟡 Medio | Timezone falla silenciosamente | Bajo — añadir fallback explícito |
| 16 | 🟡 Medio | Threshold 0.85 excluye datos válidos | Bajo — bajar threshold |
| 17 | 🟡 Medio | `fact_corrections` recibe campos que no existen | Medio — cablear is_correction |
| 18 | 🟡 Medio | Error de codificación en joke bridge | Muy bajo — reemplazar carácter |
| 19 | 🟡 Medio | 17 datos en prompt vs 6 en funnel real | Bajo — alinear prompt |
| 20 | 🟢 Bajo | Normalización muy agresiva | Observación |
| 21 | 🟢 Bajo | Variantes de pregunta de hora no cubiertas | Muy bajo — añadir variantes |

**Total:** 21 hallazgos (4 críticos, 6 altos, 8 medios, 2 bajos, 1 observación)
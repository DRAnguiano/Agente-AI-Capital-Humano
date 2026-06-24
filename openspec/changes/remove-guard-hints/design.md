## Approach

Introducir un **Turn Intent Pre-Classifier** (TIPC): una sola llamada LLM T=0 al inicio del pipeline de cada turno que devuelve un `TurnIntentSignals` dict con todas las señales semánticas. Los extractores y guards posteriores consumen este dict en lugar de invocar su propio LLM con su propio guard.

```
Mensaje entrante
      │
      ▼
┌─────────────────────────────┐
│  turn_intent_classifier.py  │  ← 1 LLM call (llama-3.1-8b-instant, T=0)
│  TurnIntentSignals (JSON)   │
└──────────┬──────────────────┘
           │
    ┌──────┴───────────────────────────────────┐
    │              Pipeline actual              │
    ▼              ▼              ▼             ▼
extract_      has_embedded_  _is_memory_  _CALL_INTENT
current_turn  business_q     claim        / RENEWAL
(ya_reclamo,  (has_embedded  (is_memory   / NO_ROAD
 exp years,    _question)     _claim)      / EXPIRY
 etc.)
```

## Key Decisions

### D1 — Un JSON unificado por turno, no N calls separadas

El TIPC devuelve todas las señales en una llamada. Los módulos individuales ya NO llaman al LLM; solo leen el dict.

```python
@dataclass
class TurnIntentSignals:
    is_ya_reclamo: bool           # "ya le habia dicho" vs "ya tengo"
    is_memory_claim: bool         # afirma haber dado el dato antes
    has_embedded_question: bool   # pregunta de negocio sin "?"
    call_requested: bool          # pide que le llamen
    renewal_proof: str | None     # "si" | "no" | null
    no_road_experience: bool      # declara no tener experiencia en carretera
    has_expiry_context: bool      # menciona fecha/plazo de vencimiento (trigger para extractor)
    experience_context: bool      # habla de SU experiencia conduciendo
```

### D2 — Fail-safe completo: si LLM falla, todos los signals = False/None

El TIPC tiene un único punto de falla. Si Groq falla (timeout, rate limit), retorna `TurnIntentSignals()` con todos los campos en su valor "neutro" (False/None). El pipeline continúa sin clasificación semántica — comportamiento degradado, no crash.

### D3 — El TIPC se llama ANTES del pipeline de extracción, se pasa como parámetro

`extract_profile_facts(message, intent, turn_signals=None)` y `extract_current_turn_facts(message, prev_q, turn_signals=None)` aceptan el dict precomputado. Si no se pasa (tests unitarios), el clasificador se llama internamente.

El orquestador lo llama una vez y lo distribuye:

```python
turn_signals = classify_turn_intent(message)
facts = extract_profile_facts(message, intent, turn_signals=turn_signals)
current = extract_current_turn_facts(message, prev_q, turn_signals=turn_signals)
is_claim = _is_memory_claim(message, turn_signals=turn_signals)
```

### D4 — Guards estructurales y de seguridad NO cambian

Los guards listados en la sección "CONSERVAR" de la proposal permanecen exactamente igual. No son semánticos y el LLM no puede reemplazarlos:
- `_PAID_SENSITIVE_RE` → seguridad
- `_B1_US_RE` etc. → política determinista
- `_residence_markers` → ancla estructural de zona
- `normalize_vehicle()` → catálogo de dominio
- Checks de unidad temporal → parsing estructural

### D5 — Prompt del TIPC: ejemplos exhaustivos del gremio

El prompt incluye ejemplos de jerga real documentada para todos los signals:

```
is_ya_reclamo:
  true: "ya le había dicho", "eso ya se lo mencioné antes", "ya les mandé eso"
  false: "ya tengo la licencia", "ya conseguí el apto", "ya está vigente"

is_memory_claim:
  true: "como le dije antes", "eso ya lo había comentado", "ya se los mandé"
  false: "tengo 10 años", "soy de Torreón", "si tengo cartas"

has_embedded_question:
  true: "soy de Gómez que rutas hay", "tengo licencia E cuánto pagan", "dan boleto"
  false: "soy de Torreón", "tengo 10 años manejando full"

call_requested:
  true: "me pueden llamar", "ponerse en contacto", "prefiero que me hablen"
  false: "no me llamen", "soy de Torreón"

renewal_proof:
  "si": "ya pagué la cita", "tengo el comprobante", "tengo el recibo del trámite"
  "no": "no tengo comprobante", "todavía no tramito", "sin papel todavía"
  null: "tengo licencia E vigente"

no_road_experience:
  true: "nunca he manejado tracto", "soy principiante", "quiero aprender a manejar"
  false: "tengo 10 años en full", "manejo sencillo"

has_expiry_context:
  true: "se me acaba en 3 meses", "vence en julio", "caduca este año"
  false: "licencia vigente", "apto al corriente"

experience_context:
  true: "manejo tracto desde hace 5 años", "soy operador de full"
  false: "me interesa ser operador", "busco trabajo de tracto"
```

### D6 — Archivo nuevo: `app/knowledge/turn_intent_classifier.py`

Módulo independiente, sin dependencias circulares. Expone:
- `classify_turn_intent(message: str) -> TurnIntentSignals`
- `TurnIntentSignals` dataclass

## Out of Scope

- Cambiar el comportamiento de `_PAID_SENSITIVE_RE`, `_B1_US_RE`, `_REINGRESO_RE`, `_NON_TARGET_RE`
- Migrar `normalize_vehicle()` o el catálogo de dominio
- Cambiar el prompt del friendly LLM (generación, no clasificación)
- Modificar `_conditional_si` (parsing sintáctico del "sí" afirmativo)

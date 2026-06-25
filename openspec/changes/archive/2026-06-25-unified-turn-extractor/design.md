## Context

El path de un turno hoy (medido en código, 2026-06-25):

```
WORKER (tasks_chatwoot.process_debounced_message)
├─1─ run_hr_graph_message → handle_message()              [PATH A: orquestador]
│      ├─ extract_profile_facts_as_dict (age guard)        ~1 LLM
│      ├─ extract_profile_facts (_store_lead_memory)       ~4 LLM
│      ├─ _build_funnel_nudge → extract_profile_facts      ~4 LLM
│      ├─ persiste facts en rh_lead_facts_v2  ◄── escritor 1
│      └─ devuelve result.reply
├─2─ extract_current_turn_facts(msg, last_bot)            [PATH B: guard]  ~5 LLM
└─3─ si should_prioritize → build_current_turn_ack()      re-extrae        ~5 LLM
        ├─ persiste context_new en rh_lead_facts_v2  ◄── escritor 2
        └─ PISA result.reply del PATH A
```

El mismo texto se extrae ~5 veces, en dos módulos, con dos escritores. `upsert_lead_fact` pisa el valor incondicionalmente (`fact_value = EXCLUDED.fact_value`) y solo sube la confianza (`GREATEST`), por lo que la confianza es decorativa: un dato débil pisa a uno fuerte y hereda confianza alta.

Constraints del proyecto que este diseño respeta:
- **Las preguntas del funnel las emite el sistema, nunca el LLM** (el extractor solo extrae, no decide qué preguntar).
- **Prioridad de fuentes de verdad:** turno actual > lead_memory > Neo4j > RAG > LLM.
- **La política de negocio va en código, nunca en un prompt/seed** (regla ya establecida para el seed Neo4j; este diseño la extiende a la extracción).

## Goals / Non-Goals

**Goals**
- Un único punto de extracción por turno; el mismo texto se procesa con LLM una sola vez.
- Eliminar el regex como *extractor* de texto natural; conservarlo como *validador* determinista.
- Confianza derivada de evidencia observable y que **gobierne** la escritura.
- Reconciliar el doble path (guard/orquestador) sobre un solo `TurnExtraction`.
- Migración sin riesgo: shadow log-only antes de cortar.

**Non-Goals**
- No cambiar qué preguntas hace el funnel ni su orden (eso ya vive en `next_question_from_missing_facts` / `_FUNNEL_STEPS`).
- No mover política de negocio al LLM (B→sencillo, escuelita, documento por residencia siguen en código).
- No rediseñar el esquema de `rh_lead_facts_v2` (cambio aditivo; sin DDL destructivo).
- No tocar la generación RAG de respuestas a dudas.

## Decisions

### D1: Híbrido por capa, no por campo

El LLM hace **lenguaje → concepto** para todos los campos en una pasada. Los catálogos deterministas hacen **concepto → válido** y el código hace **concepto → política**. La división es horizontal (por capa), no vertical (por campo).

- **Alternativa descartada:** "LLM para campos de texto libre, regex para campos con catálogo". Reproduce el desorden actual (extracción dispersa por campo) y deja la frontera difusa. La división por capa da un solo extractor y catálogos como validadores únicos.
- **Por qué:** meter la clasificación de unidad (`torton`→NON_TARGET→escuelita) en un prompt mete política de negocio en un artefacto no auditable, no testeable determinísticamente y que driftea entre versiones del modelo.

### D2: El LLM reporta evidencia, no confianza

Salida por campo: `{value, explicit_marker, answered_direct_question}`. La confianza se **computa en código**:

```
conf = base
     + 0.3 si catálogo validó (solo campos con Capa 2)
     + 0.2 si explicit_marker  ("me llamo", "soy de", "vivo en", "vence en")
     + 0.2 si answered_direct_question (last_bot pidió ese campo)
corrección explícita (is_ya_reclamo) → override de escritura
```

- **Alternativa descartada:** pedir `confidence: 0.8` al LLM. Es otro valor alucinable y no auditable. Reportar hechos observables (¿hubo marcador? ¿respondió la pregunta?) sí es verificable.

### D3: Asimetría de la frontera — campos sin catálogo

Campos con Capa 2 (ciudad/Neo4j, unidad/catálogo, edad/rango, licencia/A-B-E) tienen red: una alucinación se rechaza. Campos de texto libre (nombre, expiración, pregunta embebida) **no tienen red**. Regla para estos:

- **No persistir sin anclaje:** un valor de texto libre se persiste solo si hay `explicit_marker` **o** `answered_direct_question`. Un nombre suelto en un mensaje que no preguntaba nombre no se escribe (mata "Nombre: Hola").

### D4: Política de escritura gobernada por confianza (BREAKING)

```
HOY:    fact_value = EXCLUDED.fact_value                          (siempre pisa)
        confidence = GREATEST(old, new)                           (solo sube)

TARGET: fact_value = nuevo  SI  new.confidence ≥ old.confidence
                             O  new.is_explicit_correction
        confidence = la del valor que ganó                        (no GREATEST ciego)
```

Protege el dato fuerte de ruido; deja pasar la corrección genuina (que llega con marcador, vía `is_ya_reclamo`).

- **Riesgo:** un cambio legítimo de valor con confianza igual o menor sin marcador de corrección no se aplicaría. Mitigación: la corrección real casi siempre trae marcador ("no, es...", "me equivoqué"), que el TIPC ya detecta; el shadow mode mide cuántas escrituras cambiarían antes de cortar.

### D5: Contrato `TurnExtraction`

```python
@dataclass
class FieldValue:
    value: str | None
    explicit_marker: bool          # hubo "me llamo"/"soy de"/"vence en"...
    answered_direct_question: bool # last_bot pidió este campo

@dataclass
class TurnExtraction:
    fields: dict[str, FieldValue]  # candidate.name, candidate.city, candidate.age, ...
    embedded_question: str | None  # "cuánto pagan el km"
    signals: TurnIntentSignals     # absorbe TIPC (is_ya_reclamo, no_road_experience, ...)
```

Capa 2/3 consumen `fields` y producen los facts canónicos validados + confianza. El orquestador consume `embedded_question` y `signals`.

### D6: Un punto de extracción, antes de bifurcar

`extract_turn` se llama una vez al inicio del turno (en el worker, antes de `handle_message` y del guard). El resultado se pasa a ambos. Se elimina la re-extracción y el "quién corre último": el reply se decide sobre un único `TurnExtraction`.

## Risks / Trade-offs

- [Una sola pasada LLM falla → turno sin extracción] → Fallback: si el JSON no parsea, degradar a "no se extrajo nada este turno" (el funnel re-pregunta), nunca a regex-adivinanza. El turno siguiente reintenta.
- [Shadow duplica costo LLM durante migración] → Aceptable y acotado: shadow corre solo mientras se valida paridad; se mide y se corta. Neto post-corte: ~8-10 llamadas → ~2-3.
- [Política de escritura BREAKING rompe correcciones existentes] → Shadow registra cada divergencia de escritura (qué valor habría ganado hoy vs target) antes de activar.
- [El LLM 8b-instant no rinde el JSON estructurado completo] → Evaluar `llama-3.3-70b` para el extractor (más capaz en JSON multi-campo); medir latencia vs calidad en shadow.
- [Catálogo de ciudad (Neo4j) no cubre una ciudad real que el LLM sí entiende] → Capa 2 no debe rechazar duro; ciudad sin match queda como texto crudo de baja confianza (no se pierde, no se afirma).

## Migration Plan

1. Crear `app/knowledge/turn_extractor.py` con `extract_turn` + `TurnExtraction` (sin wirear).
2. Shadow: llamar `extract_turn` en el worker log-only, comparar su salida contra la extracción actual fact-por-fact; loggear divergencias (incluida la decisión de escritura).
3. Implementar Capa 2/3 deterministas consumiendo `TurnExtraction` (reusan Neo4j, domain_catalog, rangos existentes).
4. Nueva política de `upsert_lead_fact` detrás de flag; shadow mide divergencias de escritura.
5. Corte: cuando shadow muestre paridad o mejora, el extractor unificado pasa a ser el path vivo; se eliminan los `_SYSTEM` por-campo y los gates regex.
6. Rollback: el flag revierte al path actual sin redeploy.

## Open Questions

- ¿El extractor unificado usa `llama-3.3-70b` (mejor JSON, ~mayor latencia) o se queda en `8b-instant`? Decidir con datos de shadow.
- ¿`embedded_question` la resuelve el extractor (texto) y el orquestador la rutea, o el extractor ya marca el intent de la duda? Inclinación: solo extraer el texto; el routing sigue en el orquestador.
- ¿La confianza base y los pesos (+0.3/+0.2) se calibran con shadow o se fijan por diseño y se ajustan después?
- ¿`call_window` (scheduling) entra en el extractor unificado o queda como paso determinista aparte por su dependencia de `classify_call_window`?

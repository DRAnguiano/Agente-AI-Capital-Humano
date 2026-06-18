# Design — business-route-shadow-classifier

## Principio de diseño

```
LLM (lenguaje)        → primary_intent, secondary_intents  [conversacional, no reglas]
Catálogo de dominio   → explicit_facts, vehicle_type        [datos, no regex]
Reglas de negocio     → business_signals, ambiguity_flags   [deterministas, en contrato]
Policy router         → valida, no inventa                  [guard, no generador]
Shadow output         → log/CSV, no routing vivo            [observable, no activo]
```

Las reglas de negocio críticas (tipo de unidad, jerga ambigua, experiencia no-objetivo,
CECATI, B1, reingreso) SHALL vivir en el **contrato del clasificador** y en los
**catálogos de dominio**, no solo en RAG ni prompts ad-hoc.

## Capas del pipeline (shadow)

```
texto candidato
  → [existente] classify_message()          → primary_intent, secondary_intents, answers
  → [nuevo] extract_explicit_facts()         → explicit_facts  (catálogo, sin regex ad-hoc)
  → [nuevo] detect_business_signals()        → business_signals, ambiguity_flags
  → [nuevo] policy_router_validate()         → valida evidencia, rechaza inventados
  → [nuevo] BusinessRouteOutput (schema)     → output estructurado completo
  → [shadow] log/CSV, sin escribir DB
```

## Contrato de output (schema propuesto)

```python
@dataclass
class ExplicitFact:
    value: str
    evidence: str        # substring literal del mensaje candidato
    confidence: float    # 0.0 – 1.0; < 0.85 → no emitir como confirmed

@dataclass
class BusinessSignal:
    name: str            # enum: BUSINESS_ROUTES catalog
    evidence: str
    confidence: float

@dataclass
class AmbiguityFlag:
    name: str            # enum: vehicle_type_ambiguous, etc.
    evidence: str

@dataclass
class BusinessRouteOutput:
    primary_intent: str
    secondary_intents: list[str]
    explicit_facts: dict[str, ExplicitFact]   # "experience.vehicle_type": ExplicitFact(...)
    business_signals: list[BusinessSignal]
    ambiguity_flags: list[AmbiguityFlag]
    requires_human: bool
    safety_notes: list[str]
```

Ejemplo para "Me interesa para sencillo":

```json
{
  "primary_intent": "candidate_interest",
  "secondary_intents": [],
  "explicit_facts": {
    "experience.vehicle_type": {
      "value": "sencillo",
      "evidence": "Me interesa para sencillo",
      "confidence": 0.95
    }
  },
  "business_signals": [
    {"name": "objetivo_full_sencillo", "evidence": "Me interesa para sencillo", "confidence": 0.95}
  ],
  "ambiguity_flags": [],
  "requires_human": false,
  "safety_notes": []
}
```

Ejemplo para "Busco información, soy operador de 5ta rueda":

```json
{
  "primary_intent": "vacancy_question",
  "secondary_intents": [],
  "explicit_facts": {},
  "business_signals": [
    {"name": "jerga_ambigua_falta_unidad", "evidence": "5ta rueda", "confidence": 0.9}
  ],
  "ambiguity_flags": [
    {"name": "vehicle_type_ambiguous", "evidence": "5ta rueda"}
  ],
  "requires_human": false,
  "safety_notes": []
}
```

## Catálogo de business_signals (rutas de negocio)

| signal | condición de emisión | requires_human |
|---|---|---|
| `objetivo_full_sencillo` | `vehicle_type = full\|sencillo` (confirmado) | false |
| `jerga_ambigua_falta_unidad` | `quinta rueda`/`tráiler`/`trailero`/`tractocamión`/`operador` sin full/sencillo | false |
| `considerar_escuelita_transmontes` | torton/rabón/reparto local/interurbano/similares | false |
| `cecati_sugerido` | sin experiencia explícita en carretera | false |
| `considerar_operador_b1` | mención B1/Estados Unidos/USA/EEUU/inglés para EUA | true |
| `reingreso_verificar` | mención reingreso/ya trabajé ahí/quiero volver | true |
| `seguimiento_llamada` | cierre de conversación / confirmación / seguimiento | false |
| `pago_condiciones` | pregunta explícita de pago/sueldo/condiciones | false |
| `documentos_requisitos` | pregunta de documentos/requisitos | false |
| `ubicacion_base_traslado` | pregunta de ciudad/base/traslado | false |
| `vacante_info_general` | pregunta general de vacante / saludo / información | false |
| `otros_rag` | intención fuera del catálogo anterior | false |

## Reglas de vehicle_type (deterministas, catálogo)

Reutiliza `domain_catalog.VEHICLE_TERMS` — no se duplica lógica:

| término (normalizado) | status | business_signal |
|---|---|---|
| `full`, `fulero` | CONFIRMED `full` | `objetivo_full_sencillo` |
| `sencillo` | CONFIRMED `sencillo` | `objetivo_full_sencillo` |
| `quinta rueda`, `5ta rueda`, `trailer`, `traila`, `tractocamion` | NEEDS_CLARIFICATION | `jerga_ambigua_falta_unidad` |
| `camion` | NEEDS_CLARIFICATION (ambiguo) | no emite señal; funnel preguntará |
| `torton`, `rabon`, `reparto`, `carga local`, `camioneta` | NON_TARGET | `considerar_escuelita_transmontes` |

## Regla de evidencia

Un fact o señal SHALL emitirse solo si:
- Existe una cadena literal en el mensaje que lo evidencie (no inferencia del contexto).
- La confianza es ≥ 0.85 para `explicit_facts` confirmados.
- Si hay duda → emitir `ambiguity_flags`, no fact confirmado.

## Fuera de alcance (este change)

- No reemplazar `intent_classifier.py`.
- No modificar `knowledge_orchestrator.py` ni el flujo vivo.
- No activar routing de producción (shadow only).
- No OCR ni interpretación de imágenes/documentos.
- No integración con DB ni Chatwoot.
- La activación productiva es un change posterior, con prerequisito ≥ 80% PASS_STRONG
  en el harness QA de 224 casos.

## Frase de lenguaje de vigencia

El sistema SHALL usar `vence`/`vigencia`/`vencimiento`. SHALL NOT usar `caduca`/`caducidad`.

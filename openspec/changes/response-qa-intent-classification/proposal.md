## Why

La matriz de preguntas reales (`tests/fixtures/response_qa/matriz_qa.csv`, 224 casos)
muestra que el sistema actual no tiene cobertura verificable para las rutas críticas de
clasificación. El intent classifier existente (`app/knowledge/intent_classifier.py`) opera
correctamente para el contrato multi-intent interno, pero las rutas de respuesta
(vacante, escuelita, CECATI, B1, reingreso, documentos) no están documentadas como
contrato verificable ni enlazadas con las labels que deben emitirse.

Hallazgos concretos de la matriz:
- 81/224 preguntas esperan ruta `vacante_info_general` — la más común y más propensa
  a frases prohibidas legacy (`quinta rueda/full`).
- 22/224 preguntas son `pago_condiciones` → label `requiere_revision_ch` — el sistema
  no debe fabricar cifras.
- 13 preguntas son prioridad Alta — ninguna tiene `resultado_actual` registrado todavía.
- `frases_prohibidas` comunes a todas las filas: `quinta rueda/full`, `sencillo (escuelita)`,
  `Capital Humano valida viabilidad`, `disponible_acudir`.

## What Changes

- **OpenSpec contract**: enlace entre `route_esperada_sugerida` de la matriz y los intents
  del clasificador + las labels permitidas por ruta.
- **Script QA read-only** (`scripts/qa_response_matrix.py`): corre la matriz contra el
  sistema actual, genera reporte CSV con status PASS/FAIL/GAP_FUTURO/REVIEW/ERROR.
- **Frases prohibidas globales y por ruta**: documentadas aquí, verificadas en el script
  sin regex como fuente de verdad.
- **Diseño futuro de `classify_intent` cerrado** (shadow, no activa flujo vivo todavía):
  enum de intents cerrado + salida validada + modo shadow.

## What Does NOT Change

- El flujo productivo (`app.py`, `tasks_chatwoot.py`, `knowledge_orchestrator.py`).
- El `intent_classifier.py` existente (LLM-based, contrato interno multi-intent).
- La lógica de labels (`calculate_candidate_labels`).
- La DB ni Chatwoot.

## Intents de Ruta — Catálogo Cerrado

Estos son los valores válidos de `route_esperada_sugerida` en la matriz y su semántica
en el sistema:

| route | intent_classifier mapping | labels esperadas |
|---|---|---|
| `vacante_info_general` | `vacancy_question` / `greeting` | `seguimiento` |
| `ubicacion_base_traslado` | `logistics_question` | `falta_ciudad` |
| `documentos_requisitos` | `documents_question` | `documentos` |
| `pago_condiciones` | `pay_question` | `requiere_revision_ch` |
| `objetivo_full_sencillo` | `candidate_answer` (vehicle_type=full/sencillo) | `objetivo_full_sencillo` |
| `seguimiento_llamada` | `candidate_interest` / `acknowledgement` | `llamada_pendiente`, `seguimiento` |
| `jerga_ambigua_falta_unidad` | `candidate_answer` (low conf / ambiguous unit) | `jerga_ambigua`, `falta_unidad` |
| `considerar_operador_b1` | `logistics_question` + B1/EUA signal | `considerar_operador_b1`, `requiere_agente`, `llamada_pendiente` |
| `cecati_sugerido` | `vacancy_question` (no road experience) | `cecati_sugerido` |
| `considerar_escuelita_transmontes` | `vacancy_question` (torton/rabón exp) | `considerar_escuelita_transmontes` |
| `reingreso_verificar` | `reingreso` | `reingreso_verificar`, `requiere_agente` |
| `otros_rag` | various (pay/logistics/docs out of primary catalog) | varies |

## Frases Prohibidas Globales

El sistema NUNCA debe incluir estas frases en respuestas al candidato:

```
quinta rueda/full
sencillo (escuelita)
Capital Humano valida viabilidad
disponible_acudir
caduca
caducidad
tenemos convenio con CECATI
```

Usar siempre: `vence`, `vencimiento`, `vigencia` (nunca `caduca`/`caducidad`).

## Reglas de Dominio — Verificables en QA

1. Full/sencillo = perfil objetivo. `objetivo_full_sencillo` se emite para ambos.
2. Sencillo no es escuelita. `considerar_escuelita_transmontes` nunca se emite para sencillo.
3. Quinta rueda/tráiler/trailero/trucker son señales ambiguas → `jerga_ambigua`, `falta_unidad`.
4. Torton/rabón/reparto/interurbano → `considerar_escuelita_transmontes`, no `objetivo_full_sencillo`.
5. Sin experiencia en carretera → `cecati_sugerido`, mensaje informativo, **sin convenio directo**.
6. B1/EUA → `considerar_operador_b1` + `requiere_agente`. Requiere validación humana.
7. Reingreso → `reingreso_verificar` + `requiere_agente`. Bot se detiene.
8. Documentos enviados como imagen: agradecer + indicar que por ahora no puede revisar por ese medio.

## Labels Prohibidas (nunca en output)

```
cecati
escuelita
disponible_acudir
```

## Diseño Futuro: classify_intent cerrado (shadow, no activa flujo)

Módulo propuesto: `app/intent/classifier.py` (nuevo, no reemplaza intent_classifier.py existente).

Salida esperada:
```python
{
    "intent": "considerar_operador_b1",  # enum cerrado (rutas de arriba)
    "confidence": 0.82,
    "rationale": "El candidato pregunta por vacante EUA y menciona inglés.",
    "requires_human": True,
    "suggested_labels": ["considerar_operador_b1", "requiere_agente"],
    "missing_fields": []
}
```

Reglas del clasificador futuro:
- Enum cerrado: solo los 12 intents de ruta del catálogo de arriba.
- Validación Pydantic / dataclass — no strings libres.
- Si `confidence < 0.6`: emitir `requiere_revision_ch`, no decidir ruta.
- No regex.
- No mutar estado.
- No reemplaza flujo vivo todavía.
- **Modo shadow**: clasifica y loggea, no decide flujo. Solo activa con flag de entorno.
- Prerequisito: 80%+ PASS en `qa_response_matrix.py` antes de activar en producción.

# Design — response-qa-intent-classification

## Contexto

El harness QA corre la matriz real de preguntas de candidatos
(`tests/fixtures/response_qa/matriz_qa.csv`, 224 casos) contra el sistema actual
en modo read-only, sin mutar DB ni Chatwoot. Detecta frases prohibidas, evalúa si el
intent conversacional es compatible con la ruta de negocio esperada, y distingue matches
fuertes de matches ambiguos.

## Por qué intents conversacionales ≠ rutas de negocio

El clasificador LLM existente (`intent_classifier.py`) devuelve intents conversacionales:
`candidate_interest`, `vacancy_question`, `logistics_question`, `pay_question`, etc.

Las rutas QA son rutas de negocio: `objetivo_full_sencillo`, `jerga_ambigua_falta_unidad`,
`considerar_escuelita_transmontes`, `seguimiento_llamada`, etc.

No existe un mapeo 1:1 entre ambos vocabularios. El harness define tablas de compatibilidad
(`ROUTE_STRONG`, `ROUTE_WEAK`) para distinguir:

- **PASS_STRONG**: hay un intent conversacional (primary o secondary) que confirma de forma
  sólida la ruta de negocio.
- **PASS_WEAK**: hay un intent que es compatible, pero se necesita confirmación del
  business_route futuro.
- **REVIEW_MAPPING**: el intent conversacional es razonable pero no hay match en las tablas.
- **CONTRACT_GAP**: la ruta no tiene mapping definido todavía.
- **ERROR**: excepción técnica.

## Capa de hechos de negocio (business_fact upgrade)

Para rutas donde un hecho explícito en el texto del candidato confirma la ruta mejor que el
intent conversacional, el harness extrae hechos usando el catálogo de dominio existente
(`normalize_domain_values.normalize_vehicle`):

- `"sencillo"` / `"full"` / `"fullero"` en el texto → `vehicle_type` confirmado →
  upgrade a PASS_STRONG para `objetivo_full_sencillo`.
- `"quinta rueda"`, `"tráiler"`, `"trailero"` → NEEDS_CLARIFICATION → no upgrade.
- `"torton"`, `"rabón"`, `"reparto"` → NON_TARGET → no upgrade.

## Frases prohibidas globales

Verificadas sobre la respuesta histórica del agente y (en `--mode full`) sobre la respuesta
nueva. Verificación literal, sin regex.

## Gaps detectados — bloque 50–100 (revisión manual)

Estos gaps quedan documentados como REVIEW_MAPPING intencional; no ampliar mappings para
cubrirlos artificialmente.

| qa_id | intent actual | ruta esperada | gap / acción |
|---|---|---|---|
| qa_0054 | `complaint` + `logistics_question` | `documentos_requisitos` | `complaint_with_candidate_interest`: respuesta empática + continuar perfilamiento. No mapear. |
| qa_0071 | `vacancy_question` | `jerga_ambigua_falta_unidad` | PASS_WEAK correcto. "5ta rueda" no confirma full ni sencillo. |
| qa_0072 | `complaint` | `seguimiento_llamada` | Requiere contexto de hilo (cita para licencia/apto). No mapear `complaint`. |
| qa_0078 | `vacancy_question` | `jerga_ambigua_falta_unidad` | PASS_WEAK correcto. Mismo criterio que qa_0071. |
| qa_0093 | `greeting` | `ubicacion_base_traslado` | `classifier_gap_location_question`: "¿Dónde se ubican?" clasificado erróneamente como saludo. No mapear `greeting`. |
| qa_0096 | `candidate_answer` | `pago_condiciones` | `classifier_gap_multi_intent`: pregunta de km, pagarés y rutas clasificada como respuesta. No mapear `candidate_answer`. Entrada RAG pendiente: pagarés en blanco. |
| qa_0100 | `on_route` | `ubicacion_base_traslado` | **CORREGIDO**: `on_route` agregado a ROUTE_STRONG de `ubicacion_base_traslado`. Circuito explícito = logística. |

### Nota sobre qa_0096 — entrada RAG pendiente

```text
Pregunta: ¿En el proceso firman pagarés en blanco?
Respuesta: No. En el proceso de contratación no se realizan ese tipo de prácticas.
Categoría: proceso_contratacion / condiciones
```

No tocar RAG todavía. Documentado para cuando se revisen fuentes de conocimiento.

## Decisiones clave

1. El harness es **read-only** siempre: ningún modo escribe en DB, Chatwoot ni send real.
2. El intent classifier existente **no se modifica** — solo se observa.
3. El harness extrae hechos de negocio usando el **catálogo de dominio existente** (datos,
   no regex ad-hoc).
4. `--mode dry` corre sin LLM: solo verifica frases prohibidas contra historico.
5. `--mode classify` llama `classify_message()` y evalúa intent vs ruta.
6. `--mode full` agrega `plan_and_respond` y verifica frases en la respuesta nueva.
7. El harness es la herramienta de validación del change futuro
   `business-route-shadow-classifier`; sus resultados (PASS_STRONG ≥ 80%) son prerrequisito
   para activar el shadow classifier en producción.

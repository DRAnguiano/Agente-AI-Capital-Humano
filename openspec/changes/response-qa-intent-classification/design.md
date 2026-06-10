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

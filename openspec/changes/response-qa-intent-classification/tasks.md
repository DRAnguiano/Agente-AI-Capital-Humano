# Tasks — response-qa-intent-classification

> Script read-only en `scripts/qa_response_matrix.py`.
> Sin commits ni push hasta que David lo apruebe.

## QA-1. Harness base — dry mode (DONE)
- [x] QA-1.1 Script `scripts/qa_response_matrix.py` con `--mode dry`: verifica frases
      prohibidas globales contra `agent_answer_historica`. Sin LLM.
- [x] QA-1.2 Matriz real `tests/fixtures/response_qa/matriz_qa.csv` (224 casos, 16 columnas)
      exportada desde `.xlsx` y versionada.
- [x] QA-1.3 `.gitignore`: `reports/` excluido (outputs, no versionar).
- [x] QA-1.4 Frases prohibidas globales documentadas y verificadas en el script:
      `quinta rueda/full`, `sencillo (escuelita)`, `Capital Humano valida viabilidad`,
      `disponible_acudir`, `caduca`, `caducidad`, `tenemos convenio con CECATI`.

## QA-2. Harness classify mode + throttling (DONE)
- [x] QA-2.1 `--mode classify`: llama `classify_message()` por cada pregunta, evalúa
      `primary_intent` y `secondary_intents` vs `route_esperada_sugerida`.
- [x] QA-2.2 Throttling completo: `--requests-per-minute`, `--tokens-per-minute`,
      `--estimated-tokens-per-call`, `--sleep-seconds`, `--max-retries`,
      `--retry-base-seconds`, `--daily-token-budget`, `--stop-before-daily-budget`.
- [x] QA-2.3 Incremental write + reanudación: `--start-index`, `--append`, flush por fila.
- [x] QA-2.4 Backoff lineal: espera `retry_base_seconds × attempt` ante rate limit.

## QA-3. mapping_status fino v3 (DONE)
- [x] QA-3.1 Tablas `ROUTE_STRONG` / `ROUTE_WEAK` por ruta (no monolito permisivo).
- [x] QA-3.2 `PASS_STRONG` / `PASS_WEAK` / `REVIEW_MAPPING` / `CONTRACT_GAP` / `ERROR`.
- [x] QA-3.3 Columnas: `mapping_strength`, `match_source`, `matched_intents`.
- [x] QA-3.4 `out_of_scope` eliminado de `seguimiento_llamada`.
- [x] QA-3.5 `document_submission` en `considerar_escuelita_transmontes` → REVIEW_MAPPING.

## QA-4. Business-fact upgrade (DONE)
- [x] QA-4.1 `_extract_vehicle_fact()`: reutiliza `normalize_domain_values.normalize_vehicle`
      + `applies_objetivo_full_sencillo` (catálogo de dominio, sin regex ad-hoc).
- [x] QA-4.2 Para `objetivo_full_sencillo`: `full`/`sencillo`/`fullero` en texto →
      upgrade a PASS_STRONG con `match_source=business_fact`.
- [x] QA-4.3 `quinta rueda`, `tráiler`, `torton`, `rabón` → no upgrade (NEEDS_CLARIFICATION /
      NON_TARGET respectivamente).
- [x] QA-4.4 Columnas nuevas en CSV: `profile_vehicle_type`, `business_fact_match`.

## QA-5. Validación baseline (PENDIENTE)
- [ ] QA-5.1 Correr `--priority Alta` (13 casos) → verificar PASS_STRONG ≥ 50%.
      Resultado actual: 7 STRONG / 5 WEAK / 1 REVIEW (`qa_alta_v3.1.csv`).
- [ ] QA-5.2 Correr `--limit 50` muestra completa → registrar baseline en `reports/`.
- [ ] QA-5.3 Correr los 224 casos completos → baseline final para `business-route-shadow-classifier`.
- [ ] QA-5.4 Verificar: ninguna frase prohibida global en historicos (PASS frases = 224/224).

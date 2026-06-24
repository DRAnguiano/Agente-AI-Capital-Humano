## ADDED Requirements

### Requirement: El harness es siempre read-only

El script QA SHALL ejecutarse en modo lectura: no escribe en DB, no envía mensajes a
Chatwoot, no muta leads ni conversaciones. Produce solo archivos bajo `reports/`.

#### Scenario: Ejecución sin efecto productivo
- **WHEN** el harness corre en cualquier modo (dry, classify, full)
- **THEN** no se produce ninguna escritura en PostgreSQL, Chatwoot ni Redis
- **AND** los archivos de salida se generan solo bajo `reports/`

### Requirement: mapping_status distingue fuerza del match intent-ruta

El harness SHALL evaluar si el intent conversacional (primary o secondary) es compatible
con la ruta de negocio esperada, distinguiendo entre match fuerte, débil y sin match.

#### Scenario: Intent fuerte produce PASS_STRONG
- **GIVEN** una pregunta cuyo `primary_intent` es `vacancy_question`
- **AND** la ruta esperada es `vacante_info_general`
- **WHEN** el harness evalúa el caso
- **THEN** `mapping_status = PASS_STRONG`
- **AND** `match_source = primary`

#### Scenario: Intent en secondary produce PASS_STRONG
- **GIVEN** `primary_intent = candidate_interest` y `secondary_intents = ["pay_question"]`
- **AND** la ruta esperada es `pago_condiciones`
- **WHEN** el harness evalúa el caso
- **THEN** `mapping_status = PASS_STRONG`
- **AND** `match_source = secondary`
- **AND** `matched_intents` contiene `pay_question`

#### Scenario: Intent débil produce PASS_WEAK
- **GIVEN** `primary_intent = documents_question`
- **AND** la ruta esperada es `vacante_info_general`
- **WHEN** el harness evalúa el caso
- **THEN** `mapping_status = PASS_WEAK`

#### Scenario: Sin match produce REVIEW_MAPPING
- **GIVEN** `primary_intent = out_of_scope`
- **AND** la ruta esperada es `seguimiento_llamada`
- **WHEN** el harness evalúa el caso
- **THEN** `mapping_status = REVIEW_MAPPING`
- **AND** `match_source = none`

### Requirement: Business-fact upgrade para objetivo_full_sencillo

Para la ruta `objetivo_full_sencillo`, el harness SHALL extraer hechos de negocio del
texto usando el catálogo de dominio existente (`normalize_domain_values`), no regex
ad-hoc. Un hecho confirmado (`full` o `sencillo` explícito) SHALL subir el mapping a
PASS_STRONG aunque el intent conversacional sea solo débil.

#### Scenario: "sencillo" explícito upgradea a PASS_STRONG
- **GIVEN** `candidate_question = "Me interesa para sencillo"`
- **AND** `primary_intent = candidate_interest`
- **AND** la ruta esperada es `objetivo_full_sencillo`
- **WHEN** el harness evalúa el caso
- **THEN** `mapping_status = PASS_STRONG`
- **AND** `match_source = business_fact`
- **AND** `profile_vehicle_type = sencillo`

#### Scenario: "quinta rueda" no upgradea
- **GIVEN** `candidate_question = "manejo quinta rueda"`
- **AND** la ruta esperada es `objetivo_full_sencillo`
- **WHEN** el harness evalúa el caso
- **THEN** `profile_vehicle_type = quinta_rueda`
- **AND** `mapping_status != PASS_STRONG` (permanece PASS_WEAK o REVIEW_MAPPING)

#### Scenario: "torton" no upgradea
- **GIVEN** `candidate_question = "manejo torton"`
- **AND** la ruta esperada es `objetivo_full_sencillo`
- **WHEN** el harness evalúa el caso
- **THEN** `profile_vehicle_type = torton`
- **AND** `mapping_status != PASS_STRONG`

### Requirement: Frases prohibidas globales verificadas sin regex

El harness SHALL verificar que las respuestas del agente no contengan frases prohibidas
globales usando comparación literal (no regex), en todos los modos.

#### Scenario: Respuesta con frase prohibida produce FAIL
- **GIVEN** `agent_answer_historica` contiene `"quinta rueda/full"`
- **WHEN** el harness corre en modo dry
- **THEN** `pass_forbidden_phrases = false`
- **AND** `status = FAIL`

#### Scenario: Respuesta limpia no falla por frases prohibidas
- **GIVEN** `agent_answer_historica` no contiene ninguna frase prohibida
- **WHEN** el harness corre en modo dry
- **THEN** `pass_forbidden_phrases = true`

### Requirement: Throttling respeta límites reales de Groq

En modo classify y full, el harness SHALL respetar los límites del tier free de Groq:
RPM 30, TPM 6000, daily 500K tokens. La espera efectiva entre llamadas SHALL ser
`max(sleep_override, 60/rpm, 60*tokens_per_call/tpm)`.

#### Scenario: Default 1.5 RPM produce espera ≥ 40s
- **GIVEN** `--requests-per-minute 1.5` y `--tokens-per-minute 6000`
- **AND** `--estimated-tokens-per-call 2800`
- **WHEN** el harness calcula la espera efectiva
- **THEN** `effective_sleep >= 40.0` segundos

#### Scenario: Reanudación por bloques con --start-index y --append
- **GIVEN** una corrida previa completó los primeros 50 casos
- **WHEN** se corre con `--start-index 50 --append`
- **THEN** el reporte existente se extiende sin sobrescribir los 50 anteriores

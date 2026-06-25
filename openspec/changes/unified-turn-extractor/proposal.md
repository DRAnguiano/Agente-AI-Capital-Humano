## Why

La extracción de facts del candidato está dispersa en ~12 prompts `_SYSTEM` y ~10 llamadas `call_groq_json` repartidas entre `current_turn.py` y `profile_extractor.py`, cada una para un solo campo y gateada por su propio regex (`if "nombre" in last_bot`, `if _expiry_hints`...). El mismo mensaje se extrae ~5 veces en dos módulos distintos, con dos escritores a `rh_lead_facts_v2`, y el reply lo decide "quién corre último" (el guard del worker pisa al orquestador). Esto produce ~8-10 llamadas LLM secuenciales por turno y bugs estructurales: campos que se pisan entre sí ("manejo full hace 10 años, licencia vence en 2 años" → `experience.years=2 años`), datos perdidos (edad no extraída), y alucinaciones sin filtro en campos de texto libre ("Nombre: Hola"). Añadir un campo nuevo hoy = nuevo prompt + nueva llamada + nuevo gate regex: insostenible.

## What Changes

- **Un único extractor de turno** (`extract_turn(message, last_bot_question, known_facts) -> TurnExtraction`) que reemplaza las ~5 rondas de extracción dispersas por **una sola pasada LLM** que devuelve todos los campos del perfil + señales de turno + pregunta embebida.
- **Arquitectura por capas (no por campo):**
  - **Capa 1 (LLM):** lenguaje → concepto crudo. Una pasada, todos los campos. Devuelve `{value, evidencia}` por campo, nunca un score de confianza.
  - **Capa 2 (determinista):** concepto → válido. Catálogos cerrados validan/normalizan (Neo4j ciudad, `domain_catalog` unidad, rango 18-75 edad, A/B/E licencia). Puede rechazar alucinaciones.
  - **Capa 3 (determinista, en código):** concepto → política. B→sencillo, NON_TARGET→escuelita, local→IMSS. **Nunca en el prompt.**
- **Confianza derivada de evidencia observable** (catálogo validó + marcador lingüístico explícito + respondió pregunta directa + corrección explícita), computada en código a partir de lo que el LLM reporta, no pedida al LLM.
- **BREAKING — política de escritura:** `upsert_lead_fact` deja de pisar el valor incondicionalmente. Nuevo: `fact_value` se actualiza solo si `conf_nueva ≥ conf_guardada` o hay marcador de corrección explícita. Hoy `fact_value = EXCLUDED.fact_value` siempre pisa y `confidence = GREATEST(...)`, dejando valores débiles con confianza heredada alta.
- **El regex como extractor (Capa 1) se elimina;** el regex/catálogo como validador (Capas 2-3) se conserva.
- **Absorción de TIPC:** `turn_intent_classifier` (8 señales, 1 llamada LLM sobre el mismo texto) se fusiona en el extractor unificado → señales + facts + pregunta embebida en un solo prompt.
- **Migración en shadow:** el extractor nuevo corre log-only en paralelo al actual detrás de feature flag; se compara extracción 1×1 en producción antes de cortar.

## Capabilities

### New Capabilities

- `unified-turn-extraction`: Un único punto de extracción por turno que produce un objeto `TurnExtraction` estructurado (facts + evidencia + señales + pregunta embebida) en una sola pasada LLM, consumido por funnel, nudge, ack, labels y persistencia.

### Modified Capabilities

- `profile-extraction`: La extracción de texto natural pasa de ~10 extractores por-campo gateados por regex a una sola pasada LLM con validación determinista posterior. Los catálogos (Neo4j, domain_catalog, rangos) se conservan como validadores.
- `lead-memory`: La política de escritura de `upsert_lead_fact` cambia: el valor solo se sobreescribe cuando la confianza nueva ≥ la guardada o hay corrección explícita.
- `message-orchestration`: El reply deja de decidirse por "quién corre último" (guard vs orquestador); el `TurnExtraction` se computa una vez antes de bifurcar y ambos paths leen de él.

## Impact

- `app/knowledge/current_turn.py` — elimina `_AGE_SYSTEM`, `_NAME_SYSTEM`, `_EXPERIENCE_YEARS_SYSTEM`, `_EXPIRATION_SYSTEM` y los gates regex de extracción; conserva validadores deterministas (rango edad, `_renewal_proof_state`).
- `app/lead_memory/profile_extractor.py` — elimina `_PROFILE_EXPIRATION_SYSTEM`, `_PROFILE_EXPERIENCE_YEARS_SYSTEM`, `_CITY_FALLBACK_SYSTEM`, `_CALL_WINDOW_SYSTEM`, `_EXPERIENCE_CONTEXT_SYSTEM`, `_RENEWAL_PROOF_SYSTEM`; conserva catálogos y normalización determinista.
- `app/knowledge/turn_intent_classifier.py` — absorbido por el extractor unificado (o reducido a parser del JSON).
- `app/lead_memory/repository.py` — `upsert_lead_fact` con política de escritura gobernada por confianza.
- `app/tasks_chatwoot.py` — el doble path (guard + orquestador) se reconcilia: una sola extracción al inicio del turno.
- `app/orchestrators/knowledge_orchestrator.py` — `handle_message` y `_build_funnel_nudge` consumen `TurnExtraction` en vez de re-extraer.
- Nuevo módulo: `app/knowledge/turn_extractor.py` (extractor unificado + contrato `TurnExtraction`).
- Feature flag para shadow mode durante la migración.

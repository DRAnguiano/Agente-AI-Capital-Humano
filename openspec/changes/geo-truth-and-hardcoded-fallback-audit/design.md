## Context

Auditoría read-only de la conversación 121 (candidato de "Chávez", 10:38 hrs). Hallazgos verificados contra el código vivo:

1. **Divergencia geográfica (P0).** La nota/labels usan `geo_utils.is_zm_laguna_canonical` → `local_laguna` (correcto). El reply de la ruta RAG/LLM afirmó "Como es de Chávez, se considera foráneo". El seed Neo4j SÍ mapea `chávez → Francisco I. Madero` (`neo4j_seed_hr_rules.cypher:296`) y `zm_laguna_localities.json` también — el seed no es el problema. La causa: cuando el guard se suprime por pregunta embebida ("¿cuánto pagan?"), la respuesta la genera el LLM, que **no recibe** `location.is_local_laguna` ni el catálogo en su prompt (`persona_config.py` no menciona residencia), así que improvisa.

2. **Lógica foráneo→documento duplicada (P1).** Bloques casi idénticos en `current_turn.py:458-477` y `knowledge_orchestrator.py:1626-1655`. Ambos arrastran listas legacy de 5 ciudades (`LOCAL_LAGUNA` `current_turn.py:34`; `_LOCAL_LAGUNA` `knowledge_orchestrator.py:1569`) en `OR` con `is_local_laguna`. Esas listas NO incluyen Francisco I. Madero ni comarca ampliada → si la señal canónica faltara, Chávez caería como foráneo.

3. **Sugerencia de llamada sin horario (P1).** `_profile_complete_closing()` (`current_turn.py:13`) SÍ checa `is_business_hours()` ✓. Pero `followup/templates.py:124-139` sugiere "¿le hacemos una llamada?" sin chequeo, y la ruta RAG/LLM puede improvisar lo mismo. A las 10:38 (en horario) el copy correcto es "el equipo te contacta".

4. **Voz de equipo rota (P2).** Intro hardcodeado `tasks_chatwoot.py:128` "asistente de **Capital Humano**" y templates "que **Capital Humano** le indique" violan la regla de persona (`persona_config.py:15-18`).

## Goals / Non-Goals

**Goals:**
- Una sola fuente de residencia (`location.is_local_laguna` desde el catálogo) consumida idénticamente por nota, labels, funnel, orquestador y reply.
- Eliminar listas `LOCAL_LAGUNA`/`_LOCAL_LAGUNA` como fuente de residencia.
- De-duplicar la lógica foráneo→documento en una función de dominio.
- Toda sugerencia de llamada decidida por `is_business_hours()`.
- Voz de equipo en intros y templates de derivación.

**Non-Goals:**
- Tocar el seed Neo4j o `zm_laguna_localities.json` (ya correctos).
- Cambiar el esquema de facts, webhooks o el scheduler de followup (sólo su copy).
- Rediseñar el routing guard/RAG; sólo asegurar que la ruta RAG reciba o respete las señales deterministas.

## Decisions

- **Señal de residencia inyectada al prompt RAG/LLM, no inferida.** Pasar `location.is_local_laguna` resuelto al contexto del LLM y añadir regla explícita en `persona_config.py`: "Nunca clasifiques residencia (local/foráneo) por tu cuenta; usa sólo la señal del sistema. Si no hay señal, no afirmes residencia." Alternativa descartada: dejar que el LLM lea el catálogo (re-introduce segunda fuente de verdad).
- **Helper de dominio único** `residency_document_question(facts)` que centraliza la regla local→IMSS / foráneo→cartas, llamado tanto desde `current_turn` como desde `knowledge_orchestrator`. Elimina la duplicación.
- **`is_local` siempre desde `is_zm_laguna_canonical`** (sin `OR lista_legacy`). Borrar `LOCAL_LAGUNA` y `_LOCAL_LAGUNA`.
- **Gate de llamada centralizado.** Cualquier copy que sugiera llamada pasa por un helper que consulta `is_business_hours()`; en horario → "el equipo te contacta".
- **Intro como voz de equipo.** Cambiar el default de `ASSISTANT_PUBLIC_INTRO` a una fórmula de equipo (sin "Capital Humano" como tercero).

## Risks / Trade-offs

- **Riesgo bajo**: se consolida sobre helpers ya existentes (`geo_utils`, `business_hours`); no se introduce infraestructura nueva.
- **Trade-off**: inyectar la señal de residencia al prompt agrega un campo al contexto del LLM; aceptable frente a la alucinación de "foráneo".
- **Regresión potencial**: al borrar las listas legacy, cualquier ruta que dependiera implícitamente de ellas debe quedar cubierta por `is_zm_laguna_canonical`; mitigado con grep exhaustivo y prueba del caso "Chávez".
- **Verificación**: reproducir conversación 121 ("soy de Chávez, ¿cuánto pagan?") y confirmar que nota y reply coinciden en "local" y que no se sugiere llamada en horario.

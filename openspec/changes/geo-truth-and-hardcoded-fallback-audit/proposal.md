## Why

Auditoría read-only disparada por un caso real (conversación 121, candidato de "Chávez"): la **nota IA** etiquetó correctamente `local_laguna` (vía `geo_utils.is_zm_laguna_canonical`), pero el **reply al candidato** dijo "Como es de Chávez, se considera foráneo" y, a las 10:38 (dentro de horario), sugirió coordinar una llamada en vez de decir que el equipo lo contacta. Hay **dos fuentes de verdad geográficas** y **fallbacks de llamada/horario hardcodeados** que contradicen la nueva arquitectura (catálogo ZM Laguna como fuente única + política de horario centralizada). El sistema debe perfilar, no improvisar derivaciones ni residencia.

La causa raíz no es el seed (el seed mapea `chávez → Francisco I. Madero` correctamente, `neo4j_seed_hr_rules.cypher:296`): es que el conocimiento determinista de residencia (`location.is_local_laguna`) **no llega a la ruta RAG/LLM**, y que la lógica foráneo→documento y la sugerencia de llamada están **duplicadas y hardcodeadas** en varios módulos, algunos sin chequeo de horario.

## What Changes

- **Residencia como señal determinista única**: `location.is_local_laguna` (derivado del catálogo ZM Laguna) debe ser la ÚNICA fuente de "local vs foráneo". El LLM/RAG NUNCA debe inferir residencia desde el nombre crudo de la ciudad; recibe la señal ya resuelta o se le prohíbe el tema.
- **Eliminar listas legacy hardcodeadas** `LOCAL_LAGUNA` (`current_turn.py:34`, `:461`) y `_LOCAL_LAGUNA` (`knowledge_orchestrator.py:1569`, `:1632`): sólo 5 ciudades, NO incluyen Francisco I. Madero ni comarca ampliada → falso "foráneo" si la señal canónica falta. Reemplazar por `is_zm_laguna_canonical`.
- **De-duplicar la lógica foráneo→documento**: hoy está replicada casi idéntica en `current_turn.py:458-477` y `knowledge_orchestrator.py:1626-1655`. Unificar en una sola función de dominio.
- **Política de contacto/llamada centralizada por horario**: toda sugerencia de llamada debe pasar por `is_business_hours()`. En horario → "nuestro equipo te contacta"; fuera de horario → mensaje de llamada/agenda. Hoy `_profile_complete_closing()` (`current_turn.py:13`) sí lo checa, pero `followup/templates.py:124-139` y la ruta RAG/LLM pueden sugerir llamada sin chequeo.
- **Corregir voz de equipo en fallbacks**: el intro hardcodeado `tasks_chatwoot.py:128` ("asistente de **Capital Humano**") y los templates foráneos ("que **Capital Humano** le indique") violan la regla de persona "habla como parte del equipo, no como tercero".
- **No-BREAKING**: cambios de comportamiento de reply; sin cambios de API ni de esquema de datos.

## Capabilities

### New Capabilities
- `geo-residency-single-source`: la residencia local/foránea se computa una sola vez desde el catálogo ZM Laguna y es consumida idénticamente por nota, labels, funnel y reply (incl. RAG/LLM); prohíbe inferencia de residencia por el LLM.
- `business-hours-contact-policy`: toda sugerencia de llamada/contacto se decide por `is_business_hours()`; dentro de horario el mensaje es "el equipo te contacta", fuera de horario es el mensaje de llamada/agenda.

### Modified Capabilities
- `message-orchestration`: elimina la lógica foráneo→documento duplicada y las listas `_LOCAL_LAGUNA` hardcodeadas; la ruta RAG/LLM deja de improvisar residencia y horario.
- `zm-laguna-locality-catalog`: el catálogo es la fuente única de residencia para TODAS las rutas de respuesta, no sólo para labels/nota.

## Impact

- **Código**: `app/knowledge/current_turn.py` (listas legacy, foráneo template, cierre), `app/orchestrators/knowledge_orchestrator.py` (foráneo template duplicado `:1626-1655`, `_LOCAL_LAGUNA :1569`), `app/tasks_chatwoot.py` (intro `:128`), `app/followup/templates.py` (sugerencia de llamada sin horario), `app/persona_config.py` (regla explícita: no inferir residencia, no sugerir llamada en horario).
- **Datos/seed**: ninguno — el seed Neo4j y `zm_laguna_localities.json` ya son correctos; no se tocan.
- **Sistemas**: respuestas al candidato vía Chatwoot; sin impacto en webhooks, DB ni followup scheduler (sólo el copy de sus templates).
- **Riesgo**: bajo — consolidación sobre helpers ya existentes (`geo_utils`, `business_hours`); read-only ahora, implementación posterior vía `/opsx:apply`.

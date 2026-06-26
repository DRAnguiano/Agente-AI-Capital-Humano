## Why

Las conversaciones 121 (David, residente de Francisco I. Madero — local de la ZM Laguna) y 122 (candidato nuevo preguntando requisitos) expusieron inconsistencias que sobreviven al fix `geo-truth-and-hardcoded-fallback-audit`. En 121: el bot repitió **4 veces** la misma pregunta de documento laboral (loop), persistió `location.is_local_laguna: false` para una ciudad local mientras la etiqueta era `local_laguna`, y la data de respuesta contradice el catálogo geográfico y reintroduce la voz "Capital Humano". En 122: el saludo se emitió **duplicado** (intro de Mundo dos veces), el LLM **alucinó** un requisito inexistente ("al menos 5 años de experiencia"), listó documentos de expediente (RFC, CURP, INE…) como requisitos inmediatos contradiciendo la política del corpus, y mezcló registro tú/usted. Son fallas de **consistencia de contrato** (valores canónicos y tipos), de **consistencia de la data de respuesta** frente al catálogo, política y registro, y de **ensamblado de la respuesta** (saludo + nudge).

## What Changes

- **P0-A — Gate de canonicalización de `documents.proof`.** Toda escritura de `documents.proof` (incluido el path del LLM `answers_to_persist` / `intent_classifier`) debe normalizarse al contrato `{cartas | semanas_imss | ninguno}` antes de persistir. Hoy el LLM persistió texto libre `"cartas laborales"`, que `_has_labor_document` nunca reconoce, causando el loop de re-pregunta.
- **P0-B — Representación única de `location.is_local_laguna`.** Unificar el valor persistido a string `"true"`/`"false"` en TODOS los puntos de escritura (`current_turn.py:381`, `tasks_chatwoot.py:422`), de modo que coincida con la comparación `== "true"` de los consumidores (`current_turn.py:44`, `intent_orchestrator.py:33`). Hoy se asigna el `bool` de `is_zm_laguna_canonical(...)`, que nunca matchea la comparación de string y produjo `false` para una ciudad local.
- **P1 — Alinear el corpus al catálogo.** `data/02_documentos_requisitos.md` define "Local de la ZM Laguna" como solo 4 municipios (Torreón, Gómez Palacio, Lerdo, Matamoros); ampliar/redactar para no enumerar una lista cerrada que omite Francisco I. Madero, Chávez y la `comarca_ampliada` ya presentes en `zm_laguna_localities.json`, evitando que el RAG clasifique "foráneo" por encima de la señal determinista.
- **P1 — Voz de equipo en la data autorizada.** Reemplazar "Capital Humano" como tercero por "nuestro equipo" en `data/02_documentos_requisitos.md` (líneas 129 y 137), que el RAG emite literal.
- **F1/F2 — Saludo único y conciso (conv 122).** En primer contacto con pregunta embebida, la respuesta NO debe contener el intro de Mundo dos veces: el nudge del funnel para un candidato sin nombre no debe ser el `GREETING_REPLY` completo cuando la respuesta ya saludó. Reducir la repetición verbosa ("nuestro equipo lo contactará" ×3-4).
- **F3 — Sin alucinar requisitos (conv 122).** La respuesta MUST NOT afirmar umbrales o requisitos no presentes en el corpus (p. ej. "al menos 5 años de experiencia", que no existe en `data/`).
- **F4 — Respetar la política de precalificación del corpus (conv 122).** La respuesta de requisitos no debe presentar documentos de expediente (RFC, CURP, INE, NSS…) como inmediatos; deben enmarcarse como "más adelante, si su proceso avanza" según `data/02_documentos_requisitos.md:23,36,47,55`.
- **F5 — Registro consistente en el corpus (conv 122).** Unificar el registro del corpus a **usted** (registro del saludo/persona), eliminando la mezcla tú/usted (`data/02_documentos_requisitos.md:74,88,111,119`) que se propaga al LLM.

## Capabilities

### New Capabilities
- `fact-value-canonicalization`: Contrato de normalización de valores de fact al persistir (`documents.proof` al vocabulario `{cartas|semanas_imss|ninguno}`, y la representación canónica string `"true"`/`"false"` de señales booleanas como `location.is_local_laguna`), garantizando que productores y consumidores compartan el mismo vocabulario y tipo.

### Modified Capabilities
- `rag-knowledge-corpus`: La data de respuesta no debe enumerar una lista cerrada de municipios locales que contradiga el catálogo `zm-laguna-locality-catalog`, ni emitir "Capital Humano" como tercero; no debe afirmar requisitos ausentes del corpus; debe respetar la política de precalificación (RFC/expediente "más adelante"); y debe usar un registro consistente (usted).
- `message-orchestration`: En primer contacto con pregunta embebida, la respuesta ensamblada no debe duplicar el intro de saludo ni el nudge del funnel.

## Impact

- **Código:** `app/lead_memory/profile_extractor.py` (canonicalización de `proof` en el path LLM/answers), `app/knowledge/intent_classifier.py` (o donde se materializa `answers_to_persist`), `app/knowledge/current_turn.py:381`, `app/tasks_chatwoot.py:422` (representación string de `is_local_laguna`), ensamblado del nudge de saludo en primer contacto (`app/orchestrators/knowledge_orchestrator.py:59-66` `_GREETING_INTRO`/`GREETING_REPLY` + punto donde se concatena el nudge a la respuesta RAG).
- **Data de respuesta:** `data/02_documentos_requisitos.md` (líneas 20, 70 lista de municipios; 129, 137 voz de equipo; 74, 88, 111, 119 registro tú→usted; encuadre RFC/expediente). Posible refuerzo del prompt de grounding contra alucinación de requisitos. Requiere reindexar el corpus RAG tras editar.
- **Sin migración de datos** ni cambios de API. Riesgo bajo: cambios de normalización, copy y ensamblado.
- **Verificación:** reproducir conv 121 (David, Francisco I. Madero, "tengo cartas laborales") → un solo cierre del paso documental, `is_local_laguna: "true"`, label `local_laguna`, sin "Capital Humano" ni "foráneo". Reproducir conv 122 ("me interesa la vacante, ¿qué necesito?") → un solo intro de saludo, sin "5 años", RFC enmarcado como posterior, registro usted consistente.

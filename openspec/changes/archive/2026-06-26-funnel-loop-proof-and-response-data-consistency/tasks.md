## 1. Canonicalización de `documents.proof` (P0-A — loop)

- [x] 1.1 Localizado: el productor es `turn_extractor.extract_turn` (alimenta `_current_turn_facts` del guard y `pre_validated_facts` de persistencia); el contrato pide `{cartas|semanas_imss|ninguno}` (`turn_extractor.py:110`) pero el LLM devolvió "cartas laborales" crudo.
- [x] 1.2 Añadido `canonicalize_proof(value)` en `current_turn.py` junto a `_has_labor_document` (cartas/membretadas/laboral→cartas; semanas/imss/cotizadas→semanas_imss; negaciones→ninguno; no mapeable→None).
- [x] 1.3 Invocado en el productor `turn_extractor.py:178` (normaliza/elimina el field si no mapea, igual que `candidate.city`) y en el límite de persistencia `knowledge_orchestrator.py` (loop `pre_validated_facts`: canonicaliza o `continue` si None).
- [ ] 1.4 Verificar que `_has_labor_document` cierra el paso cuando el LLM devuelve "cartas laborales" (ya normalizado a "cartas"). → grupo 8

## 2. Representación string de `location.is_local_laguna` (P0-B)

- [x] 2.1 En `app/knowledge/current_turn.py:381`: asigna `"true"/"false"` (string).
- [x] 2.2 En `app/tasks_chatwoot.py:422`: misma conversión a string `"true"/"false"`.
- [x] 2.3 Grep confirmado: no quedan asignaciones bool crudas; consumidores (`current_turn.py:44`, `intent_orchestrator.py:33,50`, `chatwoot_note_sync.py:555`) comparan `== "true"` y ahora matchean.

## 3. Data de respuesta: alinear corpus al catálogo (P1)

- [x] 3.1 En `data/02_documentos_requisitos.md:20,70`: lista abierta con ejemplos + Francisco I. Madero, remite al catálogo.
- [x] 3.2 Grep en `data/`: corregidas 2 copias más (`00_politicas_generales.md:122`, `04_bases_rutas.md:114`) al mismo criterio.

## 4. Data de respuesta: voz de equipo (P1)

- [x] 4.1 En `data/02_documentos_requisitos.md:129,137`: "Capital Humano" → "nuestro equipo".
- [x] 4.2 Grep en `data/`: corregidas respuestas autorizadas en `01_pago_prestaciones.md:52` y `04_bases_rutas.md:23`. Se conservan menciones internas no-respondibles (definición de persona `00_politicas:5,32`, la regla `:77`, nota "confirmar con" `01_pago:11`, metadata JSON).

## 5. Saludo único y conciso en primer contacto (F1 / F2)

- [x] 5.1 Localizado: `knowledge_orchestrator.py:1893-1897` antepone la respuesta embebida (que ya saluda) al `_greeting_reply` completo (segundo intro) cuando `intent=="greeting"`.
- [x] 5.2 En la rama `greeting` (línea ~1876): si hay pregunta embebida no-derivada, el saludo se reduce a `_greeting_followup_question()` (solo el siguiente dato del funnel, sin intro); helper nuevo en `knowledge_orchestrator.py`. Concatenación tolera reply vacío (sin `\n\n` colgando).
- [x] 5.3 Instrucción 10 de concisión en `context_builder.build_generation_prompt`: "nuestro equipo lo contactará" a lo sumo una vez por mensaje.

## 6. Data: no alucinar requisitos, política RFC y registro (F3 / F4 / F5)

- [x] 6.1 (F3) Instrucción 11 en `context_builder`: prohíbe afirmar umbrales ausentes, en particular mínimos de años de experiencia ("al menos N años"). Grep confirma que `data/` no contiene ningún "al menos N años".
- [x] 6.2 (F4) Instrucción 12 en `context_builder`: RFC/CURP/INE/NSS/comprobantes se enmarcan como "más adelante, si el proceso avanza", no inmediatos. El corpus ya lo sostiene (`02_documentos:23,36,47,55`; `00_politicas:125`).
- [x] 6.3 (F5) Registro **usted** unificado: `02_documentos:74,88,111,119`; barrido a `00_politicas:90,154,176,184`, `03_seguridad:52,54,62`, `04_bases:46,152`, `05_jerga:96,118,128,149`, `01_pago:48`. Grep final: sin formas de "tú" en respuestas autorizadas.

## 7. Reindexado y build

- [x] 7.1 Reindexado vía `POST /reindex`: 6 archivos, 57 chunks, collection `rh_rag_docs_bge_m3` (BAAI/bge-m3).
- [x] 7.2 `docker compose build worker api && docker compose up -d worker api` — ambos `Up`.

## 8. Verificación

- [x] 8.1 Reproducido conv 121 (`api:verify-conv121-001`, "Francisco I. Madero" + "cuento con mis cartas laborales membretadas"): `documents.proof = "cartas"` (canonicalizado, no texto crudo); el siguiente turno no re-pregunta el documento → loop cerrado.
- [x] 8.2 `is_zm_laguna_canonical("Francisco I. Madero")` → asignación `"true"` (string); consumidor `current_turn.py:44 == "true"` matchea (Torreón→"true", Matehuala→"false", todos `str`). Señal runtime del guard (no se persiste a `rh_lead_facts_v2`).
- [x] 8.3 Corpus alineado al catálogo (listas abiertas + Francisco I. Madero + remisión a catálogo en `00,02,04`); grep confirma sin listas cerradas de 4 municipios.
- [x] 8.4 Grep: respuestas autorizadas sin "Capital Humano" como tercero; solo quedan menciones internas no-respondibles.
- [x] 8.5 Reproducido conv 122 (`verify-conv122-001/002`): un solo cierre con la pregunta de nombre, **sin doble intro** (`soy Mundo` ×0–1, antes ×2).
- [x] 8.6 Instrucciones 11/12 del prompt (sin mínimos de años; RFC/expediente "más adelante") + registro usted unificado en corpus. Nota: no observable en vivo porque el RAG deflectó (ver hallazgo preferred_sources, fuera de alcance).
- [x] 8.7 `openspec validate funnel-loop-proof-and-response-data-consistency --strict` → **valid**.

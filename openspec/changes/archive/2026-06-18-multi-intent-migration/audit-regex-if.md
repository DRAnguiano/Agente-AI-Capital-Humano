# Reporte §13 — Matriz de migración de regex/if de negocio

> Modo: **read-only**. No se modificó código. Fecha: 2026-06-04. Corresponde a `tasks.md` §13.
> Asignación de hogares resumida en `design.md` → "Plan de migración de reglas de negocio".

## Leyenda

**Clase actual:** NT (normalización técnica) · ES (extracción simple) · RN (regla de negocio)
· PD (policy declarativa) · PL (planner) · EL (eliminar).
**Destino:** Catálogo/Grafo · Policy · Planner · Extractor técnico (conservar) · Eliminar.
**Prioridad:** P0 (contradice spec / riesgo alto) · P1 (núcleo del rediseño) · P2 (mejora).

---

## A. `app/lead_memory/profile_extractor.py`

| ID | Línea | Regla actual | Clase | Destino | Motivo | Riesgo si se migra mal | Prio | Dependencias | Test/fixture obligatorio |
|----|-------|--------------|-------|---------|--------|------------------------|------|--------------|--------------------------|
| F1 | 11–41 | `KNOWN_CITY_ALIASES` (30 alias ciudad) | RN | Catálogo/Grafo (`GeoArea` + `rh_city_catalog`) | Geo es dato de negocio ya modelado en grafo+catálogo | Ciudad no reconocida → `falta_ciudad` falso, foráneo mal | P1 | Neo4j seed + `rh_city_catalog` (ya existen) | fixture: mty/slp/gómez palacio/nvo laredo → canónico |
| F2 | 55–58 | regex anti "por qué me / qué es X" | RN | Eliminar (lo cubre clasificador) | El clasificador decide si es answer `candidate.city`; heurística frágil | Volver a falsear ciudad desde quejas/preguntas | P1 | clasificador | "¿por qué me dices X?" NO extrae ciudad |
| F3 | 102–118 | tipo licencia B/E por regex | RN | Catálogo/Grafo (`Term` `license`) | Tipos y alias = conceptos de grafo | No reconocer "tipo E"/"lisensia" | P1 | Neo4j `Term` + naming `license.type` (SQL) | "licencia tipo E", "lisensia" → license.type=E |
| F4 | 121–146 | vigencia licencia/apto por keywords | RN | Policy (vigencia) | Regla condicional de vigencia | Marcar vigente algo vencido → `perfil_listo` falso | **P0** | policy + naming | vigente/vencido/trámite por campo |
| F5 | 130–132 | "vence en N años = vigente" | RN | Policy (vigencia) | Regla temporal de vigencia | Clasificar mal vigencia futura | P1 | policy | "vence en 2 años" → vigente |
| F6 | 153 | `"no le veo el problema"` → apto vigente | EL | Eliminar | Frase frágil, no es evidencia de apto vigente | Si se conserva: falso apto vigente | P1 (quick win) | — | ese mensaje NO marca apto vigente |
| F7 | 183–234 | experiencia/unidad por keywords+regex | RN | Catálogo/Grafo (`VehicleType`) + Planner | Vocabulario de unidad = grafo (`normalize_domain_values`) | Clasificar mal la unidad | **P0** | grafo + naming | fixtures full/sencillo/torton — **PARCIALMENTE RESUELTO (Fase 1B, c6e345d):** la unidad ya se resuelve vía `normalize_vehicle`/`domain_catalog`. PENDIENTE: licencia/apto siguen regex (deuda). |
| F8 | 211–212 | `quinta rueda → vehicle_type=quinta_rueda` | RN | Catálogo/Grafo (+ corregir regla) | era ⚠️ contradice spec | Aplicar `objetivo_full_sencillo` indebido | **P0** | — | **RESUELTO en camino vivo (Fase 1B, c6e345d):** `profile_extractor` ya NO escribe `vehicle_type=quinta_rueda`; queda `fifth_wheel="sí"` (compatible). Verificado en producción. |
| F9 | 197–208 | `experience.years = "10 años"` (string) | RN | Planner + naming | Canónico = entero + `unit` | Comparaciones/UI rotas | P1 | naming/SQL | "10 años" → years=10, unit=years |
| F10 | 240–261 | documentos/interés/disponibilidad por keywords | RN | Clasificador (intents) + Catálogo/Grafo | Son intents de lenguaje | "documentos completos" falso | P1 | clasificador + naming `documents.proof` | "si tengo cartas" → documents.proof=cartas |
| F11 | 264–268 | edad por regex | ES | Extractor técnico (conservar) | Extracción simple acotada (18–75) | Choque con "X años" de experiencia | P2 | — | "tengo 27" → age=27, NO years |
| F12 | 281–291 | `missing_profile_fields` | PL | Planner (`funnel_state_planner`) | Cálculo de faltantes con claves canónicas | Faltantes mal → repreguntar / `falta_*` falso | P1 | naming canónico | facts→missing esperado |

## B. `app/orchestrators/knowledge_orchestrator.py`

| ID | Línea | Regla actual | Clase | Destino | Motivo | Riesgo si se migra mal | Prio | Dependencias | Test/fixture obligatorio |
|----|-------|--------------|-------|---------|--------|------------------------|------|--------------|--------------------------|
| F13 | 146–147 | `_clean_reply` (`<think>`) | NT | Extractor técnico (conservar) | Limpieza de salida del LLM, no es negocio | Bajo | P2 | — | respuesta con `<think>` se limpia |
| F14 | 148 | `GENERIC_CLOSING_PATTERNS` | PD | Policy (salida) | Regla de estilo de salida | Bajo | P2 | config | cierre genérico removido |
| F15 | 169–177 | `_is_time_question` | RN | Eliminar (intent `local_time`) | Intent de lenguaje, no regex | Bajo | P2 | clasificador | "qué hora es" → local_time |
| F16 | 186–201 | `_looks_like_farewell` (startswith, len>80) | RN | Eliminar (intent `farewell`) + plantilla a catálogo | Intent + copy | Confundir saludo/despedida | P1 | clasificador + catálogo | "pase buen día" vs "hola buen día" |
| F17 | 204–229 | `_apply_profile_guards` (ack documentos) | RN | Eliminar (intent `document_submission`) + Planner | Intent + acción | Ack mal → avanzar perfil indebido | P1 | clasificador + planner | "ya le mandé mis papeles" |
| F18 | 292–300 | `_looks_like_greeting` (≤5 palabras) | RN | Eliminar (intent `greeting`) + plantilla a catálogo | Intent + copy | Saludo no detectado | P1 | clasificador + catálogo | "hola" → greeting |
| F19 | 303–361 | `_apply_deterministic_overrides` (ruteo) | RN | Eliminar (clasificador + `response_planner`) | Anti-patrón central: ruteo de negocio por keywords | **Alto**: cambiar ruteo global | P0/P1 | clasificador + planner | suite de ruteo greeting/farewell/time |
| F20 | 232–241 | `_CALL_*_HINTS` (acepta llamada/horario) | RN | Clasificador (intent `solicitud_llamada`) + Planner | Intent + acción de seguimiento | No detectar solicitud de llamada | P1 | clasificador | "cuando tenga licencia llámenme" |
| F21 | 364–384 | `_should_use_friendly_llm`/`_is_safe` | PD | Policy (ruteo LLM) — config→Neo4j | Política de cuándo usar LLM amistoso | Usar LLM en tema sensible | P1 | config (hoy) / Neo4j (final) | tema sensible NO friendly |
| F22 | 419–433 | `_is_strong_candidate` (umbral 3+ facts) | PL/RN | Planner + Policy (umbral) | Umbral de negocio con claves canónicas | Tono "fuerte" mal aplicado | P2 | naming canónico | 3 facts clave → strong |
| F23 | 244–264 | `_pending_call_request` (SQL) | ES | Extractor técnico (conservar) | Lectura de estado en Postgres | Bajo | P2 | — | lead con tarea enviada → true |

## C. `app/chatwoot_note_sync.py`

| ID | Línea | Regla actual | Clase | Destino | Motivo | Riesgo si se migra mal | Prio | Dependencias | Test/fixture obligatorio |
|----|-------|--------------|-------|---------|--------|------------------------|------|--------------|--------------------------|
| F24 | 40–41 | `_is_vigente` | NT | Extractor técnico (conservar) | Normalización de valor | Bajo | P2 | — | "sí"/"vigente" → true |
| F25 | 45–46 | `_risk` (bajo/medio/alto) | NT | Extractor técnico (conservar) | Mapeo de display | Bajo | P2 | — | low→Bajo |
| F26 | 49–65 | `_temperatura` (🔥/❄️ por horas) | EL | Eliminar | Deprecado, subjetivo (no estrictamente calculado) | Si se conserva: dato engañoso en nota | P1 (quick win) | — (task 10c.3) | nota SIN sección Temperatura |
| F27 | 68–83 | `_stage` (etapa→label) | PD | Catálogo (`rh_funnel_stage_catalog_v2`) | Catálogo de etapas ya existe en DB | Etapa sin label | P2 | leer catálogo DB | stage→label desde catálogo |
| F28 | 86–105 | `_normalize_labels`/`_facts_map`/`_fact` | NT/ES | Extractor técnico (conservar) | Normalización/lectura | Bajo | P2 | — | facts_map estable |

## D. `app/knowledge/intent_enricher.py`

| ID | Línea | Regla actual | Clase | Destino | Motivo | Riesgo si se migra mal | Prio | Dependencias | Test/fixture obligatorio |
|----|-------|--------------|-------|---------|--------|------------------------|------|--------------|--------------------------|
| F29 | 27–45 | `INTENT_POLICIES` (hardcoded) | PD | Neo4j (temporal en config hoy → final Neo4j) | Políticas por intent deben ser declarativas y consistentes | Políticas inconsistentes entre intents | P1 | Neo4j `Intent/Policy/InternalSource` (task 11.2) | pay→rag+medium; safety+admission→handoff |
| F30 | 28–31 | `pay_question` = `low`/`rag` | RN | Policy (`medium`/`conditional`) | ⚠️ contradice spec; sin fuente → derivar a CH | Inventar cifras de sueldo | **P0** | — (task 5.1) | pay sin fuente RAG → handoff |
| F31 | 54–85 | conflict resolution | PL | Planner (existe en enricher; conservar) | Lógica determinista correcta | Bajo | P2 | — | mismo field 2 valores → mayor confidence |

## E. `app/knowledge/intent_orchestrator.py`

| ID | Línea | Regla actual | Clase | Destino | Motivo | Riesgo si se migra mal | Prio | Dependencias | Test/fixture obligatorio |
|----|-------|--------------|-------|---------|--------|------------------------|------|--------------|--------------------------|
| F32 | 30–61 | `FUNNEL_STEPS` | PL | Planner (existe) + texto a Catálogo | Ya es el planner objetivo; strings → catálogo | Preguntas hardcoded difíciles de editar | P2 | catálogo de preguntas | `next_funnel_question` por estado |
| F33 | 79–96 | `_SIGNAL_REPLIES`/`_NO_FUNNEL_SIGNALS` | PD | Catálogo (plantillas) | Copy hardcoded disperso | Copy inconsistente | P2 | catálogo plantillas | signal→reply desde catálogo |
| F34 | 123–190 | `plan_and_respond` | PL | Planner (existe; extender) | Es el patrón objetivo (extender con memory/funnel state) | Orden de acciones incorrecto | P1 | memory_guard/funnel_state | orden handoff→RAG→señal→funnel |

---

## Quick wins (sin migración, sin SQL/naming/grafo)

- **F6** — eliminar `"no le veo el problema" → apto vigente`.
- **F26** — eliminar `_temperatura` de la nota (task 10c.3).
- **F30** — cambiar el valor de `pay_question` en `INTENT_POLICIES` a `medium`/`requires_human=conditional` (cambio de dato, no de arquitectura).
- **F33** — extraer `_SIGNAL_REPLIES` a un catálogo de plantillas (mecánico).
- **F11/F13/F23/F24/F25/F28/F31** — **conservar** (no requieren trabajo).

## Bloqueados por naming canónico / SQL

Dependen de las migraciones 10b.10–10b.14 (renombres en `rh_lead_facts_v2` + vistas):
- **F3** (`license.category`→`license.type`), **F4** (vigencia + naming), **F9** (`years` entero),
  **F10** (`documents.proof`), **F12** (`missing_fields` canónico), **F22** (claves clave del strong candidate).
Y por **Neo4j**: **F1, F3, F7, F8, F29** (conceptos/aliases/políticas en grafo).

## Orden de implementación recomendado por fases

- **Fase 0 — Quick wins (sin riesgo de naming):** F6, F26, F30, F33. + dejar conservados los NT/ES.
- **Fase 1 — Clasificador (elimina los `if` de ruteo del orquestador):** F2, F15, F16, F17, F18, F19, F20.
  Mueve detección de intents al clasificador; el orquestador deja de decidir negocio con keywords.
- **Fase 2 — Naming canónico + SQL (desbloquea el resto):** migraciones 10b.10–10b.14, luego F3, F4, F9, F10, F12, F22.
- **Fase 3 — Grafo Neo4j:** F1, F7, F8 (vocabulario de unidad + geo) y F29 (`INTENT_POLICIES`→nodos).
- **Fase 4 — Planners + policies:** F12/F22/F31/F32/F34 + crear `label_planner`, `private_note_builder`,
  `response_planner`, `funnel_state_planner`; F4/F5/F14/F21/F27 como policies/catálogo.

> Nota P0: F4, F7, F8, F19, F30 son los de mayor impacto (contradicen la spec o cambian ruteo global).
> Atender F8 y F30 ya en Fase 0/1 cierra las contradicciones código↔spec más visibles.

---

## Contradicciones código ↔ spec (resumen)

> Nota (Fase 1B, c6e345d): el extractor del camino vivo ahora consume
> `normalize_vehicle`/`domain_catalog` para la **unidad** (menos regex de negocio).

1. F8 — `quinta rueda → vehicle_type=quinta_rueda` → **RESUELTO** (Fase 1B, c6e345d): ya no se escribe; verificado en producción.
2. F3/F9/F10/F12/F22 — claves legacy (`license.category`, `documents.labor_letters_status`,
   `experience.fifth_wheel`, `experience.years` string) vs mapa canónico.
3. F30 — `pay_question` = `low`/`rag` vs `medium`/`conditional`.
4. F26 — nota aún renderiza `temperatura`/pago/labels.

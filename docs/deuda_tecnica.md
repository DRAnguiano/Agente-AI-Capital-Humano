# Deuda técnica — registro

> Módulos eliminados: `app/knowledge/disambiguate_numeric_units.py` (2026-06-23) — lógica absorbida
> en `route1_contextual.py` (inline: isdigit + fractional + subannual check) y en `current_turn.py`
> (LLM T=0 para edad/experiencia elíptica). Change: `llm-first-extraction`.

> Registro vivo de deuda detectada en auditoría. **No** es un backlog de features; son
> duplicaciones, drift y código legacy que ya existen en el sistema vivo y que deben
> resolverse con cuidado (algunos requieren un change OpenSpec propio).
>
> Convención de cada entrada: archivo · línea · comportamiento actual · comportamiento
> esperado · OpenSpec relacionado · test rojo sugerido · prioridad.
>
> Origen: auditoría técnica-documental read-only del 2026-06-16. No se modificó lógica
> al registrar esta deuda.

---

## D-1 · Edad límite (≥ 50) hardcodeada en 5 sitios — ALTA

**Comportamiento actual:** la regla "candidato de 50 años o más queda fuera de perfil"
está escrita como literal `>= 50` (o constante local) en cinco lugares independientes:

| Archivo | Línea | Forma |
|---|---|---|
| `app/knowledge/current_turn.py` | 38, 80 | `AGE_LIMIT_EXCLUSIVE = 50` + `is_age_disqualified()` (fuente canónica de facto) |
| `app/chatwoot_note_sync.py` | 112 | `int(...) >= 50` en `_age_disqualified` |
| `app/knowledge/guard_asked_field.py` | 41 | `if int(...) >= 50:` |
| `app/orchestrators/knowledge_orchestrator.py` | 708, 963, 1196 | `if age >= 50:` (×3) |

**Comportamiento esperado:** una sola fuente de verdad del umbral y del predicado.
Reutilizar `current_turn.AGE_LIMIT_EXCLUSIVE` / `current_turn.is_age_disqualified(facts)`
en los otros cuatro sitios. Cambiar el umbral debe ser una edición de un solo punto.

**OpenSpec relacionado:** `funnel-vigencia-edad` (regla de edad temprana / cierre por edad).

**Test rojo sugerido:** parametrizar `AGE_LIMIT_EXCLUSIVE` (o monkeypatch) y verificar que
los cuatro paths (note_sync, guard_asked_field, orchestrator ×3) reflejan el mismo umbral
sin tocar literales sueltos.

**Riesgo si se duplica más:** drift silencioso — cambiar el límite en un sitio y no en
los otros produce un candidato aceptado por un path y rechazado por otro.

---

## D-2 · Lista "Local Laguna" duplicada y divergente — ALTA

**Comportamiento actual:** la definición de qué ciudades son "local Laguna" (vs foráneo)
existe en dos listas en código, con contenidos distintos, además de la columna
`is_local_laguna` en Postgres (`rh_city_catalog`, la fuente que debería mandar):

| Archivo | Línea | Contenido |
|---|---|---|
| `app/knowledge/current_turn.py` | 36 | `["torreon", "torreon coahuila", "gomez palacio", "lerdo", "matamoros"]` (sin acentos; opera sobre texto normalizado; **incluye** "torreon coahuila") |
| `app/chatwoot_note_sync.py` | 294 | `["torreón", "torreon", "gómez palacio", "gomez palacio", "lerdo", "matamoros"]` (con y sin acentos; **no** incluye "torreon coahuila") |
| `app/db.py` (Postgres) | 436, 606 | columna `is_local_laguna` de `rh_city_catalog` (fuente canónica) |

**Comportamiento esperado:** una sola fuente. Idealmente leer `is_local_laguna` de
Postgres; si se necesita un fallback en código, un único helper compartido. El flag
"foráneo" / `validar_traslado` debe calcularse igual en todos los paths.

**OpenSpec relacionado:** `profile-extraction` / `chatwoot-label-taxonomy` (cálculo de
`foraneo` y `local_laguna`).

**Test rojo sugerido:** mismo input de ciudad (p. ej. "gómez palacio") debe producir el
mismo `is_local_laguna` / label `foraneo` en `current_turn` y en `calculate_candidate_labels`.
Hoy diverge por acentos y por "torreon coahuila".

**Riesgo:** un candidato local clasificado como foráneo (o viceversa) según el path,
con la label `foraneo`/`validar_traslado` incorrecta en Chatwoot.

---

## D-3 · Dos calculadoras de labels con criterio distinto de `perfil_listo` — ALTA

**Comportamiento actual:** existen dos funciones que emiten labels de Chatwoot con
criterios **diferentes** para `perfil_listo`:

| Archivo | Función | Línea | Criterio de `perfil_listo` |
|---|---|---|---|
| `app/chatwoot_note_sync.py` | `calculate_candidate_labels` (ruta principal) | 250, 297-299 | `vehicle_confirmed and has_license and has_medical and candidate.vacancy_accepted` |
| `app/app.py` | `_fallback_chatwoot_labels` (fallback) | 556, 569-570 | `result["current_stage"] == "PROFILE_READY"` |

**Comportamiento esperado:** una sola definición de "perfil listo". El fallback debería
delegar en la canónica o documentarse explícitamente como un degradado con criterio
distinto y conocido. Ambas ya comparten `OFFICIAL_LABELS` / `TERMINAL_LABELS`.

**OpenSpec relacionado:** `candidate-label-safety`, `chatwoot-label-taxonomy`.

**Test rojo sugerido:** dado un contexto con `vacancy_accepted=sí` pero
`current_stage != PROFILE_READY` (o al revés), ambas funciones deben coincidir en si
emiten `perfil_listo` — hoy pueden discrepar.

**Riesgo:** `perfil_listo` (label terminal que remueve `bot_activo`) emitida con criterio
inconsistente según se use la ruta principal o el fallback.

---

## D-4 · Copy "Cierre automático: edad fuera de perfil." duplicado — MEDIA

**Comportamiento actual:** el texto de la acción de cierre por edad está como literal en
tres archivos:

| Archivo | Línea |
|---|---|
| `app/chatwoot_note_sync.py` | 362 |
| `app/tasks_chatwoot.py` | 453 |
| `app/orchestrators/knowledge_orchestrator.py` | 737 |

**Comportamiento esperado:** una constante compartida (junto a `AGE_DISQUALIFICATION_REPLY`
en `current_turn.py`, que ya centraliza copy de edad).

**OpenSpec relacionado:** ninguno estricto; relacionado con `funnel-vigencia-edad`.

**Test rojo sugerido:** no crítico; basta una constante importada y un assert de igualdad.

**Riesgo:** bajo (solo display de next_action), pero invita a drift de copy.

---

## D-5 · Catálogo de ciudades inline vs `rh_city_catalog` (Postgres) — MEDIA

**Comportamiento actual:** `app/lead_memory/profile_extractor.py:108-117` mantiene un
catálogo de ciudades inline para anclar `candidate.city` por regex, mientras
`rh_city_catalog` (Postgres, `app/db.py:578`) es la fuente estructurada de geo.

**Comportamiento esperado:** documentar claramente cuál manda (el regex inline resuelve
ambigüedad "ciudad de origen vs destino" en texto libre; la tabla resuelve normalización).
Evaluar si el catálogo inline debe alimentarse desde la tabla.

**OpenSpec relacionado:** `profile-extraction`.

**Test rojo sugerido:** una ciudad presente en `rh_city_catalog` pero ausente del inline
(o con grafía distinta) debe normalizarse de forma consistente.

**Riesgo:** medio — dos fuentes de geo que pueden divergir al crecer el catálogo.

---

## Legacy / ruido para modelos futuros (no es duplicación, pero confunde)

- `scripts/apply_current_turn_guard_patch.py` y `scripts/connect_active_knowledge_architecture.py`
  importan `app/orchestrator.py` / `app/orchestrator_guard.py`, **módulos que ya no existen**.
  Son patches de una migración ya aplicada. Candidatos a borrar (requiere decisión explícita).
- `app/app.py.save`: backup de mayo con prompts viejos que contradicen el constraint
  "el LLM no pregunta datos de perfil". Archivo basura versionado. Candidato a borrar.
- `openspec/changes/candidate-label-safety` está marcado ✓ Complete pero **no archivado**
  (`changes/archive/` vacío). Conviene archivar para limpiar el set de changes activos.

> Estas tres entradas NO se tocan en la fase de comentarios; requieren aprobación explícita
> por ser borrado de archivos / decisiones de housekeeping.

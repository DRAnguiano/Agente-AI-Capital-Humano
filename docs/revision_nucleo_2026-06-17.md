# Revisión del núcleo — triage (2026-06-17)

Reporte de incongruencias recibido (18 hallazgos). Triage tras validar por lectura de
código. **Clave:** ~9 de los 18 (incl. 3 de los 4 "críticos") NO son bugs independientes;
son síntomas de **un solo origen**: la migración multi-intent está a medias — el pipeline
nuevo corre en **shadow** (`run_shadow`, no muta estado) junto al camino **vivo** legacy.
Completar el cutover + consolidar nombres (ya en `multi-intent` 10b.10/10b.11) los colapsa.

## A) Bugs VIVOS reales — arreglar independientemente del cutover

| # | Hallazgo | Validación | Dónde |
|---|----------|------------|-------|
| 1 | SYSTEM_PROMPT usa "Capital Humano" como tercero en sus propios ejemplos, contradiciendo su regla de "voz de equipo" | **Real.** Alinea con memoria `feedback_persona_capital_humano` | `persona_config.py` |
| 6 | Ejemplos del prompt con cifras fijas ($5,000–$10,000, $900, $15,000…) vs "no inventes cifras" | **Real** (riesgo de que el LLM las parrotee) | `persona_config.py` |
| 8 | `HUMAN_REVIEW_REQUIRED` es irreversible (sin camino de regreso) | **Confirmado** en `db.py:337-350` (stage/risk/requires_human bloqueados). Decisión: ¿intencional o necesita release? | `db.py update_stage` |
| 18 | `_clean_reply` duplicado y divergente en `app.py` (loop `while changed`) vs `knowledge_orchestrator.py` (`_strip_wrapping_quotes`) | **Confirmado.** NOTA: hoy AÑADÍ `_strip_wrapping_quotes` al del orquestador → la divergencia creció. Unificar en un helper común | `app.py:89`, `knowledge_orchestrator.py:150` |
| 7 | Guards deterministas se sobrescriben en orden; asimetría `_looks_like_greeting` (corta si >5 palabras) vs `_looks_like_farewell` (sin límite) | **Parcial.** El orden B1/reingreso→handoff es correcto (reingreso debe ir a humano); la asimetría de greeting/farewell sí es real. Mi `_apply_business_rule_overrides` se suma a la cadena | `knowledge_orchestrator.py` |
| 14 | `_TZ_CENTRO=None` si `zoneinfo` falla → hora del servidor (no CDMX) para horario 8–17:30 | **Real** (latente). Cruza con `live-reply` B7.2 `is_business_hours()` | `current_turn.py` |

## B) LATENTE — deuda del cutover multi-intent (NO bug vivo hoy)

Estos NO muerden producción porque el pipeline nuevo es shadow (no muta estado). Se
resuelven al hacer cutover + consolidación de nombres.

| # | Hallazgo | Estado real |
|---|----------|-------------|
| 2 | Dos funnels (legacy current_turn vs FUNNEL_STEPS) | Legacy es el VIVO; el nuevo es shadow. No corren ambos sobre estado real. Cutover los unifica |
| 3 | Tres criterios de `perfil_listo` | Deuda conocida (`chatwoot-ai-note-contract`, `multi-intent` 10a/10b). `app.py` ya documenta la "ruta DEGRADADA" |
| 4 | `license.type` (funnel nuevo/memory_guard) vs `license.category` (extractor) — "pregunta para siempre" | **Confirmado: `license.type` NUNCA se escribe en el camino vivo.** Pero el funnel nuevo NO es vivo → no muerde hoy. Es exactamente la migración `multi-intent` 10b.10 (renombrar category→type) |
| 10 | Intents legacy (`payment_compensation`…) no mapean a los del clasificador nuevo (`pay_question`…) | Latente; se mapea en el cutover |
| 13 | `INTENT_CONFIDENCE_THRESHOLD=0.85` excluye answers válidos (0.84/0.75) | Latente (enricher del pipeline nuevo) |
| 15 | `fact_corrections` espera `is_correction`/`certainty` que el clasificador no emite | Latente; pipeline shadow. Tocado en `multi-intent` 7.x |
| 11,16 | naming `license.category`/`status`; redundancia en `_claimed_answer` | Cosmético/latente |

## C) Sobre-dimensionados / por diseño

| # | Hallazgo | Aclaración |
|---|----------|------------|
| 5 | "Default de modelo distinto (8B vs 70B)" | **Por diseño, no race.** `settings.py` 8b = clasificación; `indexer.py` 70b = generación. Son DOS perillas para DOS tareas, usadas en sitios distintos. Confuso por compartir el nombre env `GROQ_MODEL`, pero no es el mismo default compitiendo |
| 9 | "Dos endpoints compiten" | `/orchestrate/message` = vivo; `/classify` = entrada shadow/test. No compiten en producción salvo mal uso. Se resuelve al cutover |
| 17 | Defaults RAG (`RAG_TOP_K` vs `TOP_K`) | Real pero menor; consolidar config |

## Plan propuesto (mañana)

1. **Crear change OpenSpec** `core-consistency-fixes` para el grupo **A** (bugs vivos): #1, #6
   (persona prompt), #8 (release de HUMAN_REVIEW — decidir política), #18 (unificar
   `_clean_reply`), #7 (asimetría greeting/farewell), #14 (tz segura). Contrato + tests RED.
2. **Grupo B** → NO change nuevo: anotarlos como aceptación del **cutover** en
   `multi-intent-migration` (ya cubiertos por 10a/10b/10b.10/10b.11). Evita reinventar.
3. **Grupo C** → cerrar como "por diseño" (#5, #9) o deuda menor (#17) con nota.
4. Retomar el **baseline QA** (índice 0, una sola corrida ~125) con TPD limpio.

> Pendiente de decisión del usuario: #8 (¿HUMAN_REVIEW debe poder liberarse? ¿por quién?)
> y si el grupo A entra antes o después de seguir con la espina del cutover.

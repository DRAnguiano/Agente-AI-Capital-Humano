## Context

Flujo real de un turno (productivo) hoy, **verificado contra el código**:

```
webhook → tasks_chatwoot.process_debounced_message
  [396] _pre_extraction (extracción unificada) + _pre_validated = validate_extraction(...)
  [428] result = run_hr_graph_message → knowledge_orchestrator.handle_message
          resolve_message + _apply_*_overrides ........... DECISIÓN (intent/route/flags)
          [1905/1907] reply = _controlled_reply_from_contract(contract)
          [1988] _store_lead_memory_updates(pre_validated_facts=_pre_validated)  ← ESCRITOR ÚNICO (persiste)
  [492] if _guard_should_fire:  (señal de perfil, sin pregunta embebida)
          [503] guarded_reply = build_current_turn_ack(combined, merged_facts, last_bot, pre_current)  ← ACK DEL FUNNEL
          [510-544] upsert_lead_fact(...)  ← 2.º escritor (drift vs "Escritor único"; pre-existente)
          [572] result["reply"] = guarded_reply  ← SOBRESCRIBE la respuesta del orquestador
  → reply de vuelta al worker → Chatwoot
```

Dos hechos que la verificación corrigió respecto del borrador inicial:
1. **El ack del funnel que el candidato ve NO sale de `handle_message`.** El
   orquestador arma `_controlled_reply_from_contract`, pero el **worker guard**
   (`_guard_should_fire`, tasks_chatwoot.py:492) lo **sobrescribe** con
   `build_current_turn_ack` (503) justo en los turnos de "confirmo dato + pido el
   siguiente" — el momento frío que motiva este cambio. `build_current_turn_ack`
   solo se llama desde el worker (único call-site productivo).
2. **La persistencia ya precede a la composición.** El escritor único
   `_store_lead_memory_updates` (1988) corre dentro de `handle_message` (428), antes
   del guard (492); por tanto `persisted` es veraz cuando el guard compone el ack:
   **no se requiere reordenar nada** para cumplir "persistir antes de confirmar".

El **ack del funnel** lo produce `build_current_turn_ack` (current_turn.py:605-654),
100% determinista: arma un `prefix` de frases canónicas y lo une con
`_join_ack_and_question(prefix, next_question_from_missing_facts(facts))`. Esa unión
es exactamente la costura de la Opción B: **el `prefix` es el bloque conversacional;
la pregunta es canónica.** Por eso el composer se inserta **envolviendo
`build_current_turn_ack` en la rama del guard**, no en `handle_message`.

> Restricción heredada (message-orchestration): existen "Escritor único de facts por
> turno" (`_store_lead_memory_updates`) y "Confirmación sin duplicaciones" (prefijo
> único de ack). El composer NO debe añadir un escritor de facts ni un segundo
> prefijo. El `upsert_lead_fact` del guard (510-544) ya es un 2.º escritor
> pre-existente en drift con ese requirement; este cambio no lo agrava ni depende de
> él (decisión a validar en /opsx:verify).

Piezas reutilizables ya existentes:
- `_answer_friendly_message` (knowledge_orchestrator.py:872): LLM friendly, 2
  oraciones, nunca pregunta, fallback `_FRIENDLY_NEUTRAL_REPLY`.
- `_friendly_introduces_number` (867): descarta la salida si el LLM mete una cifra
  que el candidato no dijo (anti-fabricación).
- `clean_reply`/`_sanitize` (reply_cleaner.py:67): quita `<think>`, cierres
  genéricos, comillas envolventes.
- `_enforce_vigencia_lexicon` (753): guarda de léxico sobre la respuesta final.
- `_JOKE_BANNED` (de `_generate_joke_reply`, 228) reutilizable como **validador de
  seguridad** del chiste; el **contenido del chiste pasa a generarse por LLM** (no
  banco fijo). `_time_reply` (271) se mantiene determinista con reloj real
  `datetime.now(ZoneInfo("America/Mexico_City"))`.
- `call_llm` (app/indexer.py): cliente Groq (`llama-3.3-70b-versatile`,
  `GROQ_MAX_TOKENS`), con `groq-key-fallback` ya como capability.
- Flags: `KNOWLEDGE_FRIENDLY_LLM_ENABLED`, `KNOWLEDGE_FRIENDLY_LLM_GENERATION_ENABLED`.

## Goals / Non-Goals

**Goals:**
- Calidez/contexto en el ack del funnel sin que el LLM toque ninguna decisión.
- Un contrato interno explícito (`ResponseComposition`) entre la decisión y el
  envío.
- Opción B: el modelo solo redacta bloques (reconocimiento/lateral/transición); la
  pregunta canónica y la política autorizada las ensambla Python.
- Fallback determinista idéntico al comportamiento actual ante cualquier fallo.
- Resistencia a prompt injection; sin confirmar datos no persistidos.
- Migración incremental con shadow/canary y métricas.

**Non-Goals:**
- NO cambiar extracción, validación, persistencia, labels, vacantes, elegibilidad,
  handoff ni Neo4j.
- NO que el LLM genere/alter la siguiente pregunta crítica.
- NO enviar historial completo ni memoria libre al modelo (solo el contrato
  acotado).
- NO meter política de tono en seeds de vocabulario/RAG.
- NO rediseñar `handle_message` (la deuda de las ~240 líneas se queda como está;
  esto se inserta en la costura existente).
- Fase 1 decora SOLO el ack del worker guard; NO se toca
  `_controlled_reply_from_contract` del orquestador.
- NO corregir el 2.º escritor del guard (`upsert_lead_fact`, 510-544) en este cambio:
  es drift pre-existente vs "Escritor único"; se reconcilia en un cambio aparte.

## Decisions

**D1 — Opción B (bloques) sobre Opción A (mensaje completo). [decisión a validar]**
El LLM devuelve un JSON estricto con campos opcionales:
`{ "acknowledgment": str|"", "lateral": str|"", "transition": str|"" }`.
Python ensambla: `acknowledgment [+ lateral] + (pending_question | authorized_policy)`.
Racional: preserva la pregunta canónica palabra por palabra, minimiza
alucinaciones y hace las pruebas deterministas (se valida cada bloque por
separado). Opción A se descarta porque permitiría al modelo reescribir la pregunta
o afirmar persistencia.

**D2 — Contrato `ResponseComposition` (frozen dataclass).** Ensamblado en la rama
del current-turn guard del worker (tasks_chatwoot.py ~492-502, justo antes de
`build_current_turn_ack` en 503), a partir de fuentes que el worker ya tiene
(`combined_content`, `merged_facts`, `_current_turn_facts`, `_pre_validated`,
`last_bot_message`):

| Campo | Tipo | Fuente real |
|---|---|---|
| `pending_question` | `str` | `next_question_from_missing_facts(facts)` (canónica, Python) |
| `extraction_state` | enum | `valid`/`ambiguous`/`incomplete`/`rejected`/`irrelevant` derivado de `_pre_validated` + `turn_signals` + delta de facts del turno |
| `persisted` | `bool` | si el fact del turno fue escrito por el escritor único `_store_lead_memory_updates` (1988), que corre ANTES del guard; el composer no persiste |
| `authorized_policy` | `str\|None` | `contract.reply_template.text` o respuesta RAG autorizada; si no, None |
| `transition` | enum | `continue`/`clarify`/`pause`/`handoff`/`lateral_then_continue` desde flags del contrato (`requires_human`, `requires_clarification`, intent) |
| `candidate_first_name` | `str\|None` | `first_name(candidate.name)` SOLO si está persistido y es confiable |
| `tone_signal` | enum | `humor`/`frustration`/`evasion`/`doubt`/`casual`/`neutral` desde señales ya extraídas (no nueva llamada LLM autoritativa) |
| `lateral_reply` | enum`\|None` | `joke` (→`_generate_joke_reply`) / `time` (→`_time_reply`); ambos ya guardados |
| `constraints` | flags | `may_confirm_persistence` (=persisted), `must_keep_pending_question`, `allow_tone_ack`, `allow_lateral` |

El contrato es la ÚNICA entrada del prompt (no memoria libre). El nombre se incluye
solo si `persisted` y existe; nunca derivado de un nombre dicho pero no validado.

**D3 — Capa lingüística `compose_reply(rc) -> str` con validación en cascada.**
1. Si `KNOWLEDGE_RESPONSE_COMPOSER_ENABLED` OFF o `lateral_reply`/política manda →
   ruta determinista directa (sin LLM).
2. Construir prompt solo con `rc` (bloques permitidos según `constraints`).
3. `call_llm` con timeout; parsear JSON.
4. Validar cada bloque: longitud máx., `acknowledgment` sin `?` (la pregunta es de
   Python), sin cifras introducidas (`_friendly_introduces_number`), sin frases de
   persistencia prohibidas cuando `not persisted` (regex sobre "registrad",
   "aprobad", "cumple", "avanzó", "listo", "quedó"), `clean_reply`,
   `_enforce_vigencia_lexicon`.
5. Ensamblar con la pregunta canónica/política (Python).
6. CUALQUIER fallo (excepción, timeout, JSON inválido, guarda violada, vacío) →
   `build_current_turn_ack(...)` (comportamiento actual). El composer es
   estrictamente aditivo: peor caso = hoy.

**D4 — Anti prompt-injection.** El mensaje del candidato NO entra crudo al prompt
del composer salvo, a lo sumo, como `tone_signal` ya derivada y como cita acotada
para el reconocimiento; la instrucción del sistema indica tratar todo texto del
candidato como dato y nunca como orden. La validación post-hoc descarta bloques que
mencionen instrucciones, sistema, políticas o that re-emitan la pregunta. Como la
pregunta canónica y las políticas se ensamblan en Python, ninguna inyección altera
el flujo, los labels ni la persistencia.

**D5 — Solicitudes laterales sin perder la pregunta (chiste generado, hora del reloj).**
El **chiste se genera por LLM** (variado, validado por una lista de seguridad de
temas; nunca de un banco fijo) — esto migra `_generate_joke_reply` de banco estático
a generación validada, reusando solo `_JOKE_BANNED` como filtro. La **hora** sí es
determinista: `_time_reply` con el reloj inyectado, nunca el modelo. Tras el lateral
se añade SIEMPRE el funnel nudge con la pregunta canónica. Si el LLM falla al generar
el chiste, el fallback **omite el chiste con cortesía** y retoma la pregunta (no cae
en un chiste enlatado). **Hallazgo de verificación:** una solicitud lateral **pura**
(sin señal de perfil) NO dispara el worker guard (`_guard_should_fire` exige
`_has_profile_signal` y `not is_question`); se resuelve en el **camino del
orquestador** (`local_time`/friendly + funnel nudge). Por eso la generación del
chiste por LLM aplica a ese camino (no al composer del guard); `lateral_reply` del
contrato queda como hook para turnos mixtos. Laterales no soportadas → se ignoran y
se responde el funnel.

**D6 — Uso moderado del nombre.** `first_name(facts)` = primer token capitalizado de
`candidate.name`; se usa como máximo una vez por mensaje, solo cuando `persisted` y
confiable; sin nombre → se omite el vocativo (sin placeholder). Frecuencia limitada
por código (no por el modelo) para evitar sobreuso.

**D7 — Orden canónico del turno (invariante, verificado).** El orden real hoy es
`extracción [396] → validación [396] → decisión + persistencia única
_store_lead_memory_updates [428→1988] → composición del ack en el guard [503] →
envío`. La persistencia del escritor único YA precede a la composición del guard,
así que "persistir antes de confirmar" se cumple **sin reordenar nada**. El composer
SOLO corre en el paso de composición y SOLO lee el resultado de los pasos previos;
nunca reordena, reejecuta, ni añade un segundo escritor. La idempotencia de webhook
(debounce + dedupe en el worker) no se toca: el composer no tiene efectos
secundarios (no escribe BD/labels), así que un reintento recompone texto sin
duplicar efectos.

**D8 — Migración incremental.**
- Fase 0 (shadow): el composer corre en paralelo, su salida se loguea y compara con
  el ack determinista; NO se envía. Métricas base.
- Fase 1 (canary): activación por flag para un subconjunto (p. ej. por hash de
  `lead_key`); se vigila tasa de fallback y QA de naturalidad.
- Fase 2 (on): default ON; el determinista queda como fallback permanente.

## Risks / Trade-offs

- **Latencia añadida:** una llamada `call_llm` extra en el path del funnel.
  Mitigación: timeout corto, fallback inmediato, canary; medir `compose_added_ms`.
- **Alucinación de tono:** el modelo podría afirmar algo no autorizado. Mitigación:
  Opción B + validación en cascada + `_friendly_introduces_number` + regex de
  persistencia; peor caso cae al determinista.
- **Doble mantenimiento ack determinista/composer:** el determinista sigue siendo
  fuente de verdad de la pregunta; el composer solo decora el prefix. `guard_asked_field.py`
  ya exige mantener el espejo de la cascada de preguntas — el composer no la toca.
- **Sobreuso del nombre / tono excesivo:** percibido como artificial. Mitigación:
  D6 (máx. 1 vocativo) y reglas de prompt heredadas de `_answer_friendly_message`
  (sin "¡Genial!", máx. 2 oraciones).
- **Decisión D1 (A vs B) a validar en `/opsx:verify`** junto con: umbral de timeout,
  formato JSON vs. delimitadores, y si `tone_signal` se deriva determinista o con
  una mini-clasificación no autoritativa.

## Decisiones que deben validarse en `/opsx:verify`
1. Opción B (bloques) confirmada vs. A (mensaje completo).
2. Esquema exacto de salida del LLM (JSON `{acknowledgment,lateral,transition}`).
3. Origen de `tone_signal`: determinista (de `turn_signals`) vs. mini-LLM no
   autoritativo.
4. Umbral de timeout y presupuesto de latencia añadida aceptable.
5. Lista de frases prohibidas de "persistencia" y su cobertura.
6. Estrategia de canary (criterio de subconjunto) y umbral de tasa de fallback
   para promover de fase.
7. **Punto de inyección — RESUELTO (verify):** envolver `build_current_turn_ack` en
   la rama del worker guard (`tasks_chatwoot.py` ~492-572), NO en `handle_message`.
   **Alcance fase 1: SOLO el ack del guard.** NO se decora
   `_controlled_reply_from_contract` del orquestador (queda igual).
8. **Drift "Escritor único" pre-existente — RESUELTO (verify):** el guard hace un 2.º
   `upsert_lead_fact` (510-544) que contradice el requirement `message-orchestration`
   "Escritor único de facts por turno". **Decisión: dejarlo documentado, fuera de
   alcance** (cambio aparte). Este cambio NO lo agrava ni depende de él para derivar
   `persisted` (que viene de `_store_lead_memory_updates`).

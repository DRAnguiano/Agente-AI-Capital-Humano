## Why

El sistema extrae, valida y persiste datos correctamente, pero la respuesta que
recibe el candidato durante el **funnel** se construye de forma puramente
determinista en `build_current_turn_ack` (current_turn.py:605-654): un `prefix` de
frases canónicas ("Edad anotada, continuamos con el proceso.") unido por
`_join_ack_and_question` (587-602) a la pregunta canónica
`next_question_from_missing_facts` (486-527). Eso se siente frío y mecánico cuando
el candidato responde con humor, una cifra aproximada, una evasiva o frustración.

Ya existe una capa lingüística friendly (`_answer_friendly_message`,
knowledge_orchestrator.py:872-951) con guardas anti-fabricación
(`_friendly_introduces_number`, 867), fallback determinista
(`_FRIENDLY_NEUTRAL_REPLY`/`_FRIENDLY_NO_ANSWER_REPLY`), `_clean_reply`/`clean_reply`
(reply_cleaner.py:67) y flags de entorno — **pero solo se activa en la ruta
`friendly_smalltalk`** (`_should_use_friendly_llm`, 770-783), nunca sobre el ack del
funnel. El resultado: el momento más frecuente de cara al candidato (confirmar un
dato y pedir el siguiente) no tiene tono.

No existe un **contrato interno explícito** que reúna, después de la decisión
operacional y antes del envío, lo que la capa lingüística necesita: pregunta
pendiente canónica, estado de la extracción, si persistió, política autorizada,
tipo de transición, nombre confiable, señal contextual y restricciones. Hoy esas
señales están dispersas en `contract`, `_pre_extraction`, `_pre_validated`,
`turn_signals` y los facts.

## What Changes

- **Contrato interno de composición (`ResponseComposition`).** Una estructura
  inmutable, ensamblada en la rama del current-turn guard del worker
  (`tasks_chatwoot.py` ~492-572) —donde `build_current_turn_ack` produce el ack del
  funnel que **sobrescribe** la respuesta del orquestador— DESPUÉS de que el
  escritor único `_store_lead_memory_updates` persistió los `pre_validated_facts`
  del turno y ANTES de redactar el ack, que expone a la capa lingüística:
  `pending_question` (canónica, de
  `next_question_from_missing_facts`), `extraction_state`
  (valid/ambiguous/incomplete/rejected/irrelevant), `persisted` (bool),
  `authorized_policy` (texto de `reply_template`/RAG autorizado, o None),
  `transition` (continue/clarify/pause/handoff/lateral_then_continue),
  `candidate_first_name` (solo si confiable y persistido), `tone_signal`
  (humor/frustration/evasion/doubt/casual/neutral, derivada de señales ya
  extraídas), `lateral_reply` (joke/time autorizado) y las restricciones de
  recomposición.
- **Capa lingüística controlada — Opción B (bloques, no mensaje completo).** El LLM
  SHALL generar ÚNICAMENTE bloques conversacionales acotados (reconocimiento de
  tono, respuesta lateral breve, frase de transición). Python ensambla de forma
  determinista la **pregunta pendiente canónica** o el **mensaje de política
  autorizado**; el modelo NUNCA los redacta ni altera. Se reutiliza la
  infraestructura existente (`build_current_turn_ack` como fallback, `call_llm`,
  `_friendly_introduces_number`, `clean_reply`, `_enforce_vigencia_lexicon`).
- **Validación estricta + fallback determinista + anti-injection.** Salida del LLM
  parseada y validada (longitud, sin `?` en el ack, sin cifras introducidas, sin
  afirmaciones de persistencia no ocurrida, sin políticas inventadas). Cualquier
  fallo (timeout, JSON inválido, violación de guarda, generación deshabilitada)
  cae al ack determinista actual. El mensaje del candidato se trata como dato no
  confiable (separación de rol, instrucción de ignorar órdenes embebidas); como la
  pregunta canónica nunca proviene del modelo, la inyección no puede desviar el
  funnel.

## Capabilities

### New Capabilities
- `controlled-response-composition`: capa lingüística controlada que, a partir de
  un contrato interno de composición, genera solo bloques conversacionales
  acotados (reconocimiento, lateral, transición) mientras Python ensambla la
  pregunta canónica/política autorizada; con validación estricta de la salida,
  resistencia a prompt injection y fallback determinista al ack actual.

### Modified Capabilities
- `message-orchestration`: la rama del current-turn guard SHALL ensamblar el
  contrato `ResponseComposition` tras la persistencia del escritor único y delegar
  el `prefix` del ack (reconocimiento/transición) a la capa controlada, preservando
  intacta la pregunta pendiente canónica y sin introducir un segundo escritor de
  facts ni un segundo prefijo de ack.

## Impact

- Código nuevo: módulo de composición (p. ej. `app/knowledge/response_composer.py`)
  con el dataclass `ResponseComposition`, el ensamblador del contrato y la capa
  lingüística (LLM de bloques + validación + fallback).
- Código modificado: `app/tasks_chatwoot.py` (rama del current-turn guard ~492-572:
  ensamblar el contrato y envolver `build_current_turn_ack` con `compose_reply`,
  leyendo `persisted` del escritor único previo, sin añadir un segundo escritor) y
  `app/knowledge/current_turn.py` (`build_current_turn_ack` como productor del
  `pending_question` y como fallback). Sin tocar extracción, validación, el escritor
  único de facts, labels ni Neo4j.
- Flags de entorno nuevas (alineadas a las existentes
  `KNOWLEDGE_FRIENDLY_LLM_*`): activación por defecto OFF para migración
  incremental (shadow → canary → on).
- Observabilidad: métricas de tasa de fallback, salidas inválidas, preservación de
  la pregunta canónica, latencia añadida e intentos de confirmar datos no
  persistidos.
- Sin cambios de esquema ni de datos (`data/`); el corpus y los seeds no albergan
  política de tono (restricción no negociable).

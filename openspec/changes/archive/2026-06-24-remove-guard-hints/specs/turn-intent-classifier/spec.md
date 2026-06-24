# Spec: turn-intent-classifier

Clasificador unificado de señales de intención por turno. Una sola llamada LLM T=0 (llama-3.1-8b-instant) al inicio de cada turno que devuelve todas las señales semánticas necesarias para el pipeline de extracción.

## ADDED Requirements

### Requirement: Unified turn intent classification

El sistema SHALL introducir `app/knowledge/turn_intent_classifier.py` que expone `classify_turn_intent(message: str) -> TurnIntentSignals`.
El clasificador MUST realizar una sola llamada LLM T=0 por invocación y retornar todas las señales en un único JSON.
El prompt MUST incluir ejemplos del gremio de operadores para cada señal.
En caso de fallo del LLM, la función SHALL retornar `TurnIntentSignals()` con todos los campos en valor neutro (False / None) — comportamiento degradado sin crash.

#### Scenario: Clasificación completa de turno con múltiples señales

**Given** el candidato envía "ya le había dicho que manejo full y cuánto pagan por ruta"
**When** se llama `classify_turn_intent`
**Then** `is_ya_reclamo` = True, `has_embedded_question` = True, `experience_context` = True

#### Scenario: Fail-safe ante error de Groq

**Given** Groq retorna un error de timeout
**When** se llama `classify_turn_intent`
**Then** retorna `TurnIntentSignals()` con todos los campos False/None sin lanzar excepción

### Requirement: TurnIntentSignals dataclass

El módulo SHALL exponer `TurnIntentSignals` con los campos:
- `is_ya_reclamo: bool` — el "ya" indica reclamo (no confirmación)
- `is_memory_claim: bool` — el candidato afirma haber dado el dato antes
- `has_embedded_question: bool` — contiene pregunta de negocio sin "?"
- `call_requested: bool` — pide que le llamen
- `renewal_proof: str | None` — "si" | "no" | null
- `no_road_experience: bool` — declara no tener experiencia en carretera
- `has_expiry_context: bool` — menciona vencimiento/plazo
- `experience_context: bool` — habla de SU experiencia conduciendo

#### Scenario: Señales independientes y combinables

**Given** el candidato envía "ya tengo la licencia vigente, pero cuánto pagan"
**When** se clasifica el turno
**Then** `is_ya_reclamo` = False (ya tengo = confirmación), `has_embedded_question` = True

#### Scenario: Vocabulario ampliado del gremio — call intent sin "llamada"

**Given** el candidato envía "prefiero ponerse en contacto por teléfono"
**When** se clasifica el turno
**Then** `call_requested` = True (sin necesidad de "llam" en el texto)

#### Scenario: No-road-experience con jerga no hardcodeada

**Given** el candidato envía "soy principiante en esto del tracto"
**When** se clasifica el turno
**Then** `no_road_experience` = True

#### Scenario: Expiry context con variante no listada

**Given** el candidato envía "se me acaba la vigencia en 3 meses"
**When** se clasifica el turno
**Then** `has_expiry_context` = True

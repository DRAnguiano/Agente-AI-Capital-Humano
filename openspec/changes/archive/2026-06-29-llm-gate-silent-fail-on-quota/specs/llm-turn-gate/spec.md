# llm-turn-gate Specification

## Purpose

Garantizar que ningún turno del worker Celery envíe una respuesta al candidato ni persista
facts cuando el extractor LLM no está disponible (quota agotada en primaria y backup, o
error irrecuperable). El gate es la primera comprobación del turno: si falla, el turno
termina silenciosamente en los logs, sin efecto externo observable para el candidato.

## Requirements

### Requirement: Abort silencioso ante LLM no disponible

Cuando `extract_turn` no puede completar la extracción por `GroqRateLimitError`
irrecuperable (ambas claves agotadas), el worker SHALL retornar
`status: 'skipped_llm_unavailable'` sin enviar nada a Chatwoot, sin persistir facts,
y sin llamar a `call_groq_llm`. El candidato no recibe respuesta en ese turno.

El fallo SHALL registrarse en los logs con nivel WARNING bajo el prefijo `[LLM_GATE]`,
incluyendo el `lead_key`, el `conversation_id` y el mensaje de error de la excepción.

El worker SHALL NOT relanzar la excepción como error Celery no controlado (lo que
provocaría retries automáticos): retorna un dict de resultado con `processed: False`.

#### Scenario: Extractor falla por quota agotada en ambas claves
- **WHEN** `call_groq_json` lanza `GroqRateLimitError` y el fallback al backup también
  lanza `GroqRateLimitError`
- **THEN** `extract_turn` propaga `LLMUnavailableError`
- **AND** el worker captura `LLMUnavailableError` antes de cualquier llamada a Chatwoot
  o persistencia en Postgres
- **AND** retorna `{"status": "skipped_llm_unavailable", "processed": False, "sent_to_chatwoot": False}`
- **AND** se registra un log WARNING con prefijo `[LLM_GATE]`

#### Scenario: El candidato no recibe respuesta cuando el gate dispara
- **WHEN** el gate dispara `LLMUnavailableError`
- **THEN** no se llama a la API de Chatwoot para enviar mensaje público ni nota privada
- **AND** el candidato puede reenviar el mismo mensaje cuando la quota se restaure

#### Scenario: Errores de parsing no disparan el gate
- **WHEN** `call_groq_json` devuelve JSON malformado o datos inesperados (no un error de
  cuota), y la extracción falla en el parseo
- **THEN** `extract_turn` retorna `TurnExtraction()` vacía como antes (sin gate)
- **AND** el turno continúa normalmente (con extracción vacía)

### Requirement: `LLMUnavailableError` como señal de abort

El sistema SHALL definir `LLMUnavailableError` (subclase de `RuntimeError`) en
`app/knowledge/llm_errors.py` como la señal canónica de LLM no disponible por quota.
`extract_turn` SHALL re-lanzar `GroqRateLimitError` como `LLMUnavailableError`
exclusivamente cuando el error proviene de cuota agotada (no de timeout ni parse error).

#### Scenario: Re-raise tipado desde extractor
- **WHEN** `_groq_with_fallback` lanza `GroqRateLimitError` (ambas claves)
- **THEN** `extract_turn` captura ese error específico y lanza `LLMUnavailableError`
  con el mensaje original como causa (`raise LLMUnavailableError(...) from exc`)

#### Scenario: Otros errores no se convierten en LLMUnavailableError
- **WHEN** `call_groq_json` falla por timeout (`httpx.TimeoutException`) u otro error
  no relacionado con quota
- **THEN** `extract_turn` absorbe el error y retorna `TurnExtraction()` vacía (camino actual)
- **AND** NO se lanza `LLMUnavailableError`

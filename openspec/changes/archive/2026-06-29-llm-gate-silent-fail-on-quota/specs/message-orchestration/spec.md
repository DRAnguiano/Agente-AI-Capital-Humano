## MODIFIED Requirements

### Requirement: Disponibilidad del LLM durante el procesamiento de un turno

El sistema SHALL procesar cada turno de candidato sin error de LLM siempre que al menos una
clave Groq válida esté disponible (`GROQ_API_KEY` o `GROQ_API_KEY_BACKUP`). Si la clave
primaria tiene la cuota agotada, el sistema SHALL recuperarse automáticamente usando la clave
de respaldo, sin retornar un error al candidato ni dejar el turno sin procesar.

Cuando **ambas** claves tienen la cuota agotada (error `GroqRateLimitError` irrecuperable
en la extracción del turno), el sistema SHALL abortar el turno completamente: SHALL NOT
enviar ninguna respuesta al candidato, SHALL NOT persistir facts parciales, y SHALL NOT
llamar a `call_groq_llm` para generar respuesta. El turno SHALL terminar silenciosamente
con `status: 'skipped_llm_unavailable'`, registrando el fallo en los logs bajo el prefijo
`[LLM_GATE]`. Este comportamiento garantiza que el candidato nunca reciba una respuesta
que implique que su dato fue registrado cuando en realidad la extracción falló.

#### Scenario: Turno procesado con clave primaria activa

- **WHEN** el worker procesa un turno y la clave primaria de Groq tiene cuota disponible
- **THEN** el turno se resuelve normalmente con la clave primaria; no hay impacto observable

#### Scenario: Turno procesado con fallback a clave de respaldo

- **WHEN** el worker procesa un turno y la clave primaria tiene cuota agotada
- **THEN** el sistema usa automáticamente la clave de respaldo y entrega la respuesta al
  candidato sin error visible; el turno se completa con `status: ok`

#### Scenario: Sin claves disponibles — abort silencioso

- **WHEN** ambas claves Groq tienen la cuota agotada o no están configuradas y el extractor
  falla con `GroqRateLimitError` irrecuperable
- **THEN** el worker aborta el turno antes de enviar nada a Chatwoot ni persistir facts
- **AND** retorna `{"status": "skipped_llm_unavailable", "processed": False, "sent_to_chatwoot": False}`
- **AND** el candidato no recibe ninguna respuesta en ese turno
- **AND** el fallo queda registrado en logs con `[LLM_GATE]` y el motivo detallado

## MODIFIED Requirements

### Requirement: Disponibilidad del LLM durante el procesamiento de un turno

El sistema SHALL procesar cada turno de candidato sin error de LLM siempre que al menos una
clave Groq válida esté disponible (`GROQ_API_KEY` o `GROQ_API_KEY_BACKUP`). Si la clave
primaria tiene la cuota agotada, el sistema SHALL recuperarse automáticamente usando la clave
de respaldo, sin retornar un error al candidato ni dejar el turno sin procesar.

#### Scenario: Turno procesado con clave primaria activa

- **WHEN** el worker procesa un turno y la clave primaria de Groq tiene cuota disponible
- **THEN** el turno se resuelve normalmente con la clave primaria; no hay impacto observable

#### Scenario: Turno procesado con fallback a clave de respaldo

- **WHEN** el worker procesa un turno y la clave primaria tiene cuota agotada
- **THEN** el sistema usa automáticamente la clave de respaldo y entrega la respuesta al
  candidato sin error visible; el turno se completa con `status: ok`

#### Scenario: Sin claves disponibles

- **WHEN** ambas claves Groq tienen la cuota agotada o no están configuradas
- **THEN** el worker registra el error en el log y la tarea Celery falla; el candidato no
  recibe respuesta en ese turno (comportamiento de fallo actual, sin degradación adicional)

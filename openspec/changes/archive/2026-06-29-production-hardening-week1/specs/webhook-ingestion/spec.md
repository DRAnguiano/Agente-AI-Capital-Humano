## MODIFIED Requirements

### Requirement: Encolado asíncrono con debounce

El sistema SHALL procesar los mensajes entrantes de forma asíncrona vía Celery (queue
`inbound`) **por defecto**: `INBOUND_DEBOUNCE_ENABLED` SHALL tener valor por defecto `true`,
de modo que el webhook responda rápido y el worker aplique el guard de turno actual y la
deduplicación de mensajes rápidos. El path síncrono SHALL quedar reservado únicamente como
modo de diagnóstico explícito (`INBOUND_DEBOUNCE_ENABLED=false`).

#### Scenario: Debounce activo (default)
- **WHEN** llega un mensaje válido y `INBOUND_DEBOUNCE_ENABLED` no está explícitamente en `false`
- **THEN** el sistema encola el payload (account/conversation/inbox/message/channel_user_id/contenido) y responde sin haber generado la respuesta todavía

#### Scenario: Debounce desactivado explícitamente (modo diagnóstico)
- **WHEN** `INBOUND_DEBOUNCE_ENABLED=false`
- **THEN** el mensaje se procesa de forma síncrona en el mismo request, sin pasar por el worker

## ADDED Requirements

### Requirement: Ingesta idempotente de mensajes

El sistema SHALL garantizar que un mismo mensaje entrante recibido más de una vez (p. ej.
un reintento del webhook de Chatwoot tras un timeout) no se persista dos veces ni genere
una segunda respuesta al candidato. La persistencia de mensajes (`save_message`) SHALL ser
idempotente: una inserción cuyo mensaje ya exista no debe crear una fila duplicada.

#### Scenario: Reintento del mismo mensaje en el path síncrono
- **WHEN** Chatwoot reintrega el mismo mensaje (mismo identificador / mismo contenido y clave de conversación) y el path síncrono lo procesa por segunda vez
- **THEN** no se inserta una segunda fila en `rh_messages` y no se reenvía el reply al candidato

#### Scenario: Mensajes rápidos duplicados en el worker
- **WHEN** el worker recibe dos payloads con el mismo `message_id`
- **THEN** la deduplicación conserva exactamente una ejecución y descarta la repetida

### Requirement: Durabilidad de la cola de mensajes

El sistema SHALL garantizar entrega al-menos-una-vez de los mensajes encolados: si un
worker muere durante el procesamiento de una tarea, el mensaje SHALL reencolarse para
reintento en lugar de descartarse silenciosamente. La configuración de Celery SHALL usar
`task_acks_late=true` y `task_reject_on_worker_lost=true`.

#### Scenario: Worker cae a media tarea
- **WHEN** el worker termina abruptamente (OOM/restart) mientras procesa un mensaje encolado
- **THEN** el broker reencola el mensaje y otro worker lo procesa, sin pérdida del candidato

#### Scenario: Reintento sin duplicar efectos
- **WHEN** un mensaje se reencola y se vuelve a procesar tras la caída del worker
- **THEN** la ingesta idempotente evita una segunda fila persistida o un reply duplicado

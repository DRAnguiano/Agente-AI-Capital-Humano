# followup-scheduler Specification

## Purpose

Recuperar leads que se enfriaron creando tareas de seguimiento de forma controlada, vía
Celery Beat (`app/followup/`). Detecta leads sin actividad reciente, decide el contenido
según el campo de perfil faltante, respeta ventanas horarias y límites de reintentos, y
persiste las tareas en `rh_seguimiento_tareas`.

## Requirements

### Requirement: Elegibilidad por canal productivo

El sistema SHALL programar seguimientos automaticos solo para leads que provienen
de canales productivos operados por Chatwoot. Chatwoot es la capa operativa y de
centralizacion: hoy puede recibir pruebas desde Telegram demo, y el canal final
esperado es WhatsApp via Chatwoot; en el futuro tambien podra recibir webchat u
otros inboxes integrados a Chatwoot.

El sistema SHALL tratar `telegram_demo`, canales `test_*`, `debug_*`,
`shadow_test*`, `test_faq*` y `test_verify*` como canales o claves de laboratorio,
no como leads productivos para follow-up. `telegram_demo` MAY generar follow-up
solo si existe un flag explicito de laboratorio, por ejemplo
`ENABLE_DEMO_FOLLOWUP=true`.

#### Scenario: Lead productivo via Chatwoot
- **WHEN** un lead proviene de `source_channel='chatwoot'` y cumple las reglas de
  temperatura, etapa e intentos
- **THEN** el sistema puede crear una tarea de seguimiento automatico

#### Scenario: Telegram demo bloqueado por default
- **WHEN** un lead proviene de `source_channel='telegram_demo'`
- **AND** `ENABLE_DEMO_FOLLOWUP` no esta activado
- **THEN** el sistema no crea tareas de seguimiento automatico para ese lead

#### Scenario: Canal de prueba bloqueado
- **WHEN** el `lead_key` o `source_channel` empieza con `test_`, `debug_`,
  `shadow_test`, `test_faq` o `test_verify`
- **THEN** el sistema no crea tareas de seguimiento automatico para ese lead

#### Scenario: Nuevos inboxes via Chatwoot
- **WHEN** WhatsApp, webchat u otro canal futuro entra por Chatwoot
- **THEN** el scheduler lo trata como lead productivo usando `source_channel='chatwoot'`
  y no necesita acoplarse al nombre del inbox final

### Requirement: Detección de leads fríos y creación de tareas

El sistema SHALL detectar leads elegibles para seguimiento y crear una tarea en
`rh_seguimiento_tareas`, eligiendo el contenido según el primer campo de perfil faltante
del lead.

#### Scenario: Lead frío con campo faltante
- **WHEN** un lead lleva sin actividad el tiempo definido y tiene un campo de perfil incompleto
- **THEN** el sistema crea una tarea de seguimiento dirigida a ese campo faltante

#### Scenario: Etapa excluida de seguimiento
- **WHEN** el lead está en una etapa excluida (`lost`, `closed`, `safety_review`)
- **THEN** el sistema no genera seguimiento automático para ese lead

### Requirement: Límite de reintentos y espaciado

El sistema SHALL limitar a `MAX_INTENTOS` (3) los intentos de seguimiento por lead y
exigir una espera mínima entre intentos (2 días tras el 1º, 3 días tras el 2º).

#### Scenario: Espera insuficiente
- **WHEN** no ha pasado la espera mínima desde el último intento
- **THEN** el sistema no crea un nuevo intento todavía

#### Scenario: Máximo de intentos alcanzado
- **WHEN** el lead ya acumuló el máximo de intentos
- **THEN** el sistema deja de generar seguimientos automáticos para ese lead

### Requirement: Respeto de ventana horaria

El sistema SHALL programar el envío de cada seguimiento dentro de la próxima ventana
horaria válida, no a cualquier hora.

#### Scenario: Fuera de ventana
- **WHEN** corresponde un seguimiento fuera de la ventana horaria permitida
- **THEN** el sistema lo programa para la próxima ventana válida

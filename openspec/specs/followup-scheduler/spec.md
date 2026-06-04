# followup-scheduler Specification

## Purpose

Recuperar leads que se enfriaron creando tareas de seguimiento de forma controlada, vía
Celery Beat (`app/followup/`). Detecta leads sin actividad reciente, decide el contenido
según el campo de perfil faltante, respeta ventanas horarias y límites de reintentos, y
persiste las tareas en `rh_seguimiento_tareas`.

## Requirements

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

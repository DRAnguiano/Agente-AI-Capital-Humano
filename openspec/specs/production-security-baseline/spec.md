# production-security-baseline Specification

## Purpose

TBD — Establece los controles de seguridad mínimos para el despliegue en producción: autenticación fail-closed de endpoints internos, validación de configuración segura en el arranque, gestión de secretos sin valores en repositorio, aislamiento de puertos de base de datos, y persistencia del schedule de Celery Beat.

## Requirements

### Requirement: Autenticación fail-closed de endpoints internos y de administración

El sistema SHALL exigir autenticación por API key en los endpoints de escritura,
orquestación, clasificación, administración y reindexación, y SHALL denegar el acceso
(`401`) cuando la API key esperada no coincida o no esté configurada. Aplica a `/ask`, `/orchestrate/message`,
`/classify`, `/admin/release-human-review` (vía `INTERNAL_API_KEY`) y `/reindex` (vía
`REINDEX_API_KEY`). Una API key vacía NO SHALL interpretarse como "sin autenticación".

#### Scenario: API key esperada no configurada
- **WHEN** `INTERNAL_API_KEY` (o `REINDEX_API_KEY`) está vacía y llega una petición al endpoint protegido
- **THEN** el sistema responde `401` y no ejecuta la operación (fail-closed)

#### Scenario: API key inválida
- **WHEN** la petición trae una API key distinta a la esperada
- **THEN** el sistema responde `401` y no ejecuta la operación

#### Scenario: API key válida
- **WHEN** la petición trae la API key correcta
- **THEN** el sistema ejecuta la operación normalmente

### Requirement: Validación de configuración segura en el arranque

En entorno de producción, el sistema SHALL fallar el arranque (o registrar un error
bloqueante) si las API keys críticas (`INTERNAL_API_KEY`, `REINDEX_API_KEY`) o el token de
webhook (`CHATWOOT_WEBHOOK_TOKEN`) están vacíos, o si el token de webhook conserva un valor
de desarrollo conocido.

#### Scenario: Arranque con secretos faltantes en producción
- **WHEN** el servicio arranca en producción con una API key crítica vacía
- **THEN** el arranque falla o emite un error bloqueante que impide servir tráfico con configuración insegura

#### Scenario: Arranque con configuración completa
- **WHEN** todas las API keys y tokens críticos tienen valores fuertes configurados
- **THEN** el servicio arranca normalmente

### Requirement: Gestión de secretos sin valores en repositorio

El sistema SHALL provisionar los secretos (claves de Groq, token de Chatwoot, token de
ngrok, token de Telegram, contraseñas de PostgreSQL y Neo4j, `SECRET_KEY_BASE`) mediante
variables de entorno inyectadas, no mediante valores hardcodeados en archivos versionados.
Las contraseñas de base de datos NO SHALL ser valores triviales o por defecto. El
repositorio SHALL incluir un `.env.example` con placeholders, nunca con secretos reales.

#### Scenario: Contraseña de BD no trivial
- **WHEN** se configura la contraseña de PostgreSQL o Neo4j
- **THEN** no se usa un valor trivial/por defecto (p. ej. `lapass`, `neo4j_password`); se usa un valor fuerte generado

#### Scenario: Plantilla de entorno sin secretos
- **WHEN** un colaborador clona el repositorio
- **THEN** encuentra `.env.example` con placeholders y ninguna credencial real versionada

### Requirement: Puertos de base de datos no expuestos al host en producción

El despliegue de producción NO SHALL exponer al host los puertos de PostgreSQL (`5432`) ni
de Neo4j (`7474`, `7687`); el acceso SHALL ocurrir únicamente por la red interna de Docker
entre contenedores.

#### Scenario: Sin mapeo de puertos de BD
- **WHEN** se levanta el stack de producción
- **THEN** los servicios `postgres` y `neo4j` no publican `ports:` al host y solo son alcanzables desde la red interna de Docker

### Requirement: Registro de cuentas de Chatwoot deshabilitado

El despliegue de producción SHALL deshabilitar el registro abierto de cuentas en Chatwoot
(`ENABLE_ACCOUNT_SIGNUP=false`) para impedir el alta no autorizada de usuarios con acceso a
conversaciones de candidatos.

#### Scenario: Intento de registro abierto
- **WHEN** un visitante intenta crear una cuenta en la instancia de Chatwoot en producción
- **THEN** el registro está deshabilitado y la operación es rechazada

### Requirement: Persistencia del schedule de Celery Beat

El schedule de Celery Beat SHALL persistir entre reinicios del contenedor (almacenado en un
volumen, no en `/tmp` efímero) para evitar la re-ejecución o pérdida de seguimientos
programados al reiniciar el servicio.

#### Scenario: Reinicio del servicio beat
- **WHEN** el contenedor de Celery Beat se reinicia
- **THEN** el schedule persistido se conserva y los seguimientos no se re-programan desde cero

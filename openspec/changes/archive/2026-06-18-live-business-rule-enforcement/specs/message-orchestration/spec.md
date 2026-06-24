# message-orchestration (delta)

## ADDED Requirements

### Requirement: El camino vivo aplica handoff ante vacante B1 / Estados Unidos

El camino vivo (`knowledge_orchestrator.handle_message`) SHALL marcar `requires_human` y
rutear a revisión humana cuando el candidato menciona una vacante B1, Estados Unidos,
cruce a EUA o ruta americana, mediante un guard determinista que NO depende del seed de
Neo4j. El bot SHALL NOT continuar perfilando como vacante estándar ni emitir juicio
("no es problema", aprobar o descartar). La regla aplica aunque Neo4j esté en fallback.

#### Scenario: Mención de vacante B1 → handoff vivo
- **WHEN** el candidato indica interés en una vacante B1 o para Estados Unidos
- **THEN** el contrato vivo resuelve `requires_human=true`
- **AND** el sistema no añade pregunta de funnel de perfilamiento estándar en ese turno

#### Scenario: Mención de cruce / ruta americana → handoff vivo
- **WHEN** el candidato menciona cruce a EUA, visa o ruta americana
- **THEN** el contrato vivo resuelve `requires_human=true`
- **AND** la respuesta canaliza a un reclutador humano sin emitir juicio de elegibilidad

#### Scenario: Handoff B1 sobrevive a Neo4j en fallback
- **WHEN** Neo4j no resuelve (fallback) y el candidato menciona vacante B1
- **THEN** el guard determinista igual marca `requires_human=true`

### Requirement: El camino vivo aplica handoff ante reingreso

El camino vivo SHALL marcar `requires_human` cuando el candidato indica haber trabajado
previamente con la empresa, mediante un guard determinista. El bot SHALL NOT aprobar ni
rechazar el reingreso automáticamente; solo registra y canaliza, pidiendo nombre completo
y motivo de salida. La señal de reingreso es distinta de "ya conseguí otro trabajo"
(dropoff), que no es reingreso.

#### Scenario: Candidato indica que ya trabajó en la empresa → handoff vivo
- **WHEN** el candidato indica que trabajó antes con la empresa o que quiere volver
- **THEN** el contrato vivo resuelve `requires_human=true`
- **AND** la respuesta no aprueba ni descarta el reingreso

#### Scenario: "Ya conseguí otro trabajo" no es reingreso
- **WHEN** el candidato dice que ya consiguió otro empleo (señal de abandono)
- **THEN** el contrato vivo NO lo trata como reingreso

### Requirement: El camino vivo marca experiencia no objetivo como escuelita

El camino vivo SHALL identificar torton, rabón, reparto local/interurbano y similares como
experiencia no-objetivo para la vacante principal. SHALL NOT confirmarlos como `full` ni
como `sencillo`. La experiencia no-objetivo SHALL canalizarse a valoración de Capital
Humano (señal de escuelita), no tomarse como experiencia directa en full/sencillo.

#### Scenario: Experiencia en torton → no confirma vehicle_type
- **WHEN** el candidato declara experiencia en torton/rabón/reparto
- **THEN** el sistema NO persiste `experience.vehicle_type` como `full` ni `sencillo`
- **AND** marca la experiencia como no-objetivo (escuelita / valoración humana)

### Requirement: El sistema no emite "caduca"/"caducidad" en la respuesta

El sistema SHALL usar `vence`/`vigencia`/`vencimiento` para referirse al vencimiento de
documentos médicos o de licencia, en cualquier modo de respuesta del camino vivo
(plantilla, RAG o LLM amistoso). SHALL NOT emitir `caduca` ni `caducidad` en la respuesta
al candidato.

#### Scenario: Respuesta sobre vigencia usa "vence", no "caduca"
- **WHEN** el sistema genera una respuesta sobre el vencimiento de licencia o apto médico
- **THEN** la respuesta usa `vence`, `vencimiento` o `vigencia`
- **AND** la respuesta no contiene `caduca` ni `caducidad`

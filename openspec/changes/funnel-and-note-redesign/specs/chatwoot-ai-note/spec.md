## MODIFIED Requirements

### Requirement: Formato canónico de la Nota IA

El sistema SHALL generar la nota privada de Chatwoot en **lenguaje administrativo** para Capital
Humano (no técnico): SHALL NOT usar `Canal`, `Embudo`, `Etapa`, `Bloqueo`, `Riesgo` (salvo
`riesgo_alto`), `Requiere humano`, ni nombres de labels. La cabecera SHALL describir el **escenario
operativo** del candidato. El formato base es:

```
🤖 Nota IA: <escenario operativo>

Último mensaje: "<literal del candidato, máx 500 chars>"

👤 Contacto
Nombre: <nombre | No disponible>
Teléfono: <teléfono | No disponible>

📌 Estado del candidato
<estado operativo en lenguaje simple>

✅ Lo que ya sabemos
<solo los datos relevantes al escenario, confirmados>

⚠️ Falta confirmar              ← CONDICIONAL: solo si hay pendientes
<lo que falta, en lenguaje simple>

👥 Para Capital Humano
<qué debe hacer Capital Humano>
Requiere Agente: <Sí | No>

⏭️ Siguiente acción
<una única acción, dinámica según el último pendiente resuelto>
```

`Riesgo` SHALL aparecer únicamente cuando la label `riesgo_alto` esté activa. `Requiere Agente`
SHALL reemplazar a `Requiere humano`. La sección `👤 Contacto` SHALL NOT incluir `Canal`.

#### Scenario: Sin lenguaje técnico
- **WHEN** se genera la nota privada
- **THEN** la nota no contiene `Embudo`, `Etapa`, `Bloqueo actual`, `Canal` ni `Requiere humano`
- **AND** no contiene nombres de labels técnicas

#### Scenario: Cabecera por escenario
- **WHEN** el candidato corresponde a un escenario operativo (escuelita, perfil listo local, etc.)
- **THEN** la cabecera describe ese escenario (p. ej. `🤖 Nota IA: Candidato para Escuelita Transmontes`)

#### Scenario: Riesgo solo si alto
- **WHEN** el candidato no tiene `riesgo_alto`
- **THEN** la nota no muestra ninguna línea de `Riesgo`

#### Scenario: Requiere Agente reemplaza Requiere humano
- **WHEN** un escenario requiere intervención de Capital Humano
- **THEN** la nota muestra `Requiere Agente: Sí` y nunca `Requiere humano`

## ADDED Requirements

### Requirement: Cabecera y contenido de la nota por escenario operativo

El sistema SHALL seleccionar el escenario operativo de la nota desde facts/labels/estado
(determinista, no LLM) y SHALL mostrar solo los campos relevantes a ese escenario. Escenarios
mínimos: nuevo/interesado, objetivo en captura, perfil listo local, perfil listo foráneo,
unidad ambigua, escuelita, escuelita sin licencia B/E (no aplica), CECATI (sin experiencia),
B1/EUA, reingreso, edad fuera de perfil, riesgo/sensible, pendiente por licencia/apto, y
licencia/apto vencidos en trámite con comprobante.

#### Scenario: Escuelita muestra solo lo mínimo
- **WHEN** el candidato es escuelita (experiencia no objetivo)
- **THEN** `Lo que ya sabemos` muestra la experiencia no objetivo y la licencia si existe
- **AND** no lista apto, cartas, ciudad ni edad como pendientes principales

#### Scenario: No aplica no ofrece continuar
- **WHEN** el escenario es "no aplica" (escuelita sin B/E, CECATI, edad fuera)
- **THEN** la nota indica el cierre y no propone continuar el flujo automático

#### Scenario: Perfil listo local muestra ciudad exacta
- **WHEN** el candidato es perfil listo local
- **THEN** `Ciudad` muestra la ciudad exacta de la ZM Laguna (Torreón, Gómez Palacio, Lerdo o Matamoros), no "La Laguna"

### Requirement: Documento laboral mostrado según residencia

El sistema SHALL mostrar el requisito de documento laboral según la residencia: para candidato
local de la ZM Laguna, "cartas laborales o semanas cotizadas del IMSS"; para foráneo, "2 cartas
laborales membretadas". SHALL NOT mostrar Infonavit ni mezclar ambos requisitos.

#### Scenario: Documento local
- **WHEN** el candidato es local de la ZM Laguna
- **THEN** la nota describe el documento como "cartas laborales o semanas cotizadas del IMSS"

#### Scenario: Documento foráneo
- **WHEN** el candidato es foráneo
- **THEN** la nota describe el documento como "2 cartas laborales membretadas"

### Requirement: Siguiente acción dinámica según el pendiente resuelto

La `⏭️ Siguiente acción` SHALL reflejar el siguiente pendiente del núcleo del perfil y SHALL
actualizarse cuando el candidato resuelve uno (al enviar/confirmar un dato, la acción avanza al
siguiente pendiente). Con el núcleo completo, SHALL indicar el cierre del escenario: local →
"Validar documentos y continuar proceso"; foráneo → "Validar traslado, documentos y continuidad".

#### Scenario: Avance al resolver un pendiente
- **GIVEN** la siguiente acción pedía la licencia
- **WHEN** el candidato confirma/envía la licencia y queda pendiente el apto
- **THEN** la siguiente acción pasa a pedir el apto médico

#### Scenario: Núcleo local completo
- **GIVEN** un candidato local con todo el núcleo confirmado
- **WHEN** se genera la nota
- **THEN** la siguiente acción es "Validar documentos y continuar proceso"

#### Scenario: Núcleo foráneo completo
- **GIVEN** un candidato foráneo con todo el núcleo confirmado
- **WHEN** se genera la nota
- **THEN** la siguiente acción es "Validar traslado, documentos y continuidad"

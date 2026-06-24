## ADDED Requirements

### Requirement: Documento laboral persistido según residencia

El sistema SHALL persistir el documento laboral en el fact canónico de evidencia
(`documents.proof`) con su tipo: `cartas` o `semanas_imss`. La validez del documento SHALL
evaluarse según residencia (local de la ZM Laguna acepta cualquiera de los dos; foráneo requiere
cartas membretadas), pero el fact persistido SHALL reflejar lo que el candidato declaró, con
evidencia literal y sin sobrescribir un documento ya confirmado.

#### Scenario: Semanas IMSS declaradas
- **WHEN** el candidato dice que cuenta con su documento de semanas cotizadas del IMSS
- **THEN** el sistema persiste `documents.proof = semanas_imss`

#### Scenario: Cartas declaradas
- **WHEN** el candidato dice que cuenta con cartas laborales
- **THEN** el sistema persiste `documents.proof = cartas`

### Requirement: Estado vencido-en-trámite con comprobante

El sistema SHALL persistir una señal canónica de trámite con comprobante para licencia y/o apto
(p. ej. `license.tramite_comprobante = true`, `medical.tramite_comprobante = true`) cuando el
candidato declare que el documento está vencido pero tiene cita/trámite comprobable. Esta señal
es la fuente determinista para continuar con `aclaracion_pendiente` en vez de bloquear.

#### Scenario: Licencia vencida con comprobante
- **WHEN** el candidato dice que su licencia está vencida pero tiene comprobante de cita
- **THEN** el sistema persiste la señal de trámite con comprobante para la licencia

#### Scenario: Vencido sin comprobante no marca trámite
- **WHEN** el candidato dice que su licencia está vencida y no la está tramitando
- **THEN** el sistema no persiste señal de trámite con comprobante

### Requirement: Afirmación global no confirma vigencia

El sistema SHALL NOT persistir vigencia de licencia ni de apto a partir de afirmaciones globales
no específicas ("todo en regla", "todo bien", "todo en orden"); estas SHALL dejar la vigencia
como no confirmada (ambigua) para que el funnel pregunte el vencimiento.

#### Scenario: "Todo en regla" no escribe vigencia
- **WHEN** el candidato dice "tengo todo en regla"
- **THEN** el sistema no marca `license` ni `medical.apto_status` como vigentes

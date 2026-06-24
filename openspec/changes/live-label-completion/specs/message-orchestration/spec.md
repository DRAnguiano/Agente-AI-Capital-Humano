## ADDED Requirements

### Requirement: Canalización a Capital Humano entrega acuse específico por motivo

El sistema SHALL enviar al candidato un acuse público específico según el motivo de la
canalización a Capital Humano (handoff), y SHALL NOT dejar al candidato sin respuesta. Tras el
acuse el bot detiene el perfilamiento; el humano toma el caso. SHALL NOT suprimir la respuesta
pública solo por `requires_human`.

Mensajes por motivo (al menos):
- **reingreso**: solicita nombre completo y motivo de salida;
- **B1 / EUA**: indica que es una vía distinta a la vacante publicada (operador full/sencillo);
- **escuelita** (experiencia no-objetivo): indica que Capital Humano revisará si hay generación
  disponible;
- **cecati** (sin experiencia): orientación al CECATI;
- conducta grosera/riesgo o fuera de alcance: acuse de canalización.

#### Scenario: Handoff no deja al candidato en silencio
- **WHEN** un turno resulta en canalización a Capital Humano (`requires_human`)
- **THEN** el sistema envía un acuse público al candidato
- **AND** no suprime la respuesta por el solo hecho de `requires_human`

#### Scenario: Acuse de reingreso
- **WHEN** el motivo de canalización es reingreso
- **THEN** el acuse solicita nombre completo y motivo de salida

#### Scenario: Acuse de B1
- **WHEN** el motivo de canalización es B1/EUA
- **THEN** el acuse indica que es una vía distinta a la vacante publicada

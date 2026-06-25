## ADDED Requirements

### Requirement: Punto único de extracción antes de bifurcar

El sistema SHALL computar el `TurnExtraction` del mensaje **una sola vez al inicio del turno**,
antes de bifurcar entre el orquestador y el guard del worker, y ambos caminos SHALL consumir
ese mismo objeto. SHALL NOT re-extraer el mismo texto en múltiples puntos del turno.

#### Scenario: Una extracción por turno
- **WHEN** llega un mensaje del candidato
- **THEN** la extracción del turno se realiza una vez y su resultado alimenta funnel, nudge, ack, labels y persistencia

### Requirement: Autoridad única sobre la respuesta

El reply de cara al candidato SHALL decidirse sobre el `TurnExtraction` único, no por el orden
de ejecución de dos caminos. SHALL NOT existir un camino (guard) que pise incondicionalmente
el reply ya producido por otro (orquestador) tras una segunda extracción del mismo turno.

#### Scenario: Reply no depende de quién corre último
- **WHEN** un turno produce facts y una posible duda embebida
- **THEN** el reply se determina a partir del `TurnExtraction` único, de forma estable e independiente del orden interno de los componentes

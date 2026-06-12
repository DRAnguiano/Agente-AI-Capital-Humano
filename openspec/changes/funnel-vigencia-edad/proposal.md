# Proposal: funnel-vigencia-edad

## Why

Smoke 2026-06-12 11:31 (canal demo) + decisiones de negocio del mismo día:

1. **La edad nunca se pregunta** en el flujo vivo, y es un descalificador duro:
   mayores de 56 años se descartan. Debe preguntarse TEMPRANO para no gastar
   turnos en perfiles no viables.
2. **"¿Está vigente?" es una pregunta débil**: el candidato dice "sí" y el
   sistema acepta vigencia sin fecha (el smoke aceptó un apto que vencía en 18
   días). Las preguntas deben provocar la fecha: "¿Cuándo vence su licencia?" /
   "¿Cuándo vence su apto médico?", con la regla oficial de >3 meses (2C.0c) y
   el guion de trámite fijo.
3. Los operadores presionan para ser contratados sin documentos vigentes: el
   guion de trámite NO admite desviaciones.

## What Changes

- **Flujo vivo reordenado**: ciudad → edad → tipo de unidad → licencia (tipo +
  "¿cuándo vence?") → apto ("¿cuándo vence?") → años de experiencia → documento
  laboral según residencia.
- **Edad**: pregunta temprana; >56 → guion de descarte cortés y cierre del
  funnel (sin seguir perfilando).
- **Vencimientos**: capturar fecha o tiempo relativo ("en 2 años", "en
  diciembre"); si el candidato responde "sí está vigente" sin fecha →
  repreguntar "¿En cuánto tiempo se le vence?" (la del documento que
  corresponda).
- **Regla >3 meses**: vence en <3 meses o vencido → "¿Ya tiene el papel donde
  lo tramitó?"; sin papel → guion fijo: "Por el momento no podemos seguir con
  su solicitud; en cuanto tenga el papel de trámite de su licencia/apto,
  continuamos." Sin desviaciones aunque el candidato insista; con papel de
  trámite → continúa con `aclaracion_pendiente` para validación de CH.
- **Puente suave**: tras responder una duda a media precalificación, retomar
  con "Cuando guste continuamos con su registro — me decía, ¿...?" (máx. una
  pregunta por turno).

## Open questions (requieren confirmación de negocio)

- Copy exacto del descarte por edad. Borrador: "Gracias por su interés. Por el
  momento el perfil de esta vacante considera operadores de hasta 56 años, por
  lo que no podemos continuar con su solicitud."
- Etiqueta/etapa del descartado por edad (¿solo cierre + nota, sin label nueva?).
- ¿El descarte por edad es definitivo o CH puede revisar excepciones?

## Impact

- Specs: deltas en `message-orchestration` y `profile-extraction`.
- Código: `current_turn.py` (orden del funnel + preguntas), extractor de
  fechas/tiempos relativos de vencimiento, lógica de descarte y guion de
  trámite. Tests rojos primero.
- El gate de `perfil_listo` no cambia en este change (6 núcleo); la edad
  descalifica pero no es 7º requisito del gate.

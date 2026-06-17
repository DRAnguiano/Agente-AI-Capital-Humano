# Design: core-consistency-fixes

## #1 — Voz de equipo

La regla ya existe (y es severa) en `persona_config.py:17-23` pero el propio SYSTEM_PROMPT
la viola en líneas 41,42,101,102,127,135,139,197,221,258 (usa "Capital Humano" como
tercero). `context_builder.py` la refuerza correctamente. Como los LLMs siguen ejemplos por
encima de reglas abstractas, los ejemplos contradictorios producen respuestas inconsistentes.

El contrato fija el **comportamiento observable** (la respuesta al candidato no menciona
"Capital Humano" como tercero; el prompt no induce ese uso). La implementación posterior:
reescribir las ~10 instrucciones/ejemplos del SYSTEM_PROMPT a voz de equipo.

## #8 — Política del ciclo de vida de HUMAN_REVIEW (DECISIÓN)

**Decisión:** el handoff a revisión humana **no es auto-reversible por el bot**, pero **sí
es liberable por acción humana/operativa explícita**.

Razones:
- HUMAN_REVIEW se activa por B1/EUA, reingreso, sustancias/seguridad, riesgo alto. Una vez
  que un humano toma el caso, el bot NO debe "deshacer" el handoff porque el candidato luego
  diga algo benigno — eso rompería la integridad de la derivación en casos sensibles.
- Pero el bloqueo permanente actual (`db.py:update_stage`, CASE que nunca cambia) deja leads
  válidos atrapados sin salida. Eso es el bug.

Reglas del contrato:
1. El bot SHALL NOT salir de HUMAN_REVIEW por mensajes del candidato (sin auto-regresión).
2. La conversación SHALL poder liberarse por acción humana explícita (agente resuelve/reasigna
   en Chatwoot, o vía admin/ops), tras lo cual el flujo normal MAY reanudarse.
3. SHALL NOT auto-expirar por tiempo (re-engancharía el bot en un caso sin resolver).
4. SHALL NOT quedar en bloqueo permanente sin vía de liberación.

**Mecanismo (detalle de implementación, no fijado por el contrato):** una vía de liberación
explícita — p. ej. detectar la señal del agente (handoff resuelto / reasignado a bot) o un
endpoint admin/ops que reponga el stage. El spec fija el comportamiento; el mecanismo se
decide al implementar.

## #15 — Normalización de zona horaria

Decisión de negocio: **`America/Mexico_City` es la zona canónica** del horario de oficina
(8:00–17:30 L–V) para la política de llamada/seguimiento. El código del check ya la usa
(`current_turn._TZ_CENTRO`, `knowledge_orchestrator`). Se normaliza el texto del contrato en
`live-reply-grounding-and-quality` (`America/Monterrey` → `America/Mexico_City`), revirtiendo
la nota previa de su design que proponía unificar a Monterrey.

Fuera de alcance: `followup/ventana.py` y `celery_app.py` siguen en `America/Monterrey`
(followup async, ventana 08:30–20:30 L–S — dominio distinto; además ambas zonas son
funcionalmente equivalentes en offset).

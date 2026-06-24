## Context

El bot actualmente ejecuta handoff inmediato cuando detecta señales de escuelita, CECATI, B1 o reingreso. El reclutador en Chatwoot recibe el lead sin el dato mínimo que determina su viabilidad, generando retrabajo. Las funciones de handoff viven en `_apply_business_rule_overrides` (knowledge_orchestrator) y emiten `requires_human=True` con un texto fijo.

Estado actual del flow:
```
señal (escuelita|cecati|b1|reingreso) → requires_human=True → acuse genérico → handoff
```

Estado objetivo:
```
señal → verificación previa (pregunta dato mínimo) → dato OK → requires_human=True + acuse específico
                                                    → dato faltante → bot pregunta
                                                    → dato negativo → cierre informativo
```

## Goals / Non-Goals

**Goals**
- Cada rama de handoff verifica un dato mínimo antes de activar `requires_human`.
- El acuse de handoff incluye el dato recolectado (licencia, tipo de unidad, tipo de vacante).
- La nota IA refleja `Siguiente acción` concreta por rama.

**Non-Goals**
- No añadir más de una ronda de verificación por rama.
- No cambiar el flujo de candidatos del funnel normal (ciudad→edad→licencia…).
- No modificar el texto del acuse de handoff ya aprobado por negocio (solo enriquecerlo con el dato).

## Decisions

**D1: Verificación como guard en `_apply_business_rule_overrides`, no en un nuevo módulo**

Las señales de handoff ya se detectan aquí. Añadir la verificación previa en el mismo lugar evita duplicar la detección. La función ya tiene acceso a `turn_signals` y `message`; para acceder a `lead_memory` se pasa como parámetro adicional o se consulta inline.

Alternativa descartada: módulo `pre_handoff_verifier.py` separado. Más limpio architectónicamente pero introduce un salto adicional sin beneficio hasta que haya más ramas.

**D2: Estado de verificación como fact canónico `handoff.<branch>.verified = pending|ok|no`**

Permite que el funnel sepa si ya pasó la verificación sin depender del historial de mensajes. Cuando `verified=pending` el bot hace la pregunta de verificación. Cuando `ok` → handoff. Cuando `no` → cierre informativo.

Alternativa descartada: usar solo el `last_bot_message` para inferir si ya se preguntó. Frágil ante múltiples turnos.

**D3: Preguntas de verificación servidas por `next_prehandoff_question(branch, facts)`**

Función nueva en `current_turn.py` análoga a `next_question_from_missing_facts` pero para el sub-funnel de pre-handoff. Retorna `None` cuando el dato está completo (handoff puede proceder).

**D4: `Siguiente acción` en nota IA usa el branch y los facts para texto concreto**

En `render_candidate_note`, si `handoff_branch` está en facts y `handoff.*.verified=ok`, el campo `Siguiente acción` dice "Verificar historial de [nombre]" (reingreso), "Confirmar vacante de [unidad]" (b1), etc.

## Risks / Trade-offs

- [Riesgo] Un candidato que activa la señal de escuelita pero tiene licencia E podría terminar en el funnel normal en vez del handoff. → Mitigación: si la verificación resulta en `ok`, el handoff ocurre inmediatamente y el funnel normal no interfiere.
- [Riesgo] Dos turnos de verificación si el candidato da el dato ambiguo. → Mitigación: la verificación solo hace UNA pregunta; si la respuesta es ambigua, el turno siguiente re-evalúa con los facts actualizados.

## Migration Plan

1. Añadir fact `handoff.<branch>.verified` a `rh_lead_facts_v2` (usa el schema existente, no requiere migración de BD).
2. Modificar `_apply_business_rule_overrides` para cada rama: consultar `handoff.<branch>.verified` en `lead_memory` antes de emitir `requires_human`.
3. Añadir `next_prehandoff_question` en `current_turn.py`.
4. Actualizar `render_candidate_note` para `Siguiente acción` por rama.
5. Tests Groq-free por rama antes de rebuild.

## Open Questions

- ¿El fact `handoff.<branch>.verified` debe borrarse si el candidato regresa después de varios días? Por ahora no — se asume que el estado de licencia no cambia en el corto plazo.

# Design: chatwoot-ai-note-contract

## Arquitectura actual vs. objetivo

```
ACTUAL                              OBJETIVO
─────────────────────────────────── ──────────────────────────────────────
render_candidate_note(              render_candidate_note(
  context,                            context,
  labels,                             labels,     ← solo para sección condicional
  fallback_last_message,              fallback_last_message,
  channel_label                       channel_label
)                                   )

Entradas que usa:                   Entradas que usa:
  lead.next_best_action  ← OK         lead.next_best_action  ← determinístico
  lead.memory_summary    ← LLM!       (eliminado)
  lead.funnel_stage      ← OK         lead.funnel_stage      ← OK
  lead.risk_level        ← OK         lead.risk_level        ← OK
  lead.requires_human    ← OK         lead.requires_human    ← OK
  facts.*                ← OK         facts.*                ← OK
  last_message.message   ← literal OK last_message.message   ← literal OK

Secciones que produce:              Secciones que produce:
  Acción: <next_action>  ← DUPLICA   (eliminada)
  Último mensaje         ← OK        Último mensaje         ← OK
  👤 Contacto            ← OK        👤 Contacto            ← OK
  🧠 Memoria breve       ← LLM text! (eliminada en v1)
  📋 Perfil detectado:               📋 Perfil confirmado:
    Tipo de unidad       ← OK          Tipo de unidad       ← OK
    Experiencia          ← OK          Experiencia          ← OK
    Licencia             ← OK          Licencia             ← OK
    Apto médico          ← OK          Apto médico          ← OK
    Cartas/documentos    ← OK          Cartas/documentos    ← OK
    Ciudad               ← OK          Ciudad               ← OK
    Disponibilidad actual← NOISE!     (eliminada)
    Interés en pago      ← PROHIBIDO  (eliminada)
  📍 Embudo              ← OK        📍 Embudo              ← OK
  ⏭️ Siguiente acción    ← OK        ⏭️ Siguiente acción    ← OK
  🏷️ Labels              ← PROHIBIDO (eliminada)
```

## Sección condicional: motivo de revisión humana

Solo se renderiza cuando `lead.requires_human == True` o cuando hay señales específicas
detectadas en las labels: `considerar_operador_b1`, `reingreso_verificar`.

```
⚠️ Revisión humana requerida
Motivo: Operador B1 / EUA — requiere validación de nivel de inglés y documentación.
```

No es una sección permanente; desaparece cuando `requires_human == False`.

## Decisión por sección eliminada

| Sección | Motivo de eliminación | Alternativa |
|---|---|---|
| `Acción:` superior | Duplica `⏭️ Siguiente acción` exactamente | Conservar solo sección `⏭️` |
| `🧠 Memoria breve` | Contiene `memory_summary` de posible origen LLM; no auditado | Versión futura: resumen desde facts canónicos |
| `Disponibilidad actual` | Campo `candidate.availability_status` no es core del perfil; label `disponible_acudir` está deprecada | No mostrar salvo que planner/handoff decida explícitamente |
| `Interés en pago/compensación` | Prohibido por spec `multi-intent-migration/specs/chatwoot-sync` | N/A |
| `🏷️ Labels` | Prohibido por spec; labels visibles en UI de Chatwoot | N/A |

## Formato final objetivo

```
🤖 Nota IA: Seguimiento de candidato

Último mensaje: "<literal>"

👤 Contacto
Nombre: <nombre | No disponible>
Teléfono: <teléfono | No disponible>
Canal: <canal | Chatwoot>

📋 Perfil confirmado
Tipo de unidad: <Full | Sencillo | Quinta rueda/tráiler por aclarar | Camión local/no objetivo | Pendiente>
Experiencia: <valor | Pendiente>
Licencia: <tipo/estado | Pendiente>
Apto médico: <vigente/renovado/vencido/pendiente>
Cartas/documentos: <estado | Pendiente>
Ciudad: <valor | Pendiente>

⚠️ Pendientes o conflictos          ← CONDICIONAL: solo si existen
<campo>: <conflicto/pendiente clave>

📍 Embudo
Etapa: <etapa calculada desde Postgres>
Bloqueo actual: <bloqueo | Sin bloqueo>
Riesgo: <Bajo | Medio | Alto>
Requiere humano: <Sí | No>

⏭️ Siguiente acción
<una única acción desde el planner>
```

## Invariantes del renderer

1. `next_best_action` aparece **una sola vez** — en `⏭️ Siguiente acción`.
2. `memory_summary` **no se renderiza** en v1.
3. `candidate.availability_status` **no se renderiza** salvo decisión explícita del planner.
4. `interest.payment` **no se renderiza**.
5. La lista de labels **no se renderiza** en el cuerpo de la nota.
6. `facts.*` vacíos muestran `Pendiente`, nunca valores inventados.
7. El renderer es una función pura: mismas entradas → misma salida.

## Cambio en `render_candidate_note` — firma sin cambios

La firma de `render_candidate_note(context, labels, ...)` no cambia para no romper
los callers existentes. El parámetro `labels` se usa solo para la sección condicional
de revisión humana (detectar `considerar_operador_b1` / `reingreso_verificar`).

## Horario/handoff — fuera de alcance

La decisión `perfil listo + fuera de horario → llamada_pendiente + solicitar horario`
pertenece al planner. El renderer solo muestra lo que el planner ya decidió. En v1,
la sección `⏭️ Siguiente acción` muestra `next_best_action` from DB, que el planner
ya calculó. No se implementa lógica de zona horaria ni calendario en este change.

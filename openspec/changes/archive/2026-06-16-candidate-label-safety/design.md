# Design — candidate-label-safety

## Decisiones

### D1. Conjunto terminal como constante única

El conjunto terminal lo define el spec raíz (`chatwoot-label-taxonomy/spec.md:94-101`):

```python
TERMINAL_LABELS = frozenset({
    "perfil_listo",
    "requiere_agente",
    "requiere_revision_ch",
    "riesgo_alto",
    "reingreso_verificar",
})
```

Vivirá en `app/chatwoot_note_sync.py` junto a `OFFICIAL_LABELS` (misma fuente que
ya consume el fallback conceptualmente). La regla se aplica al final del cálculo,
antes de `_filter_official_labels`:

```python
if labels & TERMINAL_LABELS:
    labels.discard("bot_activo")
```

No se duplica el catálogo completo: solo el subconjunto terminal, que el spec
declara explícitamente como regla propia.

### D2. Confirmación de unidad sin regex ni listas nuevas

`perfil_listo` exige `experience.vehicle_type` confirmado. La verificación
reutiliza el catálogo canónico ya existente:

```python
from app.knowledge.business_route_schema import VALID_VEHICLE_TYPES  # {"full", "sencillo"}

vehicle_confirmed = facts.get("experience.vehicle_type") in VALID_VEHICLE_TYPES
```

- `has_experience` (para `documentos`, etc.) puede seguir aceptando `years`.
- La condición de `perfil_listo` cambia a exigir `vehicle_confirmed` además de
  licencia, apto y aceptación.
- `falta_unidad` se emite cuando `experience.vehicle_type` NO está confirmado
  (vacío o valor ambiguo tipo "quinta rueda"), y se remueve al confirmarse —
  mismo patrón que `falta_licencia`/`falta_apto`.
- Valores ambiguos no se interpretan: si el valor no es exactamente `full` o
  `sencillo`, no confirma. La aclaración de jerga es responsabilidad del
  pipeline de comprensión (shadow/planner), no de este módulo.

### D3. Fallback con labels oficiales

`_fallback_chatwoot_labels` (`app/app.py`):

- `requiere_humano` → `requiere_agente` (en ambos puntos: requires_human y
  risk high).
- El resultado pasa por la misma regla terminal de D1 (si emite `perfil_listo`,
  `requiere_agente`, `requiere_revision_ch` o `riesgo_alto`, descarta
  `bot_activo`).
- Defensa en profundidad: el fallback filtra contra `OFFICIAL_LABELS`
  (importando `_filter_official_labels` o `OFFICIAL_LABELS` de
  `chatwoot_note_sync`) para que ninguna label futura fuera de catálogo pueda
  salir por este path.

## Invariantes

1. Ningún path de emisión (cálculo principal o fallback) produce labels fuera
   de `OFFICIAL_LABELS`.
2. `perfil_listo` ⇒ `experience.vehicle_type ∈ {full, sencillo}`.
3. label terminal presente ⇒ `bot_activo` ausente.
4. `falta_unidad` y `perfil_listo` nunca coexisten.

## Limitación conocida

`reingreso_verificar` y `considerar_operador_b1` no tienen hoy path de emisión
en `calculate_candidate_labels` (deuda N7, fuera de alcance). El escenario
terminal de `reingreso_verificar` queda especificado y la regla D1 lo cubre
automáticamente cuando exista emisión; no es testeable end-to-end desde este
módulo hasta entonces.

## Riesgo de regresión en tests existentes

- `test_regression_bot_activo_siempre_presente` usa contexto vacío (sin
  terminales) → sigue verde.
- `test_regression_perfil_listo` y los casos `sencillo` usan facts con
  `vehicle_type` confirmado → siguen verdes.
- Ningún test existente asegura `bot_activo` presente en casos terminales ni
  `perfil_listo` sin unidad.

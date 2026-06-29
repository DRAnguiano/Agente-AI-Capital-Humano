## Context

El bot tiene dos capas que generan texto hacia el candidato: (a) strings deterministas del sistema (funnel, confirms) y (b) LLM amistoso (`_answer_friendly_message`). El problema no es que una u otra capa falle — es que se retroalimentan: el prompt del LLM incluye frases de ejemplo concretas que el LLM reproduce literalmente, y el sistema tiene un string fijo de confirm que dice lo mismo. El resultado es que el candidato ve "Con ese perfil nos interesa conocerle" hasta 3 veces en una misma conversación.

## Goals / Non-Goals

**Goals:**
- Eliminar la repetición de frases formulaicas en una misma conversación.
- El LLM amistoso genera variedad genuina, no imita su propio prompt.
- La confirmación de experiencia es neutra y específica al dato capturado, no un elogio genérico.
- La variante de funnel que suena a entrevista formal desaparece.

**Non-Goals:**
- No cambiar la lógica de ruteo ni cuándo se activa el LLM amistoso.
- No eliminar `_is_strong_candidate` ni la distinción de tono por perfil — solo cambiar cómo se expresa.
- No tocar otras confirmaciones (ciudad, licencia, apto médico) que sí suenan naturales.

## Decisions

**D1: `tono_extra` sin frases literales**
Cambiar de:
```python
"Este candidato ya tiene buen perfil. Cierra con una frase corta que lo anime, "
"tipo 'Con ese perfil nos interesa conocerle' o 'Va por buen camino'."
```
A:
```python
"Este candidato ya tiene buen perfil registrado. Cierra con algo breve y cálido, "
"sin prometer contratación ni repetir frases que ya hayas dicho antes."
```
El LLM sabe generar variedad — no necesita el ejemplo literal; ese ejemplo es exactamente lo que imita.

**D2: Confirmación de experiencia → específica y sin elogio**
Cambiar de: `"Esa experiencia es valiosa. Con ese perfil nos interesa conocerle."`
A: `f"{years} años de experiencia, anotado."` donde `years` viene de los facts actuales.
Si no hay número disponible: `"Experiencia anotada."` como fallback.

**D3: Eliminar la variante problemática del funnel**
`_FUNNEL_STEPS[experience.years]` tiene 3 variantes; eliminar solo:
`"Para su perfil, ¿cuántos años lleva manejando de manera profesional?"`
Quedan las otras dos que suenan naturales para un trailero.

## Risks / Trade-offs

- [Riesgo] Quitar frases de ejemplo puede hacer que el LLM genere respuestas menos enfocadas. → Mitigación: la instrucción de tono sigue siendo clara ("breve y cálido, sin prometer contratación"); temperatura 0.0 ya reduce la varianza.
- [Riesgo] El número de años puede no estar disponible como string en `current` en todos los paths. → Mitigación: fallback a `"Experiencia anotada."` si el valor no es parseable.

## Migration Plan

1. Editar `knowledge_orchestrator.py`: eliminar variante de funnel + reescribir `tono_extra`.
2. Editar `current_turn.py`: reemplazar línea 695 con confirmación específica.
3. Reiniciar `api` y `worker`.
4. Validar con mensaje real que contenga años de experiencia — verificar que el confirm muestre el número y que el LLM no repita "nos interesa conocerle".

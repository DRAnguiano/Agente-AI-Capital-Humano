# Diseño: llm-first-extraction

## Secuencia de activación

Los tres contratos tienen dependencias. Se activan en orden:

```
B (independiente)          A y C (dependen de P1)
      │                           │
      ▼                           ▼
Eliminar                  Completar P1 batch
disambiguate_             (profile_extractor
numeric_units.py          migrado a LLM)
                                  │
                                  ▼
                          Eliminar _TYPO_CANON,
                          _PHRASE_CANON,
                          _NUM_WORDS duplicados
```

## Contrato B — Eliminar disambiguate_numeric_units.py

### Condición previa
P0 #2 completo: `current_turn.py` usa LLM para edad y experiencia.

### Verificación antes de eliminar
```bash
grep -rn "disambiguate_numeric_units\|from app.knowledge.disambiguate" app/ tests/
```
Si hay referencias activas en el pipeline de producción (no multi-intent Fase 3
que aún no está live), investigar antes de eliminar.

### Pasos
1. Confirmar que ningún caller activo en producción lo usa
2. Eliminar `app/knowledge/disambiguate_numeric_units.py`
3. Eliminar tests asociados si son unit tests del módulo (no de comportamiento)
4. Añadir nota en `docs/deuda_tecnica.md` indicando dónde fue absorbida la lógica

## Contrato A — normalize_text sin typo canon

### Condición previa
P1 batch completo: todos los extractores de texto crudo en `profile_extractor.py`
migrados a LLM.

### Decisión de diseño: ¿un normalize_text o dos?

**Opción 1** — Una sola función reducida:
- `normalize_text(text)` → solo estructural
- Simple, sin confusión de qué hace

**Opción 2** — Dos funciones:
- `normalize_text(text)` → solo estructural (para facts + catalog)
- `normalize_raw_candidate(text)` → estructural + typo canon (para cualquier regex legacy)

Se elige **Opción 1**: al completar P1 no hay callers que necesiten typo canon,
por lo que la segunda función nace muerta.

### Pasos
1. Eliminar `_TYPO_CANON` dict de `text_normalizer.py`
2. Eliminar `_PHRASE_CANON` tuple de `text_normalizer.py`
3. Eliminar el bloque de aplicación de ambos en `normalize_text()`
4. Ejecutar suite completa — cualquier test que dependa de la normalización de
   typos refleja una extracción que AÚN no migró a LLM; eso es un blocker a
   resolver primero

## Contrato C — _NUM_WORDS unificado

### Pasos (parte de P1, no independiente)
1. En `current_turn.py`: eliminar `_NUMBER_WORDS` dict y `_number_token_to_int()`
   (la única función que los usa, tras la migración LLM de P0 #2)
2. En `profile_extractor.py`: eliminar los mapas de palabras numéricas de los
   bloques de extracción que ya migraron a LLM
3. `fact_corrections.py._NUM_WORDS` — **conservar**, es el único uso legítimo

## Invariante de regresión

Antes de activar Contrato A, correr:
```bash
docker compose run --rm api-test python -m pytest -x -q
```
Si algún test falla por "sensillo" → "sencillo" o similar, ese test está
cubriendo un extractor que todavía usa regex sobre texto crudo y aún no migró.
Ese extractor debe migrar ANTES de activar el contrato.

## Age disqualification — diseño de la regla en persona_config

La descalificación por edad NO es ortografía, pero SÍ es una regla de negocio
que debe estar en persona_config, no hardcodeada.

### Threshold
```python
# app/settings.py
AGE_DISQUALIFICATION_LIMIT = _env_int("AGE_DISQUALIFICATION_LIMIT", 57)
```
Configurable vía env var. El valor 57 significa que 56 es la última edad válida.

### Generación del mensaje
```python
# app/knowledge/current_turn.py
def age_disqualification_reply(age: int | None = None) -> str:
    # Llama call_groq_with_system(SYSTEM_PROMPT, prompt)
    # El SYSTEM_PROMPT tiene la sección DESCALIFICACIÓN POR EDAD con las instrucciones
```

El LLM genera el mensaje siguiendo la voz de Mundo (persona_config), sin
hardcodear el texto de rechazo en código Python.

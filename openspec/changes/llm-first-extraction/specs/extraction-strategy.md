# Spec: estrategia de extracción de hechos de perfil

## Invariante principal

**El LLM T=0 es la única estrategia para extraer hechos del texto natural del
candidato.** Las capas deterministas solo operan sobre valores ya estructurados.

```
Mensaje candidato (texto crudo)
        │
        ├──► LLM T=0 extractors       ← fact group + fact key + value
        │    (current_turn, profile_extractor migrado)
        │
        ├──► strip_accents + lower     ← solo para catalog lookups
        │    (normalize_domain_values, fact_corrections)
        │
        └──► LLM generation (Mundo)   ← ve texto original, entiende typos
```

## Regla de normalize_text (Contrato A)

`normalize_text(text)` SOLO realiza:
1. Lowercase
2. Accent strip (unicodedata NFKD)
3. Punctuation → space (excepto guion y punto)
4. Whitespace compact

**NO realiza**: corrección de typos, corrección de frases, inferencia de
intención, expansión de abreviaciones.

**Condición de activación**: todos los callers que pasan texto crudo del
candidato a `normalize_text` para alimentar extractores regex han migrado a LLM.

### Callers actuales de normalize_text sobre texto crudo

| Caller | Migrado a LLM | Puede usar solo estructural |
|---|---|---|
| `current_turn.py` — extracción contextual | Sí (P0 #1 y #2) | Sí |
| `profile_extractor.py` — bloques regex | Pendiente (P1) | Tras P1 |
| `fact_corrections.py` — comparación de values | No aplica (values ya estructurados) | Ya |
| `normalize_domain_values.py` — catalog lookup | No aplica | Ya |
| `intent_classifier.py` — texto al LLM | LLM nativo | Ya |

## Regla de desambiguación numérica (Contrato B)

La desambiguación de un número aislado (edad vs. experiencia) se resuelve
por el **contexto de la última pregunta del bot** (`last_bot_message`), extraído
por el extractor LLM en `current_turn.py`.

`disambiguate_numeric_units.py` **no se activa en el pipeline de producción**.
Puede eliminarse tras completar P0 #2.

### Responsabilidad del extractor contextual

Cuando el bot preguntó por edad (`¿Cuántos años tiene?`):
- Extractor `_AGE_SYSTEM` recibe el mensaje, devuelve `{"age": <int>}`.
- Rango de extracción: 18–70 (sanity check de adulto).
- La regla de negocio (`AGE_DISQUALIFICATION_LIMIT`) se aplica DESPUÉS.

Cuando el bot preguntó por experiencia (`¿Cuántos años de experiencia tiene?`):
- Extractor `_EXPERIENCE_YEARS_SYSTEM` devuelve `{"years": "<N años>"}`.
- El LLM normaliza variantes: "diez" → "10 años", "año y medio" → "1 año".

## Regla de normalización numérica (Contrato C)

El mapa palabra→entero (un/uno→1, dos→2, …) tiene un único uso determinista
legítimo: **comparación de values en `fact_corrections.py`** para detectar si
"10 años" y "diez años" son el mismo fact.

Para extracción desde texto crudo, el LLM devuelve integers directamente.

### Instancias a eliminar tras P1

| Archivo | Variable | Estado |
|---|---|---|
| `current_turn.py` | `_NUMBER_WORDS` | Eliminar tras P0 #2 completo |
| `profile_extractor.py` | bloques `_NUM_WORDS` inline | Eliminar tras P1 |
| `fact_corrections.py` | `_NUM_WORDS` | CONSERVAR — comparación de facts |

## Regla de typos del candidato

Los operadores escriben con faltas documentadas ("licensia", "vijente",
"sensillo"). **El LLM extractor los entiende nativamente.** No se necesita
un preprocesador de typos para la extracción de hechos.

`_TYPO_CANON` y `_PHRASE_CANON` en `text_normalizer.py` se eliminan al
activar el Contrato A, tras completar P1.

### Excepción justificada

Si en el futuro algún catalog lookup determinista (e.g., alias de ciudad) falla
con typos documentados y el costo de un LLM call es desproporcionado, se puede
añadir entradas al catálogo de alias, NO al preprocesador de texto.

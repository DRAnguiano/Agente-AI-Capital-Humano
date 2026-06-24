# Propuesta: llm-first-extraction

## Problema

El nodo de conocimiento (`app/knowledge/`) mezcla dos estrategias de extracción
de hechos del lenguaje natural del candidato:

1. **Regex + normalización ortográfica** — `profile_extractor.py`, bloques en
   `current_turn.py`. Requieren un preprocesador de typos (`_TYPO_CANON`,
   `_PHRASE_CANON` en `text_normalizer.py`) para compensar faltas de ortografía
   que el propio LLM ya entiende nativamente.

2. **LLM T=0** — `intent_classifier.py`, `business_route_classifier.py`, y los
   bloques de extracción migrados en esta sesión (`_contextual_expiration_text`,
   edad/experiencia elíptica).

Esta mezcla produce tres problemas concretos:

- El preprocesador modifica el mensaje ANTES de que el LLM lo vea: bugs como
  C4 (regex captura "a" de "aprender a manejar") son más difíciles de
  diagnosticar porque el texto original ya fue transformado.
- `disambiguate_numeric_units.py` duplica la lógica de desambiguación
  contextual ya implementada vía LLM en `current_turn.py`.
- El mapa `_NUM_WORDS` (palabra → entero) existe en tres archivos independientes.

## Objetivo

Establecer LLM T=0 como estrategia única para extraer hechos de perfil del texto
natural del candidato. Las capas deterministas solo operan sobre valores ya
estructurados (catalog lookups, comparación de facts, lógica de ciclo de vida).

## Cambios

### Contrato A — `normalize_text` solo normalización estructural

Eliminar `_TYPO_CANON` y `_PHRASE_CANON` de `text_normalizer.py` una vez que
todos los extractores de texto-crudo migren a LLM (P1 batch en `profile_extractor`).
`normalize_text` pasa a ser: lowercase + accent strip + punctuation clean +
whitespace compact. Sin corrección de typos.

### Contrato B — Retirar `disambiguate_numeric_units.py`

La desambiguación de números (edad vs. experiencia) está resuelta por el contexto
LLM en `current_turn.py`. El módulo `disambiguate_numeric_units.py` no se
incorpora al pipeline activo de la Fase 3; se depreca y elimina.

### Contrato C — `_NUM_WORDS` unificado

El único lugar donde se necesita conversión palabra→entero de forma determinista
es `fact_corrections.py` (comparación de valores para detectar conflictos). Se
eliminan los mapas duplicados en `current_turn.py` y `profile_extractor.py`
cuando las extracciones que los usan hayan migrado a LLM.

## Fuera de scope

- `normalize_domain_values.py` / `domain_catalog.py` — catálogo de dominio
  legítimo, no ortografía.
- `fact_corrections.py` — ciclo de vida de facts, puro y bien diseñado.
- `reply_cleaner.py` — limpia output del LLM, necesario.
- `memory_guard.py` — lógica de control de flujo, no extracción de hechos.

## Dependencias

Este change depende de que el P1 batch de `profile_extractor.py` esté completo
(extracción de ciudad, experiencia, vigencia, cartas laborales migrada a LLM).
Los contratos A y C son condicionados a ese milestone. El Contrato B es
independiente y puede ejecutarse antes.

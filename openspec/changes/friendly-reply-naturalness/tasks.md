## 1. Eliminar variante formal del funnel de experiencia

- [x] 1.1 En `app/orchestrators/knowledge_orchestrator.py`, dentro de `_FUNNEL_STEPS`, en el step `experience.years`, eliminar la variante `"Para su perfil, ¿cuántos años lleva manejando de manera profesional?"` (dejar solo las otras dos variantes)

## 2. Corregir confirmación de experiencia en current_turn

- [x] 2.1 En `app/knowledge/current_turn.py` línea ~695, reemplazar `"Esa experiencia es valiosa. Con ese perfil nos interesa conocerle."` por una confirmación que incluya el número de años si está disponible. Usar `current.get("experience.years")` para construir `f"{years} años de experiencia, anotado."` con fallback `"Experiencia anotada."` si el valor no está disponible

## 3. Reescribir tono_extra del prompt amistoso

- [x] 3.1 En `app/orchestrators/knowledge_orchestrator.py`, en `_answer_friendly_message`, reescribir la rama `strong` de `tono_extra`: eliminar las frases de ejemplo literales (`'Con ese perfil nos interesa conocerle'`, `'Va por buen camino'`) y reemplazar por instrucción de tono sin citas concretas

## 4. Eliminar "nuestro equipo lo contactará" del prompt RAG cuando perfil incompleto

- [x] 4.1 En `app/knowledge/context_builder.py`, reescribir la instrucción 9 del prompt RAG: eliminar la indicación de decir "nuestro equipo lo contactará" durante horario de atención. Reemplazar por: en horario de atención, el RAG solo informa — no hace promesas de contacto porque eso corresponde al sistema cuando el perfil esté completo

## 5. Deploy y validación

- [x] 5.1 Reiniciar `api` y `worker` con `docker compose restart api worker`
- [x] 5.2 Enviar mensaje con años de experiencia y verificar que el confirm muestra el número sin "nos interesa conocerle"
- [x] 5.3 Verificar en conversación real que "Con ese perfil nos interesa conocerle" no aparece más de una vez (idealmente cero en perfilamiento)

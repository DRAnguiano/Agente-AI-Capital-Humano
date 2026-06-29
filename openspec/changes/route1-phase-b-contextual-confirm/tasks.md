## 1. Agregar ROUTE1_ACK en route1_contextual.py

- [x] 1.1 En `app/knowledge/route1_contextual.py`, agregar dict `ROUTE1_ACK: dict[str, str]` con los ack strings por campo:
  - `"documents.proof"` → `"Cartas anotadas."`
  - `"experience.years"` → `"{value} años de experiencia, anotado."`
  - `"experience.vehicle_type"` → `"Entendido, {value}."`
  - fallback (no en dict) → `"Entendido."`

## 2. Mover resolve_route1 antes del funnel nudge en handle_message

- [x] 2.1 En `app/orchestrators/knowledge_orchestrator.py`, leer `fresh_keys` antes de `_build_funnel_nudge` (actualmente se lee después). Extraer la lectura de `read_current_asked_field_keys(lead_key)` al bloque previo al nudge.

- [x] 2.2 Llamar `resolve_route1(message, fresh_keys)` antes de `_build_funnel_nudge`. Si `r1["status"] == "confirmed"`:
  - Construir `route1_extra = [{"fact_group": field_group, "fact_key": field_key, "fact_value": str(value)}]` a partir de `r1["field"]` (splitear por `.`) y `r1["value"]`.
  - Mezclar `route1_extra` con `_pre_validated` (o usar como `_pre_validated` si era None) antes de pasar a `_build_funnel_nudge`.

## 3. Suprimir friendly_result y usar ack cuando route-1 confirma

- [x] 3.1 Si `r1["status"] == "confirmed"`, construir el ack string usando `ROUTE1_ACK`:
  - Importar `ROUTE1_ACK` desde `route1_contextual`.
  - `ack_text = ROUTE1_ACK.get(r1["field"], "Entendido.").format(value=r1.get("value", ""))`.
  - Anular `friendly_result` (setear a None) para que no genere el comentario amistoso del LLM.
  - Usar `ack_text` como prefijo del reply en lugar del friendly_result.

- [x] 3.2 Asegurar que el reply final sea `f"{ack_text}\n\n{nudge}"` si hay nudge, o solo `ack_text` si el perfil está completo.

## 4. Actualizar log de ROUTE1_SHADOW → ROUTE1_ACTIVE cuando actúa

- [x] 4.1 Cambiar el label del log de `[ROUTE1_SHADOW]` a `[ROUTE1_ACTIVE]` cuando `r1["status"] == "confirmed"` y la inyección se ejecutó. Mantener `[ROUTE1_SHADOW]` cuando solo se loguea sin actuar (campos fuera del allowlist, no_persist, etc.).

## 5. Deploy y validación

- [ ] 5.1 Reiniciar `api` y `worker` con `docker compose restart api worker`
- [ ] 5.2 Enviar mensaje de prueba: preguntar una conversación donde el bot pregunte cartas y el candidato responda "Es correcto señor" — verificar que NO repite la pregunta y responde con ack + siguiente campo
- [ ] 5.3 Verificar en log que aparece `[ROUTE1_ACTIVE]` en lugar de `[ROUTE1_SHADOW]` para ese turno

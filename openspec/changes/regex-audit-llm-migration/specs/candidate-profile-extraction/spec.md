# Spec: candidate-profile-extraction (delta)

## MODIFIED Requirements

### R-renewal-proof — Polaridad de documento de renovación

**Antes**: `_has_renewal_proof()` usa dos regex (`r"\b(?:no|todavia no|aun no|sin)\b"`, `r"\b(?:si|sí|ya|tengo|cuento)\b"`) para inferir si el candidato tiene o no comprobante de trámite de renovación.

**Después**: migrar a LLM T=0 con guardia `("papel", "comprobante", "pago", "cita", "tramite", "tramit")`.
- Prompt devuelve `{"renewal_proof": "si" | "no" | null}`
- `null` = no hay mención de comprobante → mismo comportamiento que hoy (no se registra fact)
- La guardia de contexto (keyword hints) se mantiene antes del LLM call para no llamar en cada turno

### R-call-request — Detección de solicitud de llamada

**Antes**: `_CALL_REQUEST_RE` es una alternación de ~15 frases que detecta "me llamen", "quiero llamada", "que me hablen", etc.

**Después**: LLM T=0 con guardia `("llamen", "llamada", "llame", "hablen", "hablar", "contacten", "marcar")`.
- Prompt devuelve `{"call_requested": true | false, "call_window": "<texto>" | null}`
- Si `call_requested = true`, se registra `scheduling.call_requested = "true"`
- Si `call_window` no es null, se registra `scheduling.call_window_text`
- Unifica `_CALL_REQUEST_RE` y `_CALL_NEG_RE` en un solo clasificador

### R-no-road-experience — Declaración explícita de sin experiencia

**Nota**: Este extractor YA existe en `profile_extractor.py` como `_NO_ROAD_EXP_SYSTEM` (LLM T=0). El equivalente regex en `knowledge_orchestrator.py` (`_NO_ROAD_EXPERIENCE_RE`) es un duplicado.

**Acción**: eliminar `_NO_ROAD_EXPERIENCE_RE` en `knowledge_orchestrator.py` y delegar a `profile_extractor.extract_profile_facts_as_dict()` que ya lo cubre.

## Non-Goals de este delta

- `_PAID_SENSITIVE_RE` en `knowledge_orchestrator.py` (fraude/pagos sospechosos): **NO migrar**. Es una guardia de seguridad donde el costo de un falso negativo es mayor que un LLM call de verificación. Se puede añadir LLM como segunda capa en una fase posterior.

## Archivos afectados

- `app/lead_memory/profile_extractor.py` — `_has_renewal_proof()`, `_CALL_REQUEST_RE`, `_CALL_NEG_RE`
- `app/orchestrators/knowledge_orchestrator.py` — eliminar `_NO_ROAD_EXPERIENCE_RE` (redundante)

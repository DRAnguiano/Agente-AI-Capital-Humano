# Spec: llm-intent-classifiers

Clasificadores LLM T=0 para señales de intención y polaridad que hoy se detectan con regex en `current_turn.py` y `memory_guard.py`.

## Requisitos

### R1 — "ya" reclamo vs confirmación
- **Señal de activación**: token `"ya"` al inicio del mensaje normalizado
- **Clasificador**: devuelve `{"is_complaint": true | false}`
- **true**: "ya te lo dije", "ya le había mandado", "ya lo había dicho" (el candidato refuta o exige)
- **false**: "ya lo tengo", "ya conseguí", "ya está vigente" (el candidato confirma)
- **Contrato**: si `is_complaint = true`, NO se infiere ningún fact de confirmación desde ese turno

### R2 — Reclamo de memoria pasada
- **Señal de activación**: presencia de términos como "ya te", "ya le", "habia dicho", "ya mande", "ya envie"
- **Clasificador**: devuelve `{"is_memory_claim": true | false}`
- **true**: el candidato afirma haber dado información previamente ("ya te había mandado las cartas")
- **false**: cualquier otro caso
- **Contrato**: si `is_memory_claim = true`, el orquestador prioriza lead_memory sobre extracción del turno actual

### R3 — Guard `_conditional_si` (EXCEPCIÓN: permanece regex)
- El patrón `r"^si\s+(?:me|te|le|...)\s+(?:cuenta|cuentas|...)\b"` es un guard de baja latencia en el hot path
- **NO se migra a LLM** en esta fase (ver D2 en design.md)
- Si aparecen falsos positivos en producción documentados, se revisita

## Contratos de test

- Cada clasificador tiene test con `@pytest.mark.skipif(_NO_GROQ, reason="requiere GROQ_API_KEY")`
- Los tests asertan el **hecho de negocio** (fact generado o suprimido), no el literal del mensaje
- Los mensajes de prueba son ejemplos representativos, no el contrato

## Archivos afectados

- `app/knowledge/current_turn.py` — reemplazar `_ya_reclamo` regex (línea ~257)
- `app/knowledge/memory_guard.py` — reemplazar `_MEMORY_CLAIM_PATTERNS` (6 patrones, líneas 50–55)

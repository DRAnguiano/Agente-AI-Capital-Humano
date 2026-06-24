## Why

Un smoke real (S1) sobre el camino vivo (debounce ON: `current_turn` guard + LLM friendly +
RAG + `profile_extractor`, no la capa canónica en migración) expuso fallas conversacionales
que hoy no están capturadas como contrato:

- **Alucinación factual**: el comentario friendly introdujo "4 años" que el candidato nunca
  dijo (eco de un few-shot del propio prompt).
- **Fuga de instrucciones internas**: una respuesta de pago expuso reglas operativas
  ("Mundo debe pedir... antes de dar una cifra") que viven en el archivo de conocimiento.
- **Mezcla de temas no relacionados** en una respuesta de RAG (pago + paradas + proceso).
- **Error de dominio**: `sencillo` se convirtió automáticamente en `escuelita`, contra el
  esquema de perfilamiento.
- **Edad falsa**: "20 años de fullero" se extrajo como `candidate.age=20`.
- **Ack con duplicaciones**: "Perfecto" repetido y "20 años, 20 años de experiencia".
- **Correcciones ignoradas**: el candidato corrige y el sistema repite el valor anterior.
- **Falta de política** de perfil listo / agendar llamada / horario de oficina.
- **Sin disclaimer de OCR** al declarar documentos.

Queremos capturar estas fallas como requirements y tasks verificables **antes de tocar
código**, para que la deuda quede versionada (no como nota conversacional) y se corrija en
bloques pequeños.

## What Changes

- **Grounding del comentario conversacional**: el modo friendly no introduce números, años,
  experiencia, ciudad, licencia, apto, documentos ni condiciones que el candidato no dijo.
- **Sin fuga de instrucciones internas**: la respuesta es de cara al candidato; no expone
  reglas tipo "Mundo debe...".
- **Higiene de fuentes de conocimiento** (capability nueva): separar contenido respondible de
  notas internas; el RAG no devuelve ni mezcla texto interno como respuesta.
- **Respuesta enfocada**: ante una pregunta específica, no se mezclan temas no relacionados.
- **Dominio de unidad**: `sencillo` (rígido 2 ejes) = experiencia válida, nunca escuelita;
  `full` = tractocamión con doble remolque/dolly; `torton`/`rabón`/reparto local/servicio
  interurbano = experiencias de carga que pueden derivar a `escuelita`/CECATI, no `full` ni
  `sencillo` ni "transferencia hacia quinta rueda".
- **Edad ≠ años de experiencia** en el extractor.
- **Ack sin duplicaciones**: un solo prefijo de confirmación, sin facts repetidos.
- **Correcciones explícitas**: reconocer la corrección y no repetir el valor anterior
  (cross-reference a tasks de `multi-intent-migration`, sin duplicar).
- **Perfil listo y llamada**: siguiente paso claro + política de horario **8:00–17:30, lunes a
  viernes** (`America/Mexico_City`) + estado/label de lead; sin prometer agenda real inexistente.
- **Sin OCR**: registrar documentos para revisión humana sin afirmar validación automática.
- **Datos sensibles**: el bot no solicita pagos, depósitos, cuentas, CURP/NSS completos ni
  comprobantes fuera de flujo autorizado; ante trámites con costo → handoff / canal autorizado.
- **Decisión operativa unificada**: respuesta visible, nota interna y labels derivan de la misma
  decisión por turno (perfil, intención, horario, llamada, humano, bloqueo) sin contradecirse.
- **Labels oficiales**: solo se emiten labels del catálogo de `chatwoot-label-taxonomy`; nada de
  labels fantasma (p. ej. `falta_cartas` → usar `documentos`). `llamada_pendiente` ya existe
  en el catálogo; falta el flujo determinista `call_scheduling` para emitirla y guardar
  `scheduling.call_window_*`.

Cambio **doc-only**: define el contrato esperado; la adaptación del flujo vivo se hace en
bloques posteriores (ver `tasks.md`).

## Capabilities

### New Capabilities
- `knowledge-source-hygiene`: separación de contenido respondible al candidato vs notas
  internas/políticas operativas en las fuentes de conocimiento, y recuperación/ensamblado de
  RAG enfocado, sin devolver instrucciones internas ni decidir facts del candidato.

### Modified Capabilities
- `message-orchestration`: grounding del comentario conversacional, no fuga de instrucciones
  internas, respuesta enfocada, ack sin duplicaciones, reconocimiento de correcciones, cierre
  de perfil + política de llamada, y registro de documentos sin OCR.
- `profile-extraction`: la edad no se infiere de años de experiencia; dominio correcto de
  unidad (sencillo = rígido 2 ejes, válido, ≠ escuelita; full = doble remolque/dolly;
  torton/rabón/reparto/interurbano → pueden derivar a escuelita/CECATI, ≠ full, ≠ sencillo).
- `chatwoot-label-taxonomy`: labels de perfil listo/seguimiento/llamada derivados de la misma
  decisión operativa; prohibición de labels fantasma (alineación con el catálogo oficial).

## Impact

- **Camino vivo afectado (implementación futura, no en este cambio doc-only):**
  `app/orchestrators/knowledge_orchestrator.py` (`_answer_friendly_message` few-shot/guard,
  `_answer_rag_message`), `app/knowledge/current_turn.py` (`build_current_turn_ack`,
  `next_question_from_missing_facts`, escuelita), `app/lead_memory/profile_extractor.py`
  (edad, dominio), `app/chatwoot_note_sync.py` (escuelita), `app/knowledge/context_builder.py`
  (RAG grounding).
- **Fuentes de conocimiento:** `data/00_*.md`..`data/05_*.md` (separar instrucción interna).
- **Cross-reference (no duplicar):** `multi-intent-migration` tasks de corrección (6.3, 7.2,
  7.4, 9.3.3, 9.3.11) y FUTURO `call_scheduling`/`llamada_pendiente`; `followup-scheduler`
  (ventana horaria); `chatwoot-label-taxonomy` (estado/label de lead).
- **Fuera de alcance:** promover route1 a productivo (sigue shadow); OCR/document-understanding.

# Arquitectura activa del agente RH

Estado objetivo para la demo y siguientes cambios.

## Camino activo

```text
Chatwoot / Telegram / WhatsApp
  -> FastAPI app.py
  -> app.graphs.hr_graph.run_hr_graph_message
  -> HR_GRAPH_MODE=knowledge
  -> app.orchestrators.knowledge_orchestrator.handle_message
  -> app.knowledge
  -> app.lead_memory best effort
  -> Chatwoot note sync
```

## Regla de prioridad

```text
mensaje actual > facts de memoria > Neo4j Knowledge Graph > RAG / ChromaDB > LLM
```

El mensaje actual siempre tiene prioridad para datos explícitos del candidato. Ejemplo: si el candidato dice `todo vigente y tengo cartas laborales`, el bot no debe responder como si los documentos no estuvieran vigentes.

## Responsabilidades

### app/knowledge

Diccionario, normalización, Neo4j, schema controlado, contexto RAG compacto.

No debe guardar memoria operativa por sí mismo.

### app/orchestrators/knowledge_orchestrator.py

Cerebro activo en `HR_GRAPH_MODE=knowledge`.

Debe decidir la ruta pública de respuesta con contrato limpio. Debe evitar que RAG o memoria vieja pisen el mensaje actual.

### app/lead_memory

Persistencia operativa v2.

Solo registra identidad, mensajes, facts, eventos y resumen. No decide respuestas.

### app/graphs/hr_graph.py

Entry point de compatibilidad usado por `app.py`.

Si `HR_GRAPH_MODE=knowledge`, llama al knowledge orchestrator. Si no, puede caer al legacy para compatibilidad.

### app/orchestrator.py

Legacy. No debe ser el camino principal de nuevas decisiones. Se conserva como respaldo temporal.

## Reglas para evitar Frankenstein

1. No conectar nuevos features directamente a `app/orchestrator.py`.
2. No meter prompts largos de memoria al LLM sin estructura.
3. No usar RAG para decidir facts del candidato.
4. No usar la nota de Chatwoot como fuente de verdad.
5. No duplicar lógica de extracción entre 4 archivos. Si es determinística, va en `app/knowledge/current_turn.py` o `app/lead_memory/profile_extractor.py`.
6. No responder directo desde Telegram saltándose Chatwoot en demo operativa.

## Pendientes controlados

- Migrar gradualmente nodos grandes de `app/graphs/hr_nodes_*` solo si aportan al camino knowledge.
- Eliminar o aislar imports legacy cuando el modo knowledge sea estable.
- Agregar job de abandono: activo, seguimiento, posible abandono, abandonado.
- Convertir Neo4j events a tablas planas para Power BI si el conector Neo4j no conviene.

# Esquema de Perfilamiento v1

> Fuente única de verdad para el perfilamiento de leads del agente de reclutamiento
> (operadores de quinta rueda — sencillo y full). Define qué pregunta el bot, en qué
> orden, cómo se valida, y qué estados produce. Base para el sistema multi-intent.
>
> Acordado el 2026-06-03. Reemplaza la lógica dispersa en `_FUNNEL_STEPS`
> (orchestrator), `next_question_from_missing_facts` (current_turn) y los 17 datos
> del `SYSTEM_PROMPT`.

---

## 1. Flujo de las 6 preguntas del núcleo (una por turno)

| # | Campo | Pregunta canónica | Completo cuando |
|---|---|---|---|
| 1 | `candidate.city` | "¿Desde qué ciudad o estado nos escribe?" | ciudad reconocida |
| 2 | `experience.vehicle_type` | "¿Ha manejado sencillo, full o ambos?" | tipo válido |
| 3 | `license` (tipo + status) | "¿Qué tipo de licencia federal tiene y está vigente?" | tipo + vigente |
| 4 | `medical.apto_status` | "¿Su apto médico está vigente?" | vigente |
| 5 | `experience.years` | "¿Cuántos años tiene manejando?" | número |
| 6 | `documents.proof` | "¿Cuenta con 2 cartas laborales o su documento de semanas cotizadas del IMSS?" | cartas **o** semanas IMSS |

**Por qué unidad (2) antes que licencia (3):** saber sencillo/full define qué licencia
esperar (B/E) y permite validar la licencia sobre la marcha en el mismo turno.

---

## 2. Reglas de validación (van en el grafo Neo4j, no en el LLM)

```
full      → requiere licencia E
sencillo  → licencia B o E      (la licencia es progresiva: E habilita ambas)

INCONSISTENCIA = full + licencia B   (la B no habilita full)
trámite / vencido = campo INCOMPLETO (no completa el núcleo)
```

**Manejo de inconsistencia licencia↔unidad (sobre la marcha):**
1. El bot aclara suave **una sola vez**:
   *"Para full normalmente se necesita licencia tipo E, ¿me confirma cuál tiene?"*
2. Si el candidato insiste o confirma → registra `full + B` con label
   `revisar_licencia` y continúa al apto médico. No vuelve a insistir.

---

## 3. Estados especiales (no son completitud de campos)

| Disparador | Acción |
|---|---|
| Ciudad foránea | label `validar_traslado` (el proceso se hace en Torreón) |
| Nunca ha manejado vehículo de carga | `candidato_escuelita` → referir a CECATI Gómez Palacio |
| Inconsistencia licencia↔unidad | label `revisar_licencia` |
| Documento en trámite o vencido | campo incompleto + seguimiento "avísenos cuando lo tenga vigente" |
| Sustancias / antidoping | `human_handoff` inmediato |
| Reingreso (ya trabajó en la empresa) | `human_handoff` inmediato |
| Documento dudoso o falso | `human_handoff` inmediato |
| Candidato molesto / riesgo de fuga | `human_handoff` inmediato |
| Pregunta fuera de dominio (otra vacante o tema ajeno a operador full/sencillo) | `human_handoff` inmediato |

**Nota:** "sencillo" es una vacante válida (no es escuelita). La escuelita/CECATI
es **solo** para quien no sabe manejar o nunca ha manejado un vehículo de carga.

---

## 4. Status del lead en Chatwoot (por completitud del núcleo)

```
0-2 campos completos  →  nuevo
3-5 campos completos  →  en_proceso
6/6 campos completos  →  perfil_listo
```

Las labels de estados especiales (sección 3) se superponen al status base.
El mapeo exacto campo→label se define en el documento del Paso 2.

---

## 5. Datos fuera del bot (los recolecta el reclutador humano en llamada)

El bot **nunca** pide por WhatsApp:

- Retención Infonavit / Fonacot
- Estado civil / pensión alimenticia
- Expectativa económica / sueldo anterior
- Última empresa / motivo de salida / referencias laborales

Estos se recolectan en la llamada de reclutamiento, no por chat.

---

## 6. Comportamiento transversal

- **Ritmo:** una sola pregunta por turno. Nunca interrogatorio.
- **Multi-intent:** cuando un mensaje trae respuesta + pregunta
  (ej. "sí me interesa, pero ¿cuánto pagan?"), el bot detecta ambas,
  **registra el answer en silencio** y **prioriza contestar la pregunta**.
  Orden de acciones: `[persist_answer_silently, answer_question]`.
- **Voz de equipo:** "nuestro equipo", "llámenos de 8:00 a 17:30 hrs".
  Nunca "Capital Humano" como tercero externo.
- **El LLM no pregunta** datos de perfil: las preguntas del funnel las
  emite el sistema. El LLM solo informa, comenta o anima.

---

## 7. Mapeo a Chatwoot (Paso 2)

### Status base — mutuamente excluyente (una sola activa)

| Label | Cuándo |
|---|---|
| `lead_nuevo` | 0-2 campos núcleo completos |
| `lead_en_proceso` | 3-5 campos núcleo |
| `perfil_listo` | 6/6 campos núcleo (NO exige señal de interés explícita) |

### Tipo de operador — mutuamente excluyente

| Label | Cuándo |
|---|---|
| `operador_sencillo` | maneja solo sencillo |
| `operador_full` | maneja solo full |
| `operador_ambos` | maneja sencillo y full |

### Labels superpuestas (coexisten con status y tipo)

| Label | Cuándo |
|---|---|
| `foraneo` + `validar_traslado` | ciudad fuera de la Laguna |
| `revisar_licencia` | inconsistencia full + licencia B |
| `candidato_escuelita` | nunca ha manejado vehículo de carga |
| `seguimiento` | va en ruta / promete enviar documentos |
| `requiere_agente` + `requiere_revision_ch` | handoff (sustancias, reingreso, doc dudoso, molesto, fuera de dominio) |
| `riesgo_alto` | risk_level = high |
| `bot_activo` | siempre (base) |

### Labels de campo faltante (mientras el campo esté incompleto)

`falta_experiencia` · `falta_licencia` · `falta_apto` · `falta_cartas`
(ciudad y años no llevan label propia — se ven en status y nota interna)

### Labels eliminadas (vigencia simplificada a vigente/no-vigente)

```
✗ apto_por_vencer     ✗ apto_por_vencer_urgente
✗ licencia_por_vencer ✗ licencia_por_vencer_urgente
```
Ahora: vigente → completa el campo · vencido/trámite → `falta_apto` / `falta_licencia`.

### Cambio respecto al sistema actual

`perfil_listo` ya NO exige `vacancy_accepted`. Los 6 campos núcleo bastan —
responderlos ya implica interés.

### Ejemplo de transición de labels

```
"soy de Monterrey"        → 1/6 → lead_nuevo · foraneo · validar_traslado
"manejo full"             → 2/6 → lead_nuevo · operador_full · foraneo · validar_traslado
"licencia tipo E vigente" → 3/6 → lead_en_proceso · operador_full · foraneo · validar_traslado
"mi apto está vigente"    → 4/6 → lead_en_proceso · operador_full · foraneo · validar_traslado
"4 años manejando"        → 5/6 → lead_en_proceso · operador_full · foraneo · validar_traslado
"tengo 2 cartas"          → 6/6 → perfil_listo · operador_full · foraneo · validar_traslado
```

---

## 8. Contrato de intención multi-intent (Paso 3)

### División de responsabilidades

- **El LLM** llena lo que entiende del lenguaje: `message_type`, `primary_intent`,
  `secondary_intents`, `answers[]`, `questions[].intent` + `evidence` + `confidence`.
- **El grafo Neo4j** enriquece las políticas de cada `question.intent`:
  `requires_rag`, `requires_human`, `risk_level`, `policies`, `preferred_sources`.
  El LLM NUNCA decide políticas (consistencia de reglas de negocio).

### Esquema del JSON (salida del clasificador LLM)

```jsonc
{
  "message_type": "compound",            // simple | compound
  "primary_intent": "candidate_answer",
  "secondary_intents": ["salary_question"],
  "answers": [
    {
      "field": "experience.vehicle_type",
      "value": "full",
      "evidence": "manejo full",         // debe estar LITERAL en el mensaje
      "confidence": 0.93
    }
  ],
  "questions": [
    { "intent": "salary_question", "evidence": "cuánto pagan" }
  ]
}
```

### Flujo de procesamiento — DOS llamadas al LLM

```
1. LLM clasifica           → JSON (intents, answers, questions)
2. Validar answers         → persiste si: evidence ∈ mensaje  Y  confidence ≥ 0.85
                             (persistencia silenciosa, sin verbalizar)
3. Grafo enriquece         → cada question.intent → routing + políticas
4. Orden de acción         → [persist_answers, answer_primary_question]
5. LLM genera respuesta    → responde primary_question (RAG/grafo según routing)
                             si NO hay question → emite siguiente pregunta del funnel
6. Registrar               → response_log: { channel: public | private_note }
```

### Reglas del contrato

- **Guardrail anti-alucinación:** un `answer` se persiste solo si su `evidence`
  aparece literal en el mensaje **y** `confidence ≥ 0.85`. Si no, se descarta.
- **Multi-pregunta:** si hay varias `questions`, el bot contesta la `primary_intent`
  y ofrece brevemente la otra ("sobre rutas también le platico si gusta").
- **Persistencia silenciosa:** los `answers` se guardan sin acusar recibo verboso.
- **Registro:** cada respuesta guarda el canal usado (público WhatsApp / nota privada).

### Catálogo de intents (validado)

**ANSWER** (→ `answers[]`, actualizan el perfil):
- `candidate_answer` con `field` ∈ {candidate.city, experience.vehicle_type,
  license, medical.apto_status, experience.years, documents.proof}

**QUESTION** (→ `questions[]`, el grafo decide el routing):
| intent | cubre | doc fuente | routing |
|---|---|---|---|
| `pay_question` | sueldo, km, prestaciones, IMSS, viáticos, bono | 01 | RAG |
| `logistics_question` | rutas, bases, patios, descansos, rol, traslado foráneo, llegada al proceso | 04 | RAG |
| `documents_question` | requisitos, documentos, licencia, apto, cartas | 02 | RAG |
| `vacancy_question` | "¿qué vacantes hay?" → presenta operador sencillo/full | 00 | RAG |
| `safety_intent` | antidoping, sustancias, pruebas | 03 | ver flag ↓ |

`safety_intent` lleva flag `is_admission`:
```
is_admission: false  (pregunta: "¿hacen antidoping?")   → RAG
is_admission: true   (admite: "salí positivo / consumo") → human_handoff
```

**SIGNAL** (→ acciones, sin RAG):
- `greeting` · `farewell` · `on_route` (va manejando) · `dropoff` · `acknowledgement`
- `candidate_interest` ("me interesa") → continúa el funnel
- `document_submission` ("ya mandé mis cartas") → acuse preliminar + seguimiento
- `meta_confusion` ("¿qué me preguntaste?", "no entendí") → reformula/resume

**RISK / HANDOFF** (el grafo → human_handoff):
- `reingreso` · `out_of_scope` · `complaint`
- (`safety_intent` con `is_admission: true` también)

### Nota sobre jerga ambigua (cachimba, etc.)

No se creó un intent `clarification` propio. La jerga ambigua se resuelve por el
intent temático que corresponda + el doc 05 (jerga) vía RAG. Si el LLM no logra
clasificar con confianza, cae en `meta_confusion` (pide aclarar) en lugar de asumir.

---

## 9. Pendiente (implementación)

- Validar el catálogo de intents (sección 8).
- Definir el prompt del clasificador LLM (llamada 1) con few-shot de mensajes
  compuestos reales de WhatsApp.
- Implementar la capa de validación de `evidence` + umbral.
- Reposicionar Neo4j: de clasificador a motor de políticas (enriquecer questions).
- Migrar las 3 fuentes dispersas de preguntas del funnel a este esquema único.

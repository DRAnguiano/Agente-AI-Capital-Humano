## ADDED Requirements

### Requirement: El clasificador separa intent conversacional de ruta de negocio

El sistema SHALL mantener el intent conversacional (`primary_intent`, `secondary_intents`)
separado de las señales de ruta de negocio (`business_signals`). El LLM clasifica lenguaje;
el catálogo de dominio y las reglas deterministas clasifican la ruta de negocio. Un mismo
mensaje puede tener `primary_intent = candidate_interest` y señal `objetivo_full_sencillo`
simultáneamente.

#### Scenario: "Me interesa para sencillo" produce señal de negocio correcta
- **GIVEN** el candidato dice "Me interesa para sencillo"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `primary_intent` PUEDE ser `candidate_interest`
- **AND** `explicit_facts["experience.vehicle_type"].value = sencillo`
- **AND** `business_signals` contiene `objetivo_full_sencillo`
- **AND** `ambiguity_flags` está vacío

#### Scenario: El intent solo no activa la señal sin el hecho
- **GIVEN** el candidato dice "me interesa la vacante" sin mencionar tipo de unidad
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` NO contiene `objetivo_full_sencillo` como señal confirmada
- **AND** no se emite `explicit_facts["experience.vehicle_type"]`

### Requirement: Extracción explícita de vehicle_type solo cuando es literal

El sistema SHALL extraer `experience.vehicle_type` solo cuando `full` o `sencillo` aparecen
de forma explícita (o sus variantes del catálogo: `fulero`, `tracto full`, etc.).
SHALL NOT inferir vehicle_type desde contexto ni desde jerga ambigua.

#### Scenario: "manejo sencillo" → vehicle_type=sencillo
- **GIVEN** el candidato dice "manejo sencillo"
- **WHEN** el shadow classifier extrae hechos
- **THEN** `explicit_facts["experience.vehicle_type"].value = sencillo`
- **AND** `explicit_facts["experience.vehicle_type"].evidence` contiene `sencillo`

#### Scenario: "tracto sencillo" → vehicle_type=sencillo
- **GIVEN** el candidato dice "tengo experiencia en tracto sencillo"
- **WHEN** el shadow classifier extrae hechos
- **THEN** `explicit_facts["experience.vehicle_type"].value = sencillo`

#### Scenario: "manejo full" → vehicle_type=full
- **GIVEN** el candidato dice "manejo full"
- **WHEN** el shadow classifier extrae hechos
- **THEN** `explicit_facts["experience.vehicle_type"].value = full`

#### Scenario: "fullero" → vehicle_type=full
- **GIVEN** el candidato dice "soy fullero"
- **WHEN** el shadow classifier extrae hechos
- **THEN** `explicit_facts["experience.vehicle_type"].value = full`

### Requirement: Jerga ambigua de quinta rueda NO produce vehicle_type

El sistema SHALL NOT inferir `full` ni `sencillo` a partir de jerga de quinta rueda o
tractocamión genérico. Debe emitir `ambiguity_flags` y señal `jerga_ambigua_falta_unidad`
para que el funnel pregunte explícitamente.

#### Scenario: "operador de 5ta rueda" → jerga ambigua
- **GIVEN** el candidato dice "Soy operador de 5ta rueda"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** NO se emite `explicit_facts["experience.vehicle_type"]`
- **AND** `ambiguity_flags` contiene `vehicle_type_ambiguous`
- **AND** `business_signals` contiene `jerga_ambigua_falta_unidad`

#### Scenario: "tráiler" → jerga ambigua
- **GIVEN** el candidato dice "manejo tráiler"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** NO se emite `vehicle_type` como confirmado
- **AND** `ambiguity_flags` contiene `vehicle_type_ambiguous`

#### Scenario: "trailero" → jerga ambigua (substring de trailer)
- **GIVEN** el candidato dice "soy trailero"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** NO se emite `vehicle_type` como confirmado
- **AND** `ambiguity_flags` contiene `vehicle_type_ambiguous`

#### Scenario: "quinta rueda" → jerga ambigua
- **GIVEN** el candidato dice "información para operador quinta rueda"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** NO se emite `vehicle_type`
- **AND** `business_signals` contiene `jerga_ambigua_falta_unidad`

### Requirement: Experiencia no objetivo (torton/rabón/reparto) → señal escuelita

El sistema SHALL identificar torton, rabón, reparto local, interurbano y similares como
experiencia no-objetivo para la vacante principal. SHALL NOT confirmar como `full` ni como
`sencillo`. SHALL emitir señal `considerar_escuelita_transmontes`.

#### Scenario: "manejé torton" → escuelita, no vehicle_type
- **GIVEN** el candidato dice "manejé torton varios años"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** NO se emite `explicit_facts["experience.vehicle_type"]`
- **AND** `business_signals` contiene `considerar_escuelita_transmontes`
- **AND** `business_signals` NO contiene `objetivo_full_sencillo`

#### Scenario: "trabajé en rabón" → escuelita
- **GIVEN** el candidato dice "trabajé en rabón y pipa"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `considerar_escuelita_transmontes`

#### Scenario: "reparto local" → escuelita
- **GIVEN** el candidato dice "hago reparto local"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `considerar_escuelita_transmontes`

### Requirement: Sin experiencia en carretera → señal CECATI solamente

El sistema SHALL distinguir entre "sin experiencia" (CECATI) y "experiencia no-objetivo"
(escuelita). Si el candidato indica no tener experiencia, emite `cecati_sugerido`.
La respuesta SHALL informar sobre CECATI de forma limitada: sin afirmar convenio directo,
sin proporcionar horarios/costos/requisitos específicos, sin prometer ingreso.

#### Scenario: "no tengo experiencia" → cecati_sugerido
- **GIVEN** el candidato dice "no tengo experiencia manejando"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `cecati_sugerido`
- **AND** `business_signals` NO contiene `considerar_escuelita_transmontes`

#### Scenario: "quiero aprender a manejar" → cecati_sugerido
- **GIVEN** el candidato dice "quiero aprender a manejar tracto, ¿hay cursos?"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `cecati_sugerido`

### Requirement: Vacante B1 / Estados Unidos requiere humano

Si el candidato menciona B1, Estados Unidos, USA, EEUU o inglés para EUA, el sistema SHALL
emitir señal `considerar_operador_b1` y marcar `requires_human = true`. El bot no puede
validar el nivel de inglés ni aprobar esta ruta; debe canalizar a un reclutador humano.

#### Scenario: "busco vacante B1" → señal + humano
- **GIVEN** el candidato dice "busco vacante B1 o para Estados Unidos"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `considerar_operador_b1`
- **AND** `requires_human = true`

#### Scenario: "trabajo en USA" → señal + humano
- **GIVEN** el candidato dice "quiero trabajar en USA"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `considerar_operador_b1`
- **AND** `requires_human = true`

### Requirement: Reingreso requiere verificación humana

Si el candidato indica haber trabajado previamente con la empresa, el sistema SHALL emitir
`reingreso_verificar` y `requires_human = true`. El bot SHALL NOT aprobar ni rechazar el
reingreso; solo registra y canaliza.

#### Scenario: "ya trabajé con ustedes" → reingreso + humano
- **GIVEN** el candidato dice "ya trabajé con ustedes hace dos años"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `reingreso_verificar`
- **AND** `requires_human = true`

#### Scenario: "quiero volver" → reingreso + humano
- **GIVEN** el candidato dice "quiero volver a trabajar con la empresa"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `reingreso_verificar`
- **AND** `requires_human = true`

### Requirement: El shadow classifier no muta estado productivo

El shadow classifier SHALL ejecutarse sin efecto en la base de datos, Chatwoot ni
el routing productivo. Es observable (log/CSV) pero no activo.

#### Scenario: Clasificación no produce escritura a DB
- **WHEN** `classify_business_route(text)` se ejecuta con cualquier input
- **THEN** no se produce ninguna escritura a PostgreSQL, Redis ni Chatwoot
- **AND** el output es un objeto `BusinessRouteOutput` en memoria

#### Scenario: El módulo shadow no importa módulos productivos de escritura
- **WHEN** se importa `app.knowledge.business_route_classifier`
- **THEN** no se importa `app.db`, `app.tasks_chatwoot` ni `app.app`

### Requirement: Todo fact y señal requiere evidencia literal

El sistema SHALL incluir evidencia para cada `ExplicitFact` y `BusinessSignal`. Si no
existe una subcadena del mensaje del candidato que lo evidencie, el fact o señal SHALL
NOT emitirse. El policy router SHALL eliminar cualquier fact o señal sin evidencia.

#### Scenario: Fact sin evidence es eliminado por el policy router
- **GIVEN** un `ExplicitFact` con `evidence = ""`
- **WHEN** `policy_router_validate()` procesa el output
- **THEN** el fact es eliminado del output final

#### Scenario: Señal con confidence < 0.7 es eliminada
- **GIVEN** un `BusinessSignal` con `confidence = 0.5`
- **WHEN** `policy_router_validate()` procesa el output
- **THEN** la señal es eliminada del output final

### Requirement: Lenguaje de vigencia — prohibición de "caduca"/"caducidad"

El sistema SHALL usar `vence`/`vigencia`/`vencimiento` para referirse al vencimiento de
documentos médicos o de licencia. SHALL NOT usar `caduca` ni `caducidad`.

#### Scenario: Respuesta sobre apto médico usa "vence" no "caduca"
- **GIVEN** el candidato pregunta cuándo vence su apto médico
- **WHEN** el sistema genera una respuesta
- **THEN** la respuesta usa `vence`, `vencimiento` o `vigencia`
- **AND** la respuesta no contiene `caduca` ni `caducidad`

### Requirement: Documentos/imágenes — sin OCR, sin inferir facts

El sistema SHALL NOT inferir hechos, elegibilidad ni `profile_ready` desde imágenes,
archivos, documentos, stickers o audio. Ante multimedia, SHALL agradecer, aclarar que por
ahora no puede revisar ese tipo de contenido y pedir la respuesta en texto.

#### Scenario: Candidato envía foto de documento
- **GIVEN** el candidato envía una imagen (tipo "image")
- **WHEN** el sistema procesa el mensaje
- **THEN** la respuesta agradece y aclara que no puede revisar documentos por ese medio
- **AND** la respuesta solicita la respuesta en texto
- **AND** no se extrae ningún fact desde la imagen

#### Scenario: Mensaje mixto multimedia + texto → flag + clasificación del texto
- **GIVEN** el candidato envía `"<Multimedia omitido> Necesitas fotos por los dos lados?"`
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `ambiguity_flags` contiene `multimedia_no_ocr`
- **AND** `business_signals` contiene `documentos_requisitos` (evidenciado por el texto)
- **AND** no se infieren facts desde el contenido multimedia

### Requirement: Multi-intent — pago + pagarés + rutas en un solo mensaje

El sistema SHALL detectar múltiples señales de negocio en un mismo mensaje. Un candidato
puede hacer preguntas de pago, condiciones de contratación y rutas en un solo turno.
El sistema SHALL emitir señales para cada categoría y `policy_answer_keys` cuando la
pregunta activa una respuesta de política predefinida.

#### Scenario: Pago + pagarés en blanco + rutas → multi-señal + policy_answer_key
- **GIVEN** el candidato dice "¿A cómo el km cargado y vacío? ¿Firman pagarés en blanco? ¿Las rutas de Coahuila para dónde son?"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `pago_condiciones`
- **AND** `business_signals` contiene `ubicacion_base_traslado`
- **AND** `policy_answer_keys` contiene `no_pagares_en_blanco`
- **AND** `requested_info` tiene al menos 3 elementos

#### Scenario: policy_answer_keys vacío cuando no hay pregunta de pagarés
- **GIVEN** el candidato dice "¿cuánto paga el km cargado?"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `policy_answer_keys` está vacío

### Requirement: Queja con interés laboral → señal complaint_with_candidate_interest

El sistema SHALL emitir `complaint_with_candidate_interest` cuando el candidato expresa
frustración o queja pero simultáneamente demuestra interés en continuar buscando trabajo.
El sistema SHALL NOT rechazar ni desactivar el perfilamiento. El `profile_context_action`
SHALL ser `acknowledge_complaint_then_profile`.

#### Scenario: Queja + sigue buscando → señal + acción correcta
- **GIVEN** el candidato dice "La verdad entré a laborar la semana pasada y aún no me dan viaje, estoy buscando en otro lado"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `complaint_with_candidate_interest`
- **AND** `profile_context_action = acknowledge_complaint_then_profile`
- **AND** `requires_human = false`

### Requirement: Referido — candidato que menciona a un tercero

Si el candidato menciona a otra persona interesada en la vacante, el sistema SHALL
emitir `referral_candidate_contact` y `profile_context_action = handle_referral`.

#### Scenario: Referido explícito → señal + acción
- **GIVEN** el candidato dice "Mi cuñado también anda buscando trabajo de operador, ¿le puedo pasar el contacto?"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `referral_candidate_contact`
- **AND** `profile_context_action = handle_referral`

### Requirement: Policy router SHALL producir resultados deterministas

El policy router (`validate_business_output`) SHALL producir el mismo output para los
mismos inputs: facts confirmados (sencillo/full), `requires_human`, y validación de
vehicle_type son siempre deterministas independientemente del output LLM. El policy
router SHALL eliminar facts y señales inconsistentes antes de devolver el output final.

#### Scenario: vehicle_type policy es siempre determinista
- **GIVEN** cualquier mensaje que contenga solo "quinta rueda" como indicio de vehículo
- **WHEN** `validate_business_output` procesa el output
- **THEN** `experience.vehicle_type` NUNCA aparece en `explicit_facts`
- **AND** `requires_human` no es forzado a True (quinta rueda no es B1/reingreso)

### Requirement: El clasificador acepta contexto de perfil sin mutar estado

`classify_business_route_shadow` SHALL aceptar `canonical_profile` como contexto
read-only para detectar conflictos (e.g., city conflict). SHALL NOT modificar el
perfil canónico ni disparar acciones de escritura.

#### Scenario: Ciudad nueva contradice perfil canónico → needs_confirmation
- **GIVEN** el perfil canónico tiene `candidate.city = "Monterrey"`
- **AND** el candidato dice "soy de Torreón"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `explicit_facts["candidate.city"].needs_confirmation = true`
- **AND** el perfil canónico no es modificado

#### Scenario: Ciudad nueva igual al perfil → sin conflicto
- **GIVEN** el perfil canónico tiene `candidate.city = "Monterrey"`
- **AND** el candidato dice "soy de Monterrey"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `explicit_facts["candidate.city"].needs_confirmation = false`

### Requirement: Solicitud genérica de información sobre vacante → vacante_info_general

El sistema SHALL emitir `vacante_info_general` y `requested_info[category=vacancy_information]`
cuando el candidato solicita información general sobre la vacante sin mencionar tipo de unidad.
El `profile_context_action` SHALL ser `answer_or_clarify_current_question_first` ya que la
pregunta del candidato debe atenderse antes de continuar el perfilamiento.

#### Scenario: "Más información sobre la vacante" → vacante_info_general
- **GIVEN** el candidato dice "Hola. Más información sobre la vacante Operador Especializado por favor!"
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `business_signals` contiene `vacante_info_general`
- **AND** `requested_info` contiene al menos un item con `category = vacancy_information`
- **AND** `profile_context_action = answer_or_clarify_current_question_first`
- **AND** NO se emite `experience.vehicle_type`

### Requirement: Pregunta logística con multimedia → travel_logistics + multimedia_no_ocr, sin vehicle_type_ambiguous

El sistema SHALL emitir `multimedia_no_ocr` y la señal `ubicacion_base_traslado` cuando el
candidato pregunta sobre cómo trasladarse a una ciudad o base de operaciones y el mensaje
incluye `<Multimedia omitido>`. El sistema SHALL NOT emitir `vehicle_type_ambiguous` a menos
que la evidencia pertenezca explícitamente al catálogo de términos vehiculares ambiguos.

#### Scenario: "cómo irme a Manzanillo + multimedia" → travel_logistics + multimedia, sin vehicle_type_ambiguous
- **GIVEN** el candidato dice `"Pero como le Voi Acer para irme a Manzanillo\n<Multimedia omitido>"`
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `ambiguity_flags` contiene `multimedia_no_ocr`
- **AND** `ambiguity_flags` NO contiene `vehicle_type_ambiguous`
- **AND** `business_signals` contiene `ubicacion_base_traslado`
- **AND** `requested_info` contiene al menos un item con `category = travel_logistics`

### Requirement: vehicle_type_ambiguous solo para términos vehiculares del catálogo

El sistema SHALL emitir `vehicle_type_ambiguous` ÚNICAMENTE cuando la evidencia contiene
un término del catálogo vehicular ambiguo: quinta rueda, 5ta rueda, tráiler, trailer,
trailero, tractocamión. SHALL NOT emitir esta flag para texto que no pertenezca al dominio
vehicular — una expresión puede tener significado lingüístico válido (incluso en variante
ortográfica informal) sin ser evidencia de categoría vehicular. El policy router SHALL
eliminar la flag si la evidencia no resuelve a `status=NEEDS_CLARIFICATION` en el catálogo.

#### Scenario: Evidencia no vehicular hace que la policy elimine vehicle_type_ambiguous
- **GIVEN** el LLM emite `ambiguity_flags: [{"name": "vehicle_type_ambiguous", "evidence": "Voi Acer"}]`
  (nota: "Voi Acer" es variante ortográfica de "voy a hacer" — texto válido, no terminología vehicular)
- **WHEN** `validate_business_output` procesa el output
- **THEN** `vehicle_type_ambiguous` es eliminado de `ambiguity_flags`
- **AND** `validation_errors` contiene `vehicle_type_ambiguous_invalid_evidence`

#### Scenario: "quinta rueda" como evidencia conserva vehicle_type_ambiguous
- **GIVEN** el LLM emite `ambiguity_flags: [{"name": "vehicle_type_ambiguous", "evidence": "quinta rueda"}]`
- **WHEN** `validate_business_output` procesa el output
- **THEN** `vehicle_type_ambiguous` se conserva en `ambiguity_flags`

### Requirement: Pregunta contextual pendiente → answer_or_clarify_current_question_first

El sistema SHALL usar `answer_or_clarify_current_question_first` como `profile_context_action`
cuando el candidato hace una pregunta (aunque sea ambigua o requiera contexto previo).
`continue_profiling` SHALL NOT emplearse para ignorar la pregunta actual del candidato;
la intención presente debe atenderse o aclararse antes de continuar el perfilamiento.

#### Scenario: Pregunta ambigua sobre visita → clarify antes de continuar perfil
- **GIVEN** el candidato dice `"Oya se fueron\nSino para ir mañana\n??"`
- **WHEN** el shadow classifier procesa el mensaje
- **THEN** `profile_context_action = answer_or_clarify_current_question_first`
- **AND** `requested_info` contiene un item con `category = visit_availability`
- **AND** `ambiguity_flags` contiene `context_missing`
- **AND** el profile_context_action NO es `continue_profiling`

### Requirement: Validación general de catálogos sobre el output del LLM

El policy validator SHALL validar todo el output del LLM contra los catálogos del schema:
`ambiguity_flags` contra `AMBIGUITY_FLAG_NAMES`, `profile_context_action` contra
`PROFILE_CONTEXT_ACTIONS`, `policy_answer_keys` contra `POLICY_ANSWER_KEYS` y
`requested_info.category` contra `VALID_REQUESTED_INFO_CATEGORIES`. Los valores fuera de
catálogo SHALL eliminarse (o, para `profile_context_action`, reemplazarse por el fallback
seguro `continue_profiling`) y SHALL registrarse en `validation_errors` con el valor
rechazado. El sistema SHALL NOT usar regex ni listas duplicadas fuera del schema para
esta validación.

#### Scenario: Flag desconocido eliminado
- **GIVEN** el LLM emite `ambiguity_flags: [{"name": "address_needed", "evidence": "x"}]`
- **WHEN** `validate_business_output` procesa el output
- **THEN** `address_needed` NO está en `ambiguity_flags`
- **AND** `validation_errors` contiene `unknown_ambiguity_flag`

#### Scenario: profile_context_action desconocida cae al fallback
- **GIVEN** el LLM emite `profile_context_action = "continue_profilingg"`
- **WHEN** `validate_business_output` procesa el output
- **THEN** `profile_context_action = continue_profiling`
- **AND** `validation_errors` contiene `unknown_profile_context_action`

#### Scenario: Categoría de requested_info desconocida eliminada
- **GIVEN** el LLM emite `requested_info: [{"category": "salary_info", "evidence": "sueldo"}]`
- **WHEN** `validate_business_output` procesa el output
- **THEN** `requested_info` NO contiene `salary_info`
- **AND** `validation_errors` contiene `unknown_requested_info_category`

### Requirement: business_shadow_status independiente de la validación semántica

El sistema SHALL exponer `business_validation_errors` y `business_signal_names` como
columnas independientes de `business_shadow_status` en el reporte del harness. El sistema
SHALL emitir `business_shadow_status=OK` cuando el pipeline termina sin excepción técnica,
incluso si `business_validation_errors` no está vacío (la policy corrigió facts o flags
del LLM) o si el output quedó semánticamente vacío. El sistema SHALL NOT usar
`business_shadow_status` como indicador de validez semántica del output.

#### Scenario: status=OK con validation_errors no vacío
- **GIVEN** el LLM emite `vehicle_type_ambiguous` con evidencia no vehicular
- **WHEN** el shadow classifier procesa y el policy router valida
- **THEN** `business_shadow_status = OK`
- **AND** `business_validation_errors` contiene `vehicle_type_ambiguous_invalid_evidence`
- **AND** `business_ambiguity_names` NO contiene `vehicle_type_ambiguous`

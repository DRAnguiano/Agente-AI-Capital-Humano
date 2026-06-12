// Neo4j seed for HR recruiting assistant knowledge graph.
// Goal: move rule/dictionary/control knowledge out of scattered regex nodes.
// Safe to re-run: uses MERGE and stable ids.

// -----------------------------------------------------------------------------
// Constraints
// -----------------------------------------------------------------------------
CREATE CONSTRAINT kg_rule_id IF NOT EXISTS FOR (n:Rule) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_intent_id IF NOT EXISTS FOR (n:Intent) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_route_id IF NOT EXISTS FOR (n:Route) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_reply_id IF NOT EXISTS FOR (n:ReplyTemplate) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_term_id IF NOT EXISTS FOR (n:Term) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_policy_id IF NOT EXISTS FOR (n:Policy) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_topic_id IF NOT EXISTS FOR (n:Topic) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kg_source_id IF NOT EXISTS FOR (n:InternalSource) REQUIRE n.id IS UNIQUE;

// -----------------------------------------------------------------------------
// Routes
// -----------------------------------------------------------------------------
UNWIND [
  {id:'greeting', label:'Greeting'},
  {id:'rag', label:'Internal document answer'},
  {id:'profile', label:'Candidate profile capture'},
  {id:'human_handoff', label:'Human handoff'},
  {id:'clarification', label:'Ask clarification'},
  {id:'fallback', label:'Controlled fallback'},
  {id:'policy_boundary', label:'Policy boundary'},
  {id:'candidate_dropoff_recovery', label:'Candidate dropoff recovery'}
] AS row
MERGE (r:Route {id: row.id})
SET r.label = row.label;

// -----------------------------------------------------------------------------
// Reply templates
// -----------------------------------------------------------------------------
UNWIND [
  {
    id:'static_greeting',
    text:'Hola, soy Mundo del equipo de reclutamiento de Transmontes. ¿Le interesa la vacante de operador de tracto full o sencillo?'
  },
  {
    id:'static_on_route',
    text:'Claro, escribe cuando estés detenido y con seguridad; aquí seguimos con tu proceso.'
  },
  {
    id:'static_callback',
    text:'Claro, lo dejo anotado para que nuestro equipo pueda darte seguimiento por llamada.'
  },
  {
    id:'human_handoff_default',
    text:'Ese punto debe revisarlo nuestro equipo antes de continuar. Lo dejo anotado para seguimiento.'
  },
  {
    id:'dropoff_recovery',
    text:'Entiendo, una disculpa por la demora. Si aún estás abierto a escuchar la propuesta, podemos explicarte la vacante en una llamada rápida para que compares y decidas qué opción te conviene más. ¿Te gustaría que te agendemos?'
  },
  {
    id:'dropoff_close',
    text:'Gracias por avisarnos. Entendemos si ya decidiste avanzar con otra opción; te agradecemos el tiempo y dejamos la puerta abierta por si más adelante deseas revisar otra vacante.'
  },
  {
    id:'policy_zero_tolerance_review',
    text:'Nuestra empresa tiene política de 0 tolerancia en sustancias o alcohol relacionados con operación. Ese punto lo revisa nuestro equipo antes de continuar.'
  }
] AS row
MERGE (t:ReplyTemplate {id: row.id})
SET t.text = row.text,
    t.updated_at = datetime();

// -----------------------------------------------------------------------------
// Topics and internal sources
// -----------------------------------------------------------------------------
UNWIND [
  {id:'payment'},
  {id:'requirements'},
  {id:'routes'},
  {id:'safety'},
  {id:'training'},
  {id:'documents'}
] AS row
MERGE (topic:Topic {id: row.id});

UNWIND [
  {id:'payment_policy', kind:'rag_document'},
  {id:'requirements_policy', kind:'rag_document'},
  {id:'routes_policy', kind:'rag_document'},
  {id:'safety_policy', kind:'rag_document'},
  {id:'documents_policy', kind:'rag_document'}
] AS row
MERGE (source:InternalSource {id: row.id})
SET source.kind = row.kind;

MATCH (topic:Topic {id:'payment'}), (source:InternalSource {id:'payment_policy'})
MERGE (topic)-[:PREFERS_SOURCE]->(source);
MATCH (topic:Topic {id:'requirements'}), (source:InternalSource {id:'requirements_policy'})
MERGE (topic)-[:PREFERS_SOURCE]->(source);
MATCH (topic:Topic {id:'routes'}), (source:InternalSource {id:'routes_policy'})
MERGE (topic)-[:PREFERS_SOURCE]->(source);
MATCH (topic:Topic {id:'safety'}), (source:InternalSource {id:'safety_policy'})
MERGE (topic)-[:PREFERS_SOURCE]->(source);
MATCH (topic:Topic {id:'documents'}), (source:InternalSource {id:'documents_policy'})
MERGE (topic)-[:PREFERS_SOURCE]->(source);

// -----------------------------------------------------------------------------
// Intents
// -----------------------------------------------------------------------------
UNWIND [
  {id:'greeting', risk_level:'low', topic:null, route:'greeting'},
  {id:'payment_compensation', risk_level:'low', topic:'payment', route:'rag'},
  {id:'requirements_documents', risk_level:'low', topic:'requirements', route:'rag'},
  {id:'bases_routes_rest', risk_level:'low', topic:'routes', route:'rag'},
  {id:'safety_antidoping', risk_level:'low', topic:'safety', route:'rag'},
  {id:'candidate_profile_signal', risk_level:'low', topic:null, route:'profile'},
  {id:'candidate_dropoff_recovery', risk_level:'medium', topic:null, route:'candidate_dropoff_recovery'},
  {id:'candidate_dropoff_close', risk_level:'low', topic:null, route:'fallback'},
  {id:'ambiguous_slang_clarification', risk_level:'medium', topic:null, route:'clarification'},
  {id:'sensitive_handoff', risk_level:'high', topic:'safety', route:'human_handoff'},
  {id:'driving_school', risk_level:'low', topic:'documents', route:'rag'}
] AS row
MERGE (intent:Intent {id: row.id})
SET intent.risk_level = row.risk_level,
    intent.topic = row.topic
WITH intent, row
MATCH (route:Route {id: row.route})
MERGE (intent)-[:ROUTES_TO]->(route);

// -----------------------------------------------------------------------------
// Policies
// -----------------------------------------------------------------------------
UNWIND [
  {
    id:'no_hiring_promise',
    label:'No prometer contratación',
    risk_level:'low',
    public_guidance:'No prometas contratación ni selección; solo informa que nuestro equipo valida el avance.'
  },
  {
    id:'pay_must_come_from_internal_source',
    label:'Pago desde fuente interna',
    risk_level:'low',
    public_guidance:'No inventes pagos, kilómetros, vueltas, descansos ni bonos. Usa solo fuentes internas recuperadas.'
  },
  {
    id:'zero_tolerance_review',
    label:'Cero tolerancia operativa',
    risk_level:'high',
    public_guidance:'En temas de sustancias, alcohol o seguridad operativa, responde con cuidado y escala a nuestro equipo cuando aplique.'
  }
] AS row
MERGE (policy:Policy {id: row.id})
SET policy.label = row.label,
    policy.risk_level = row.risk_level,
    policy.public_guidance = row.public_guidance,
    policy.updated_at = datetime();

MATCH (policy:Policy {id:'no_hiring_promise'}), (intent:Intent)
MERGE (policy)-[:APPLIES_TO]->(intent);
MATCH (policy:Policy {id:'pay_must_come_from_internal_source'}), (intent:Intent {id:'payment_compensation'})
MERGE (policy)-[:APPLIES_TO]->(intent);
MATCH (policy:Policy {id:'zero_tolerance_review'}), (intent:Intent {id:'sensitive_handoff'})
MERGE (policy)-[:APPLIES_TO]->(intent);
MATCH (policy:Policy {id:'zero_tolerance_review'}), (intent:Intent {id:'safety_antidoping'})
MERGE (policy)-[:APPLIES_TO]->(intent);

// -----------------------------------------------------------------------------
// Controlled terms / dictionary
// -----------------------------------------------------------------------------
UNWIND [
  {
    id:'greeting_basic', canonical:'saludo', category:'greeting',
    aliases:['hola','buen dia','buen día','buenos dias','buenas','que tal','q tal'],
    intent:'greeting', reply:'static_greeting', source:null
  },
  {
    id:'payment_question', canonical:'pregunta de pago', category:'faq_topic',
    aliases:['cuanto pagan','cuánto pagan','pago','sueldo','compensacion','compensación','kilometro','kilómetro','km'],
    intent:'payment_compensation', reply:null, source:'payment_policy'
  },
  {
    id:'route_question', canonical:'pregunta de rutas', category:'faq_topic',
    aliases:['que rutas','qué rutas','rutas tienen','bases','cedis','monterrey','tramos'],
    intent:'bases_routes_rest', reply:null, source:'routes_policy'
  },
  {
    id:'documents_question', canonical:'documentos', category:'faq_topic',
    aliases:['documentos','papeles','cartas laborales','licencia','apto medico','apto médico'],
    intent:'requirements_documents', reply:null, source:'documents_policy'
  },
  {
    id:'profile_license_e', canonical:'licencia tipo E', category:'profile_signal',
    aliases:['licencia tipo e','tipo e','licencia e'],
    intent:'candidate_profile_signal', reply:null, source:null
  },
  {
    id:'profile_all_valid', canonical:'todo vigente', category:'profile_signal',
    aliases:['todo vigente','todos vigentes','documentacion vigente','documentación vigente','papeles vigentes'],
    intent:'candidate_profile_signal', reply:null, source:null
  },
  {
    id:'fifth_wheel_full', canonical:'full', category:'jargon',
    aliases:['full','doble remolque'],
    intent:'candidate_profile_signal', reply:null, source:null
  },
  {
    // Jerga del oficio/tractocamión: NO es tipo de unidad y NO equivale a full.
    // Señal de experiencia compatible; la unidad se confirma preguntando full o sencillo.
    id:'fifth_wheel_jargon', canonical:'quinta rueda (jerga, confirmar full o sencillo)', category:'jargon',
    aliases:['quinta rueda','quinta','5ta rueda','kinta rueda','op 5ta','operador 5ta','tracto','tractocamion','tractocamión'],
    intent:'candidate_profile_signal', reply:null, source:null
  },
  {
    // Escuelita: SOLO señales de falta de experiencia / interés en curso.
    // La jerga de quinta rueda NO va aquí: tener quinta rueda = experiencia
    // compatible, no candidato a escuelita (esos aliases viven en fifth_wheel_jargon).
    // Definido en el seed para sobrescribir el nodo legacy del grafo (SET aliases).
    id:'escuelita', canonical:'escuela de manejo', category:'jargon',
    aliases:['escuelita','escuela','eskuela','curso','kurso','capacitacion','capacitación','entrenamiento','me falta experiencia','falta experiencia','sin experiencia','no tengo experiencia','aprender','aprendo','ensenan','enseñan','me enseñan','me ensenan'],
    intent:'driving_school', reply:null, source:'documents_policy'
  },
  {
    id:'on_route_unavailable', canonical:'va manejando', category:'dropoff_signal',
    aliases:['voy manejando','vengo manejando','ando manejando','al rato','mas tarde','más tarde'],
    intent:'candidate_dropoff_recovery', reply:'static_on_route', source:null
  },
  {
    id:'dropoff_already_called', canonical:'ya me hablaron de otro trabajo', category:'dropoff_close_signal',
    aliases:['ya me hablaron de otro trabajo','ya agarre trabajo','ya agarré trabajo','ya consegui trabajo','ya conseguí trabajo'],
    intent:'candidate_dropoff_close', reply:'dropoff_close', source:null
  },
  {
    id:'safety_substances', canonical:'sustancias / antidoping', category:'sensitive_handoff',
    aliases:['droga','drogas','mota','cristal','perico','antidoping','antidopin','toxicológico','toxicologico'],
    intent:'safety_antidoping', reply:null, source:'safety_policy'
  },
  {
    id:'ambiguous_cachimba', canonical:'cachimba', category:'ambiguous_slang',
    aliases:['cachimba','cachimbear'],
    intent:'ambiguous_slang_clarification', reply:null, source:null
  }
] AS row
MERGE (term:Term {id: row.id})
SET term.canonical = row.canonical,
    term.category = row.category,
    term.aliases = row.aliases,
    term.updated_at = datetime()
WITH term, row
MATCH (intent:Intent {id: row.intent})
MERGE (term)-[:SUGGESTS_INTENT]->(intent)
WITH term, row
OPTIONAL MATCH (reply:ReplyTemplate {id: row.reply})
FOREACH (_ IN CASE WHEN reply IS NULL THEN [] ELSE [1] END |
  MERGE (term)-[:USES_REPLY]->(reply)
)
WITH term, row
OPTIONAL MATCH (source:InternalSource {id: row.source})
FOREACH (_ IN CASE WHEN source IS NULL THEN [] ELSE [1] END |
  MERGE (term)-[:PREFERS_SOURCE]->(source)
);

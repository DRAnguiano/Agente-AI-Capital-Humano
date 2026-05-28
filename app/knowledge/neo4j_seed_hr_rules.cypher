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
    text:'Hola, soy Mundo de Capital Humano. ¿Te interesa la vacante de operador de quinta rueda?'
  },
  {
    id:'static_on_route',
    text:'Claro, escribe cuando estés detenido y con seguridad; aquí seguimos con tu proceso.'
  },
  {
    id:'static_callback',
    text:'Claro, lo dejo anotado para que Capital Humano pueda darte seguimiento por llamada.'
  },
  {
    id:'human_handoff_default',
    text:'Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento.'
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
    text:'Nuestra empresa tiene política de 0 tolerancia. Capital Humano debe revisar este punto antes de continuar.'
  },
  {
    id:'ambiguous_term_clarification',
    text:'Me perdí tantito con esa palabra. ¿Me confirmas a qué te refieres? Así te respondo bien y sin inventarte información.'
  }
] AS row
MERGE (t:ReplyTemplate {id: row.id})
SET t.text = row.text,
    t.updated_at = datetime();

// -----------------------------------------------------------------------------
// Intents and routing
// -----------------------------------------------------------------------------
UNWIND [
  {id:'greeting', route:'greeting', risk:'low'},
  {id:'payment_compensation', route:'rag', risk:'low', topic:'payment'},
  {id:'requirements_documents', route:'rag', risk:'low', topic:'requirements'},
  {id:'drug_testing_urine', route:'rag', risk:'medium', topic:'safety'},
  {id:'bases_routes_rest', route:'rag', risk:'low', topic:'routes'},
  {id:'driving_school', route:'rag', risk:'low', topic:'training'},
  {id:'candidate_dropoff_risk', route:'candidate_dropoff_recovery', risk:'medium'},
  {id:'callback_request', route:'profile', risk:'low'},
  {id:'high_risk_sensitive', route:'human_handoff', risk:'high'},
  {id:'ambiguous_slang_clarification', route:'clarification', risk:'medium'}
] AS row
MERGE (i:Intent {id: row.id})
SET i.risk_level = row.risk,
    i.topic = row.topic
WITH row, i
MATCH (r:Route {id: row.route})
MERGE (i)-[:ROUTES_TO]->(r);

// -----------------------------------------------------------------------------
// Controlled dictionary / terms
// match_type is intentionally data, not Python regex architecture.
// The future node should tokenize/normalize text and query this dictionary.
// -----------------------------------------------------------------------------
UNWIND [
  // greetings
  {id:'hola', canonical:'hola', category:'greeting', intent:'greeting', aliases:['hola','buenas','buenos dias','buenos días','buen dia','buen día','buenas tardes','buenas noches','que tal','qué tal','q tal','k tal','hey']},

  // payment
  {id:'pago', canonical:'pago', category:'faq_topic', intent:'payment_compensation', source:'01_pago_prestaciones.md', aliases:['pago','pagan','pagos','sueldo','salario','kilometro','kilómetro','km','x kilometro','por kilometro','prestaciones','beneficios','bono','bonos','gastos muertos','viaticos','viáticos','fondo de ahorro']},

  // requirements
  {id:'documentos_requisitos', canonical:'documentos y requisitos', category:'faq_topic', intent:'requirements_documents', source:'02_documentos_requisitos.md', aliases:['requisitos','rekisitos','reqisitos','documentos','que piden','qué piden','ocupan','okupan','licencia','lic','apto','medico','médico','cartas laborales','cartas','sello','logotipo','vencida','vencido','renovarla','vigente']},

  // safety / tests
  {id:'antidoping', canonical:'pruebas toxicológicas', category:'faq_topic', intent:'drug_testing_urine', source:'03_seguridad_antidoping.md', aliases:['antidoping','anti doping','antidopin','doping','dooping','toxicol','toxicologica','toxicológica','toxicológicas','toxicologicas','prueba de drogas','pruebas de drogas','prueba de orina','pruebas de orina','orina','miados','meados','pipi','pipí','drogas']},

  // routes/bases
  {id:'rutas_bases', canonical:'rutas y bases', category:'faq_topic', intent:'bases_routes_rest', source:'04_bases_rutas.md', aliases:['base','bases','vase','patio','patios','siudad','ciudad','monterrey','torreon','torreón','nuevo laredo','queretaro','querétaro','cd juarez','cd. juárez','manzanillo','descanso','descansos','paradas','parada','cafe','café','baño','bano','ruta','rutas']},

  // training
  {id:'escuelita', canonical:'escuela de manejo', category:'faq_topic', intent:'driving_school', source:'02_documentos_requisitos.md', aliases:['escuelita','escuela','curso','op 5ta','5ta rueda','quinta rueda','me falta experiencia','sin experiencia','aprender','ensenan','enseñan']},

  // dropoff
  {id:'dropoff_delay', canonical:'riesgo de abandono por demora', category:'dropoff_signal', intent:'candidate_dropoff_risk', aliases:['desde ayer estoy esperando','desde ayer espero','estoy esperando','sigo esperando','me dejaron en visto','nadie me contesto','nadie me contestó','no me han contestado','no me respondieron','tardaron mucho','ya me hablaron de otro lado','me hablaron de otro lado','ya me llamaron de otro lado','me llamaron de otro lado','ya fui a otra entrevista']},
  {id:'dropoff_close', canonical:'candidato cierra proceso', category:'dropoff_close_signal', intent:'candidate_dropoff_risk', reply:'dropoff_close', aliases:['ya encontre trabajo','ya encontré trabajo','ya consegui trabajo','ya conseguí trabajo','ya no me interesa','no me interesa','ya acepte otro','ya acepté otro','gracias ya no']},

  // callback
  {id:'callback_request', canonical:'solicitud de llamada', category:'profile_signal', intent:'callback_request', reply:'static_callback', aliases:['llamenme','llámenme','llamenme','llámeme','me llaman','me pueden llamar','quiero que me llamen','a que hora me llaman','a qué hora me llaman']},

  // on route
  {id:'on_route', canonical:'candidato manejando/en ruta', category:'safety_static', intent:'profile', reply:'static_on_route', aliases:['voy manejando','ando en ruta','voy en ruta','10-4','al rato','ahorita manejo','luego te escribo','luego te mando']},

  // ambiguous slang
  {id:'cachimba', canonical:'cachimba/cachimbear', category:'ambiguous_slang', intent:'ambiguous_slang_clarification', aliases:['cachimba','cachimbear','cachimbr','cachimb','kchmbr','kchimb','kchimba','kachmbr'], meanings:['paradas breves en ruta','posible referencia sensible según contexto'], action:'clarify_or_dual_safe_response'},

  // high risk / sensitive handoff candidates
  {id:'high_risk_sensitive_terms', canonical:'tema sensible de revisión humana', category:'sensitive_handoff', intent:'high_risk_sensitive', aliases:['boletinado','r.control','r-control','huachicol','combustible robado','robo','robe','robé','abandone unidad','abandoné unidad','documento falso','licencia falsa','arma','armas','violencia','golpee','golpeé','pelea','demanda','acoso','me drogo','uso drogas','marihuana','mariguana','cristal','perico','cocaina','cocaína','metanfetamina','pastillas para aguantar','para no dormir']}
] AS row
MERGE (t:Term {id: row.id})
SET t.canonical = row.canonical,
    t.category = row.category,
    t.aliases = row.aliases,
    t.meanings = coalesce(row.meanings, []),
    t.action = row.action,
    t.updated_at = datetime()
WITH row, t
OPTIONAL MATCH (i:Intent {id: row.intent})
FOREACH (_ IN CASE WHEN i IS NULL THEN [] ELSE [1] END | MERGE (t)-[:SUGGESTS_INTENT]->(i))
WITH row, t
OPTIONAL MATCH (src:InternalSource {id: row.source})
FOREACH (_ IN CASE WHEN row.source IS NULL THEN [] ELSE [1] END |
  MERGE (s:InternalSource {id: row.source})
  SET s.kind = 'rag_document'
  MERGE (t)-[:PREFERS_SOURCE]->(s)
)
WITH row, t
OPTIONAL MATCH (reply:ReplyTemplate {id: row.reply})
FOREACH (_ IN CASE WHEN reply IS NULL THEN [] ELSE [1] END | MERGE (t)-[:USES_REPLY]->(reply));

// -----------------------------------------------------------------------------
// Policies
// -----------------------------------------------------------------------------
UNWIND [
  {
    id:'zero_tolerance',
    label:'Política de cero tolerancia',
    risk_level:'medium',
    public_guidance:'La empresa maneja política de cero tolerancia y puede realizar pruebas toxicológicas. La continuidad del proceso depende de cumplir esa política y de la validación de Capital Humano.',
    applies_to:['drug_testing_urine','ambiguous_slang_clarification','high_risk_sensitive']
  },
  {
    id:'no_hiring_promise',
    label:'No prometer contratación',
    risk_level:'low',
    public_guidance:'No afirmar que el candidato ya está contratado ni seleccionado.'
  },
  {
    id:'no_test_evasion',
    label:'No dar evasión de pruebas',
    risk_level:'high',
    public_guidance:'No explicar cómo evadir pruebas toxicológicas ni ventanas de detección.'
  }
] AS row
MERGE (p:Policy {id: row.id})
SET p.label = row.label,
    p.risk_level = row.risk_level,
    p.public_guidance = row.public_guidance,
    p.updated_at = datetime()
WITH row, p
UNWIND coalesce(row.applies_to, []) AS intent_id
MATCH (i:Intent {id: intent_id})
MERGE (p)-[:APPLIES_TO]->(i);

// -----------------------------------------------------------------------------
// Topic to source map
// -----------------------------------------------------------------------------
UNWIND [
  {id:'payment', source:'01_pago_prestaciones.md'},
  {id:'requirements', source:'02_documentos_requisitos.md'},
  {id:'safety', source:'03_seguridad_antidoping.md'},
  {id:'routes', source:'04_bases_rutas.md'},
  {id:'training', source:'02_documentos_requisitos.md'}
] AS row
MERGE (topic:Topic {id: row.id})
MERGE (src:InternalSource {id: row.source})
SET src.kind = 'rag_document'
MERGE (topic)-[:PREFERS_SOURCE]->(src);

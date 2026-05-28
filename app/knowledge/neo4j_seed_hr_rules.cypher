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
  {id:'on_route_safety', route:'profile', risk:'low'},
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
  {id:'hola', canonical:'hola', category:'greeting', intent:'greeting', aliases:['hola','ola','holaa','buenas','buenos dias','buenos días','buen dia','buen día','buenas tardes','buenas noches','que tal','qué tal','q tal','k tal','hey','ei','buenaz','buenas tardes']},

  // payment
  {id:'pago', canonical:'pago', category:'faq_topic', intent:'payment_compensation', source:'01_pago_prestaciones.md', aliases:['pago','paga','pagan','pagos','pgo','pagam','kuanto pagan','cuanto pagan','cuánto pagan','kuanto pagn','k pagan','cuanto es','cuánto es','sueldo','sueld','sueldo base','salario','salrio','lana','varos','dinero','kilometro','kilómetro','kilometraje','km','kms','x km','x kilometro','por km','por kilometro','por kilómetro','prestaciones','prestacion','prestacionez','beneficios','benefisio','benefisios','bono','bonos','bonificacion','bonificación','gastos muertos','gasto muerto','viaticos','viáticos','viatico','viático','fondo de ahorro','fondo ahorro']},

  // requirements
  {id:'documentos_requisitos', canonical:'documentos y requisitos', category:'faq_topic', intent:'requirements_documents', source:'02_documentos_requisitos.md', aliases:['requisitos','requisito','rekisitos','rekisito','reqisitos','reqisito','rekizitos','requerimientos','documento','documentos','doc','docs','documentacion','documentación','documentasion','papel','papeles','papeleria','papelería','papelera','papeles piden','que papeles','qué papeles','que papeles piden','qué papeles piden','informacion','información','informasion','información del proceso','info','datos','dato','mis datos','datos personales','que datos','qué datos','que piden','qué piden','que ocupan','qué ocupan','que okupan','qué okupan','que nesecitan','qué necesitan','que necesitan','qué nesecitan','que se necesita','que se nesecita','que documento piden','qué documento piden','que documentos piden','qué documentos piden','que documento debo subir','qué documento debo subir','que documentos debo subir','qué documentos debo subir','que papeles debo subir','qué papeles debo subir','que informacion debo subir','qué información debo subir','que datos debo subir','qué datos debo subir','documento debo subir','documentos debo subir','papeles debo subir','informacion debo subir','datos debo subir','subir documento','subir documentos','subir papeles','subir informacion','subir información','subir datos','mandar documento','mandar documentos','mandar papeles','mandar informacion','mandar información','mandar datos','enviar documento','enviar documentos','enviar papeles','enviar informacion','enviar información','enviar datos','seguir el proceso','continuar el proceso','para seguir el proceso','para continuar el proceso','proseguir','avanzar proceso','siguiente paso','siguiente proseso','ocupan','okupan','ocupo mandar','okupo mandar','licencia','lic','licencia federal','apto','apto medico','apto médico','medico','médico','cartas laborales','cartas','carta laboral','sello','logotipo','logo','vencida','vencido','renovarla','renovar','vigente','vigensia','vigencia']},

  // safety / tests
  {id:'antidoping', canonical:'pruebas toxicológicas', category:'faq_topic', intent:'drug_testing_urine', source:'03_seguridad_antidoping.md', aliases:['antidoping','anti doping','antidopin','antidopi','antidopin','anti dopin','doping','dooping','dopin','toxicol','toxicologica','toxicológica','toxicológicas','toxicologicas','toxicologica','toxicológico','toxicologico','examen medico','examen médico','revision medica','revisión médica','prueba de drogas','pruebas de drogas','prueba drogas','pruebas drogas','prueba de orina','pruebas de orina','prueba orina','orina','miados','meados','pipi','pipí','drogas','droga','sustancias','sustancia','alcohol','alcol','alchol']},

  // routes/bases
  {id:'rutas_bases', canonical:'rutas y bases', category:'faq_topic', intent:'bases_routes_rest', source:'04_bases_rutas.md', aliases:['base','bases','vase','vases','patio','patios','siudad','ciudad','cd','monterrey','mty','torreon','torreón','trc','nuevo laredo','nvo laredo','queretaro','querétaro','qro','cd juarez','cd. juárez','juarez','juárez','manzanillo','descanso','descansos','descanzo','deskanzo','paradas','parada','parador','paradores','cachimba','cafe','café','baño','bano','banio','ruta','rutas','viaje','viajes','vuelta','vueltas','sencillo','full','redondo','redonda','cedis','planta','cliente']},

  // training
  {id:'escuelita', canonical:'escuela de manejo', category:'faq_topic', intent:'driving_school', source:'02_documentos_requisitos.md', aliases:['escuelita','escuela','eskuela','curso','kurso','capacitacion','capacitación','entrenamiento','op 5ta','5ta rueda','quinta rueda','kinta rueda','quinta','me falta experiencia','falta experiencia','sin experiencia','no tengo experiencia','aprender','aprendo','ensenan','enseñan','me enseñan','me ensenan']},

  // dropoff
  {id:'dropoff_delay', canonical:'riesgo de abandono por demora', category:'dropoff_signal', intent:'candidate_dropoff_risk', reply:'dropoff_recovery', aliases:['desde ayer estoy esperando','desde ayer estoy esperndo','desde ayer espero','estoy esperando','estoy esperndo','sigo esperando','sigo esperndo','me dejaron en visto','nadie me contesto','nadie me contestó','nadie me a contestado','nadie me ha contestado','no me han contestado','no me an contestado','no me respondieron','no me responden','tardaron mucho','tardan mucho','ya me hablaron de otro lado','me hablaron de otro lado','ya me llamaron de otro lado','me llamaron de otro lado','ya fui a otra entrevista','otra empresa ya me habló','otra empresa ya me hablo']},
  {id:'dropoff_close', canonical:'candidato cierra proceso', category:'dropoff_close_signal', intent:'candidate_dropoff_risk', reply:'dropoff_close', aliases:['ya encontre trabajo','ya encontré trabajo','ya consegui trabajo','ya conseguí trabajo','ya agarre trabajo','ya agarré trabajo','ya no me interesa','no me interesa','ya acepte otro','ya acepté otro','gracias ya no','ya no gracias','no gracias','mejor ya no']},

  // callback
  {id:'callback_request', canonical:'solicitud de llamada', category:'profile_signal', intent:'callback_request', reply:'static_callback', aliases:['llamenme','llámenme','llamenme','llámeme','llameme','llamame','llámame','me llaman','me pueden llamar','pueden llamarme','quiero que me llamen','ocupó llamada','ocupo llamada','okupo llamada','a que hora me llaman','a qué hora me llaman','cuando me llaman','cuándo me llaman','me marcas','me marca','marquenme','márquenme']},

  // on route
  {id:'on_route', canonical:'candidato manejando/en ruta', category:'safety_static', intent:'on_route_safety', reply:'static_on_route', aliases:['voy manejando','boi manejando','boy manejando','voy manejano','ando manejando','ando en ruta','ando en carretera','voy en ruta','voy en carretera','10-4','al rato','alraton','alratito','ahorita manejo','ahorita manejando','estoy manejando','toy manejando','luego te escribo','luego le escribo','luego te mando','despues le escribo','después le escribo','cuando me pare','cuando este parado','cuando esté parado']},

  // ambiguous slang
  {id:'cachimba', canonical:'cachimba/cachimbear', category:'ambiguous_slang', intent:'ambiguous_slang_clarification', aliases:['cachimba','cachimbear','cachimbr','cachimb','kchmbr','kchimb','kchimba','kachmbr','kachimba','cachimbas','cachimbearle'], meanings:['paradas breves en ruta','posible referencia sensible según contexto'], action:'clarify_or_dual_safe_response'},

  // high risk / sensitive handoff candidates
  {id:'high_risk_sensitive_terms', canonical:'tema sensible de revisión humana', category:'sensitive_handoff', intent:'high_risk_sensitive', aliases:['boletinado','boletin','r.control','r-control','reporte control','huachicol','combustible robado','diesel robado','robo','robe','robé','abandone unidad','abandoné unidad','deje tirada la unidad','dejé tirada la unidad','documento falso','papeles falsos','licencia falsa','arma','armas','violencia','golpee','golpeé','pelea','demanda','acoso','me drogo','uso drogas','marihuana','mariguana','mota','cristal','perico','cocaina','cocaína','metanfetamina','pastillas para aguantar','para no dormir']}
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

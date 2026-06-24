## MODIFIED Requirements

### Requirement: normalize_text solo normaliza, no corrige

La función `normalize_text(text)` SHALL realizar únicamente lowercase, strip de acentos (NFKD), puntuación→espacio y compactación de espacios. SHALL NOT reescribir typos, corregir frases, inferir intención ni expandir abreviaciones. La corrección de typos en texto natural del candidato es responsabilidad exclusiva del LLM T=0.

#### Scenario: Typo pasa sin modificar por normalize_text

- **WHEN** `normalize_text` recibe "mi licensia esta vigente"
- **THEN** retorna "mi licensia esta vigente" (sin corregir "licensia")
- **AND** el LLM extractor puede interpretar "licensia" como "licencia"

#### Scenario: Acento strip aplicado correctamente

- **WHEN** `normalize_text` recibe "licencia tipo E vigente"
- **THEN** retorna "licencia tipo e vigente" (lowercase + sin acento en É si hubiera)

### Requirement: Extracción de hechos del candidato vía LLM T=0

El sistema SHALL usar exclusivamente LLM con temperatura=0 para extraer hechos del texto natural del candidato (vencimiento de licencia/apto, edad, años de experiencia, ciudad libre, ventana de llamada). Las capas deterministas SHALL operar únicamente sobre valores ya estructurados (catalog lookups, domain normalization).

#### Scenario: Vencimiento extraído por LLM desde texto con typo

- **WHEN** el candidato escribe "mi licensia vense en 1 año"
- **THEN** el extractor LLM T=0 retorna `expiration_text = "vence en 1 año"`
- **AND** el regex determinista no participa en la extracción

#### Scenario: Vencimiento no inventado sin contexto

- **WHEN** el candidato escribe "mi licencia es tipo E" (sin mención de vencimiento)
- **AND** la guarda `_expiry_hints` no detecta palabras de vencimiento en el mensaje
- **THEN** el sistema NO llama al LLM extractor de vencimiento
- **AND** `license.expiration_text` no se persiste en ese turno

#### Scenario: Edad extraída por LLM desde número escrito en español

- **WHEN** el candidato escribe "tengo cincuenta y un años"
- **THEN** el extractor LLM T=0 retorna `age = 51`
- **AND** no se confunde con 61 (sesenta y uno)

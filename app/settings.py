import os

from dotenv import load_dotenv

load_dotenv(override=False)

# Modelos
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))

# RAG
CHUNK_SIZE = os.getenv("CHUNK_SIZE", "800")
CHUNK_OVERLAP = os.getenv("CHUNK_OVERLAP", "150")
TOP_K = os.getenv("TOP_K", "3")
INDEX_EXTENSIONS = [
    ext.strip().lower()
    for ext in os.getenv("INDEX_EXTENSIONS", ".pdf,.txt,.md").split(",")
    if ext.strip()
]

# Rutas internas del contenedor
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DB_DIR = os.getenv("DB_DIR", "/app/chroma_db")

# Generacion
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.20"))

# Seguridad e indexacion
REINDEX_API_KEY = os.getenv("REINDEX_API_KEY", "")
INCLUDE_ERROR_DETAILS = os.getenv("INCLUDE_ERROR_DETAILS", "false").lower() == "true"
REINDEX_CLEAN = os.getenv("REINDEX_CLEAN", "false").lower() == "true"

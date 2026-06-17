import os

from dotenv import load_dotenv

load_dotenv(override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    ]


# =========================
# Modelos / embeddings
# =========================

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "BAAI/bge-m3",
)

# Provider principal:
# - groq
# - cohere
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()

# Groq fallback / provider alterno
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")
GROQ_MAX_TOKENS = _env_int("GROQ_MAX_TOKENS", 900)

# Cohere generación
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
COHERE_MODEL = os.getenv("COHERE_MODEL", "command-r-plus-08-2024")
COHERE_MAX_TOKENS = _env_int("COHERE_MAX_TOKENS", GROQ_MAX_TOKENS)

# Generación
TEMPERATURE = _env_float("TEMPERATURE", 0.5)


# =========================
# RAG / Chroma
# =========================

CHUNK_SIZE = _env_int("CHUNK_SIZE", 800)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 150)
TOP_K = _env_int("TOP_K", 5)

# Ensamblado de contexto RAG (context_builder.py) — fuente única de defaults.
# RAG_TOP_K hereda TOP_K por defecto para que un solo knob controle la recuperación
# (antes context_builder usaba un 3 hardcodeado independiente de TOP_K).
RAG_TOP_K = _env_int("RAG_TOP_K", TOP_K)
RAG_MIN_SCORE = _env_float("RAG_MIN_SCORE", 0.25)
RAG_MAX_CONTEXT_CHARS = _env_int("RAG_MAX_CONTEXT_CHARS", 2200)
RAG_MAX_CHARS_PER_DOC = _env_int("RAG_MAX_CHARS_PER_DOC", 850)

INDEX_EXTENSIONS = _env_list(
    "INDEX_EXTENSIONS",
    ".pdf,.txt,.md,.markdown",
)

# Rutas internas del contenedor
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DB_DIR = os.getenv("DB_DIR", "/app/chroma_db_bge_m3")

# Alias usado por indexer.py
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", DB_DIR)
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "rh_rag_docs_bge_m3")


# =========================
# Cohere Rerank
# =========================

RERANK_ENABLED = _env_bool("RERANK_ENABLED", False)
COHERE_RERANK_MODEL = os.getenv("COHERE_RERANK_MODEL", "rerank-v4.0-pro")
RERANK_INPUT_K = _env_int("RERANK_INPUT_K", 20)
RERANK_TOP_K = _env_int("RERANK_TOP_K", TOP_K)
RERANK_MAX_CHARS_PER_DOC = _env_int("RERANK_MAX_CHARS_PER_DOC", 2500)


# =========================
# Seguridad e indexación
# =========================

REINDEX_API_KEY = os.getenv("REINDEX_API_KEY", "")
# Clave para proteger endpoints internos (/ask, /orchestrate/message).
# Si está vacía, los endpoints siguen abiertos (modo demo). Configúrala en producción.
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
INCLUDE_ERROR_DETAILS = _env_bool("INCLUDE_ERROR_DETAILS", False)
REINDEX_CLEAN = _env_bool("REINDEX_CLEAN", False)

# Telemetría
CHROMA_ANONYMIZED_TELEMETRY = _env_bool("CHROMA_ANONYMIZED_TELEMETRY", False)
ANONYMIZED_TELEMETRY = _env_bool("ANONYMIZED_TELEMETRY", False)
POSTHOG_DISABLED = _env_bool("POSTHOG_DISABLED", True)

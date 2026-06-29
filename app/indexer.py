"""Indexación RAG y clientes LLM.

Dos responsabilidades:

1. **Construcción del índice** (`build_index`): lee fuentes en ``DATA_DIR``
   (PDF/txt/md), las trocea (`_split_text`) y las persiste como embeddings
   `BAAI/bge-m3` en la colección ChromaDB. El volumen ``.cache/`` (~2.4 GB con
   el modelo) NO se borra; ver constraint 7 en ``openspec/project.md``.
2. **Recuperación y generación**: `retrieve_context_for_guardrail` (recupera +
   rerank Cohere para el guardrail) y los clientes LLM Groq/Cohere
   (`call_llm`, `call_groq_json`, …).

Nota: la recuperación acotada por fuente autorizada (fail-closed de pago) vive
en `app/knowledge/context_builder.py`, que reutiliza los helpers privados de
este módulo (`_embed_texts`, `_get_collection`). El RAG responde políticas/HR;
nunca decide facts del candidato.
"""
import os
import re
from pathlib import Path
from typing import Any

import chromadb
import cohere
import httpx
from chromadb.config import Settings as ChromaSettings
from groq import Groq, RateLimitError as GroqRateLimitError
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from . import settings


# =========================
# Configuración con defaults
# =========================

DATA_DIR = getattr(settings, "DATA_DIR", os.getenv("DATA_DIR", "/app/data"))

CHROMA_DB_DIR = getattr(
    settings,
    "CHROMA_DB_DIR",
    getattr(settings, "DB_DIR", os.getenv("CHROMA_DB_DIR", "/app/chroma_db")),
)

COLLECTION_NAME = getattr(
    settings,
    "COLLECTION_NAME",
    os.getenv("COLLECTION_NAME", "rh_rag_docs"),
)

EMBEDDING_MODEL = getattr(
    settings,
    "EMBEDDING_MODEL",
    os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
)

CHUNK_SIZE = int(getattr(settings, "CHUNK_SIZE", os.getenv("CHUNK_SIZE", "500")))
CHUNK_OVERLAP = int(getattr(settings, "CHUNK_OVERLAP", os.getenv("CHUNK_OVERLAP", "100")))
TOP_K = int(getattr(settings, "TOP_K", os.getenv("TOP_K", "5")))

# Provider LLM:
# - groq
# - cohere
LLM_PROVIDER = getattr(
    settings,
    "LLM_PROVIDER",
    os.getenv("LLM_PROVIDER", "groq"),
).strip().lower()

GROQ_MODEL = getattr(
    settings,
    "GROQ_MODEL",
    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
)

GROQ_MAX_TOKENS = int(
    getattr(settings, "GROQ_MAX_TOKENS", os.getenv("GROQ_MAX_TOKENS", "900"))
)

COHERE_MODEL = getattr(
    settings,
    "COHERE_MODEL",
    os.getenv("COHERE_MODEL", "command-r-plus-08-2024"),
)

COHERE_MAX_TOKENS = int(
    getattr(
        settings,
        "COHERE_MAX_TOKENS",
        os.getenv("COHERE_MAX_TOKENS", str(GROQ_MAX_TOKENS)),
    )
)

TEMPERATURE = float(getattr(settings, "TEMPERATURE", os.getenv("TEMPERATURE", "0.0")))

GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

# Cohere Rerank.
# Flujo:
#   Chroma recupera RERANK_INPUT_K candidatos.
#   Cohere Rerank reordena esos candidatos.
#   El sistema devuelve RERANK_TOP_K o top_k, según aplique.
RERANK_ENABLED = str(
    getattr(settings, "RERANK_ENABLED", os.getenv("RERANK_ENABLED", "false"))
).strip().lower() in {"1", "true", "yes", "y", "on"}

COHERE_RERANK_MODEL = getattr(
    settings,
    "COHERE_RERANK_MODEL",
    os.getenv("COHERE_RERANK_MODEL", "rerank-v4.0-pro"),
)

RERANK_INPUT_K = int(
    getattr(settings, "RERANK_INPUT_K", os.getenv("RERANK_INPUT_K", "20"))
)

RERANK_TOP_K = int(
    getattr(settings, "RERANK_TOP_K", os.getenv("RERANK_TOP_K", str(TOP_K)))
)

RERANK_MAX_CHARS_PER_DOC = int(
    getattr(
        settings,
        "RERANK_MAX_CHARS_PER_DOC",
        os.getenv("RERANK_MAX_CHARS_PER_DOC", "2500"),
    )
)

INDEX_EXTENSIONS = getattr(
    settings,
    "INDEX_EXTENSIONS",
    [
        ext.strip().lower()
        for ext in os.getenv("INDEX_EXTENSIONS", ".pdf,.txt,.md,.markdown").split(",")
        if ext.strip()
    ],
)

if isinstance(INDEX_EXTENSIONS, str):
    INDEX_EXTENSIONS = [
        ext.strip().lower()
        for ext in INDEX_EXTENSIONS.split(",")
        if ext.strip()
    ]


def _normalize_extension(ext: str) -> str:
    ext = (ext or "").strip().lower()
    if not ext:
        return ""
    return ext if ext.startswith(".") else f".{ext}"


INDEX_EXTENSIONS = [
    normalized
    for normalized in (_normalize_extension(ext) for ext in INDEX_EXTENSIONS)
    if normalized
]


_embedding_model: SentenceTransformer | None = None


# =========================
# Utilidades generales
# =========================

def _to_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\uFFFD", "")
    text = text.replace("\x00", "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model

    if _embedding_model is None:
        print(f"[indexer] Cargando embedding model: {EMBEDDING_MODEL}", flush=True)
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    return _embedding_model


def _embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


# =========================
# Lectores de documentos
# =========================

def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages: list[str] = []

    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            print(f"[indexer] Error leyendo página {index} de {path}: {exc}", flush=True)
            text = ""

        if text.strip():
            pages.append(f"\n\n[Página {index}]\n{text.strip()}")

    return _normalize_text("\n".join(pages))


def _read_text_file(path: Path) -> str:
    return _normalize_text(path.read_text(encoding="utf-8", errors="ignore"))


def _read_source_file(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _read_pdf(path)

    if suffix in {".txt", ".md", ".markdown"}:
        return _read_text_file(path)

    return ""


def _iter_source_files(data_dir: str) -> list[Path]:
    base = Path(data_dir)

    if not base.exists():
        raise RuntimeError(f"No existe DATA_DIR: {data_dir}")

    if not base.is_dir():
        raise RuntimeError(f"DATA_DIR no es una carpeta: {data_dir}")

    allowed = {ext.lower() for ext in INDEX_EXTENSIONS}

    files = [
        path
        for path in base.rglob("*")
        if path.is_file()
        and path.suffix.lower() in allowed
        and not path.name.startswith(".")
        and "/_backup" not in str(path).replace("\\", "/")
    ]

    return sorted(files)


# =========================
# Chunking
# =========================

def _split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = _normalize_text(text)

    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Intentar cortar bonito en salto de línea o punto.
        if end < text_len:
            newline_cut = text.rfind("\n", start, end)
            period_cut = text.rfind(". ", start, end)

            cut = max(newline_cut, period_cut)

            if cut > start + int(chunk_size * 0.55):
                end = cut + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        start = max(end - overlap, start + 1)

    return chunks


# =========================
# ChromaDB
# =========================

def _get_chroma_client(db_dir: str | None = None):
    persist_dir = db_dir or CHROMA_DB_DIR
    Path(persist_dir).mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(
        path=persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _reset_collection(client):
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _get_collection(db_dir: str | None = None):
    client = _get_chroma_client(db_dir)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# =========================
# Indexación
# =========================

def build_index(data_dir: str | None = None, db_dir: str | None = None):
    data_dir = data_dir or DATA_DIR
    db_dir = db_dir or CHROMA_DB_DIR

    files = _iter_source_files(data_dir)

    if not files:
        raise RuntimeError(f"No se encontraron documentos indexables en {data_dir}")

    print(f"[indexer] DATA_DIR={data_dir}", flush=True)
    print(f"[indexer] CHROMA_DB_DIR={db_dir}", flush=True)
    print(f"[indexer] COLLECTION_NAME={COLLECTION_NAME}", flush=True)
    print(f"[indexer] INDEX_EXTENSIONS={INDEX_EXTENSIONS}", flush=True)
    print(f"[indexer] Documentos encontrados: {len(files)}", flush=True)

    client = _get_chroma_client(db_dir)
    collection = _reset_collection(client)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    total_chunks = 0
    indexed_files = 0
    skipped_files = 0

    base_path = Path(data_dir)

    for path in files:
        rel_path = str(path.relative_to(base_path))

        try:
            raw_text = _read_source_file(path)
        except Exception as exc:
            skipped_files += 1
            print(f"[indexer] Error leyendo {rel_path}: {type(exc).__name__}: {exc}", flush=True)
            continue

        chunks = _split_text(raw_text)

        if not chunks:
            skipped_files += 1
            print(f"[indexer] Documento sin texto útil: {rel_path}", flush=True)
            continue

        indexed_files += 1

        for index, chunk in enumerate(chunks):
            chunk_id = f"{rel_path}::chunk-{index}"

            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "source": rel_path,
                    "chunk": index,
                    "file_name": path.name,
                    "file_ext": path.suffix.lower(),
                }
            )

        total_chunks += len(chunks)
        print(f"[indexer] {rel_path}: {len(chunks)} chunks", flush=True)

    if not documents:
        raise RuntimeError("No se generaron chunks indexables.")

    embeddings = _embed_texts(documents)

    batch_size = 256
    for start in range(0, len(documents), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            embeddings=embeddings[start:end],
        )

    return {
        "data_dir": data_dir,
        "db_dir": db_dir,
        "collection": COLLECTION_NAME,
        "files_found": len(files),
        "files_indexed": indexed_files,
        "files_skipped": skipped_files,
        "chunks_indexed": total_chunks,
        "embedding_model": EMBEDDING_MODEL,
        "extensions": sorted(list(set(INDEX_EXTENSIONS))),
        "rerank_enabled": RERANK_ENABLED,
        "rerank_model": COHERE_RERANK_MODEL if RERANK_ENABLED else None,
    }


# =========================
# Rerank
# =========================

def _extract_rerank_results(response: Any) -> list[Any]:
    """
    Extrae resultados de Cohere Rerank de forma tolerante.
    Normalmente response.results trae objetos con index y relevance_score.
    """
    try:
        results = getattr(response, "results", None)
        if results is not None:
            return list(results)
    except Exception:
        pass

    try:
        if isinstance(response, dict):
            return response.get("results", []) or []
    except Exception:
        pass

    return []


def _get_rerank_result_index(result: Any) -> int | None:
    idx = getattr(result, "index", None)

    if idx is None and isinstance(result, dict):
        idx = result.get("index")

    if idx is None:
        try:
            document = getattr(result, "document", None)
            if document is not None:
                doc_id = getattr(document, "id", None)
                if doc_id is not None:
                    idx = doc_id
        except Exception:
            pass

    if idx is None:
        try:
            if isinstance(result, dict):
                document = result.get("document") or {}
                idx = document.get("id")
        except Exception:
            pass

    try:
        return int(idx)
    except Exception:
        return None


def _get_rerank_result_score(result: Any) -> float | None:
    score = getattr(result, "relevance_score", None)

    if score is None and isinstance(result, dict):
        score = result.get("relevance_score")

    try:
        return float(score)
    except Exception:
        return None


def _rerank_context_items(
    query: str,
    items: list[dict[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    """
    Reordena chunks recuperados por Chroma usando Cohere Rerank.
    Si Cohere falla, devuelve los items originales para no romper el sistema.
    """
    if not RERANK_ENABLED:
        return items[:top_n]

    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        print("[rerank] RERANK_ENABLED=true pero falta COHERE_API_KEY. Usando Chroma directo.", flush=True)
        return items[:top_n]

    if not query or not items:
        return items[:top_n]

    try:
        client = cohere.ClientV2(api_key=api_key)

        documents: list[str] = []
        for i, item in enumerate(items):
            source = item.get("source") or "unknown"
            text = (item.get("text") or "")[:RERANK_MAX_CHARS_PER_DOC]
            documents.append(f"id: {i}\nsource: {source}\ntext: {text}")

        top_n = min(top_n, len(documents))

        print(
            f"[rerank] Modelo: {COHERE_RERANK_MODEL} | input={len(documents)} | top_n={top_n}",
            flush=True,
        )

        response = client.rerank(
            model=COHERE_RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_n,
        )

        ranked_results = _extract_rerank_results(response)
        reranked: list[dict[str, Any]] = []

        for result in ranked_results:
            idx = _get_rerank_result_index(result)
            relevance_score = _get_rerank_result_score(result)

            if idx is None or idx < 0 or idx >= len(items):
                continue

            item = dict(items[idx])

            # Conservamos score original de Chroma para auditoría.
            item["chroma_score"] = item.get("score")
            item["rerank_score"] = relevance_score

            # Compatibilidad: app.py y orchestrator.py filtran por item["score"].
            # Si existe rerank_score, lo ponemos como score principal.
            if relevance_score is not None:
                item["score"] = relevance_score

            reranked.append(item)

        if reranked:
            return reranked[:top_n]

        print("[rerank] Cohere devolvió resultados vacíos. Usando Chroma directo.", flush=True)
        return items[:top_n]

    except Exception as exc:
        print(f"[rerank] Error: {type(exc).__name__}: {exc}. Usando Chroma directo.", flush=True)
        return items[:top_n]


# =========================
# Recuperación RAG
# =========================

def retrieve_context_for_guardrail(question: str, top_k: int | None = None) -> list[dict[str, Any]]:
    query = _normalize_text(question)

    if not query:
        return []

    requested_k = _to_int(top_k, TOP_K)

    if RERANK_ENABLED:
        chroma_k = max(requested_k, RERANK_INPUT_K)
        final_k = min(requested_k, RERANK_TOP_K) if top_k is not None else RERANK_TOP_K
    else:
        chroma_k = requested_k
        final_k = requested_k

    try:
        collection = _get_collection()
        query_embedding = _embed_texts([query])[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=chroma_k,
            include=["documents", "distances", "metadatas"],
        )
    except Exception as exc:
        print(f"[indexer] Error recuperando contexto: {type(exc).__name__}: {exc}", flush=True)
        return []

    docs = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    output: list[dict[str, Any]] = []

    for doc, distance, metadata, chunk_id in zip(docs, distances, metadatas, ids):
        # Chroma cosine distance: menor distancia = más parecido.
        # Convertimos a score simple 0-1 aproximado.
        try:
            score = max(0.0, 1.0 - float(distance))
        except Exception:
            score = 0.0

        output.append(
            {
                "id": chunk_id,
                "text": doc,
                "distance": distance,
                "score": score,
                "source": (metadata or {}).get("source"),
                "metadata": metadata or {},
            }
        )

    if RERANK_ENABLED:
        return _rerank_context_items(query=query, items=output, top_n=final_k)

    return output[:final_k]


# =========================
# LLM remoto: Groq / Cohere
# =========================

def _llm_system_message() -> str:
    return (
        "Eres un asistente de Capital Humano para reclutamiento. "
        "Sigue estrictamente las instrucciones del prompt. "
        "No inventes datos no proporcionados por los documentos o el sistema. "
        "Responde en español natural, claro y profesional."
    )


def _extract_cohere_text(response: Any) -> str:
    """
    Extrae texto de respuestas Cohere SDK v2 de forma tolerante.

    En Cohere v2 normalmente se usa:
        response.message.content[0].text

    Pero dejamos extracción flexible para evitar romper por pequeñas diferencias
    de versión del SDK.
    """
    try:
        content = response.message.content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
                    continue

                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
                    continue

            return "\n".join(parts).strip()

        if isinstance(content, str):
            return content.strip()
    except Exception:
        pass

    try:
        text = getattr(response, "text", None)
        if text:
            return str(text).strip()
    except Exception:
        pass

    return ""


def _groq_call(
    api_key: str,
    messages: list[dict],
    model: str,
    *,
    json_mode: bool = False,
    temperature: float = TEMPERATURE,
    max_tokens: int = GROQ_MAX_TOKENS,
    timeout_key: str = "GROQ_TIMEOUT_SECONDS",
    timeout_default: str = "8",
) -> str:
    """Ejecuta una llamada a Groq y devuelve el contenido de la respuesta.

    Punto único de construcción del cliente; los callers públicos implementan
    el patrón de fallback (primary → backup) sobre este helper.
    """
    timeout_secs = float(os.getenv(timeout_key, timeout_default))
    timeout = httpx.Timeout(timeout_secs, connect=5.0)
    kwargs: dict = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=timeout) as http_client:
        client = Groq(api_key=api_key, http_client=http_client)
        completion = client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content or ("" if not json_mode else "{}")


def _groq_with_fallback(
    primary_key: str,
    backup_key: str | None,
    fn_name: str,
    messages: list[dict],
    model: str,
    *,
    json_mode: bool = False,
    temperature: float = TEMPERATURE,
    max_tokens: int = GROQ_MAX_TOKENS,
    timeout_key: str = "GROQ_TIMEOUT_SECONDS",
    timeout_default: str = "8",
) -> str:
    """Llama a _groq_call con primary_key; si devuelve RateLimitError y hay
    backup_key, reintenta con ella. Registra el fallback en el log.
    """
    call_kwargs = dict(
        json_mode=json_mode,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_key=timeout_key,
        timeout_default=timeout_default,
    )
    try:
        return _groq_call(primary_key, messages, model, **call_kwargs)
    except GroqRateLimitError as exc:
        if not backup_key:
            raise
        print(f"[groq-fallback] cuota primaria agotada, usando BACKUP — {fn_name}", flush=True)
        try:
            return _groq_call(backup_key, messages, model, **call_kwargs)
        except GroqRateLimitError as exc2:
            print(f"[groq-fallback] BACKUP también agotada — {fn_name}: {exc2}", flush=True)
            raise exc2


def call_groq_llm(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        return "Error: falta configurar GROQ_API_KEY."

    backup_key = os.environ.get("GROQ_API_KEY_BACKUP")
    messages = [
        {"role": "system", "content": _llm_system_message()},
        {"role": "user", "content": prompt},
    ]
    print(f"[groq] Modelo: {GROQ_MODEL}", flush=True)
    try:
        return _groq_with_fallback(
            api_key, backup_key, "call_groq_llm", messages, GROQ_MODEL,
            temperature=TEMPERATURE, max_tokens=GROQ_MAX_TOKENS,
        )
    except Exception as exc:
        print(f"[groq] Error: {type(exc).__name__}: {exc}", flush=True)
        return "Tuve un problema al generar la respuesta. Por favor intenta de nuevo."


def call_cohere_llm(prompt: str) -> str:
    api_key = os.environ.get("COHERE_API_KEY")
    model = os.environ.get("COHERE_MODEL", COHERE_MODEL)
    max_tokens = _to_int(os.environ.get("COHERE_MAX_TOKENS"), COHERE_MAX_TOKENS)

    if not api_key:
        print("[cohere] Falta COHERE_API_KEY. Intentando fallback Groq.", flush=True)
        if os.environ.get("GROQ_API_KEY"):
            return call_groq_llm(prompt)
        return "Error: falta configurar COHERE_API_KEY."

    try:
        client = cohere.ClientV2(api_key=api_key)

        print(f"[cohere] Modelo: {model}", flush=True)

        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": _llm_system_message(),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=TEMPERATURE,
            max_tokens=max_tokens,
        )

        text = _extract_cohere_text(response)

        if not text:
            raise RuntimeError("Respuesta vacía desde Cohere.")

        return text

    except Exception as exc:
        print(f"[cohere] Error: {type(exc).__name__}: {exc}", flush=True)

        # Fallback a Groq si está configurado.
        if os.environ.get("GROQ_API_KEY"):
            print("[cohere] Usando fallback Groq.", flush=True)
            return call_groq_llm(prompt)

        return "Tuve un problema al generar la respuesta. Por favor intenta de nuevo."


def call_groq_json(prompt: str, system_message: str, *, temperature: float = 0.0,
                   model: str | None = None) -> str:
    """Llama a Groq en JSON mode para clasificación determinista.

    Devuelve el string JSON crudo (el caller lo parsea/valida). Distinta de
    call_llm: usa response_format json_object, temperatura ~0 y un system message
    propio (no el de Mundo conversacional). No reemplaza call_llm.

    model: por defecto GROQ_MODEL. Para clasificación conviene un modelo chico
    (ej. llama-3.1-8b-instant): más barato en tokens y más rápido.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return '{"error": "missing_groq_api_key"}'

    backup_key = os.environ.get("GROQ_API_KEY_BACKUP")
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt},
    ]
    try:
        return _groq_with_fallback(
            api_key, backup_key, "call_groq_json", messages, model or GROQ_MODEL,
            json_mode=True, temperature=temperature, max_tokens=GROQ_MAX_TOKENS,
            timeout_key="GROQ_JSON_TIMEOUT_SECONDS", timeout_default="10",
        )
    except Exception as exc:
        print(f"[groq_json] Error: {type(exc).__name__}: {exc}", flush=True)
        return f'{{"error": "{type(exc).__name__}"}}'


def call_groq_with_system(system: str, user: str, *, temperature: float | None = None, max_tokens: int = 300) -> str:
    """Groq conversational call con system prompt arbitrario (no JSON mode).

    Distinta de call_llm: acepta system prompt externo en lugar de _llm_system_message().
    Usada para respuestas generadas por el LLM siguiendo reglas de persona_config sin
    pasar por el pipeline RAG completo (ej. descalificación por edad).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Tuve un problema al generar la respuesta. Por favor intenta de nuevo."
    backup_key = os.environ.get("GROQ_API_KEY_BACKUP")
    t = temperature if temperature is not None else TEMPERATURE
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        return _groq_with_fallback(
            api_key, backup_key, "call_groq_with_system", messages, GROQ_MODEL,
            temperature=t, max_tokens=max_tokens,
        )
    except Exception as exc:
        print(f"[groq_with_system] Error: {type(exc).__name__}: {exc}", flush=True)
        return "Tuve un problema al generar la respuesta. Por favor intenta de nuevo."


def call_groq_transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Transcribe un archivo de audio con Groq Whisper; devuelve el texto o '' si falla.

    Sigue el mismo patrón de fallback a GROQ_API_KEY_BACKUP que las demás funciones Groq.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[groq_transcribe] Falta GROQ_API_KEY", flush=True)
        return ""
    if not audio_bytes:
        return ""

    backup_key = os.environ.get("GROQ_API_KEY_BACKUP")

    def _transcribe(key: str) -> str:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as http_client:
            client = Groq(api_key=key, http_client=http_client)
            result = client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model=GROQ_WHISPER_MODEL,
                response_format="text",
            )
        # SDK devuelve str directamente con response_format="text"
        return str(result).strip() if result else ""

    try:
        return _transcribe(api_key)
    except GroqRateLimitError:
        if not backup_key:
            raise
        print("[groq-fallback] cuota primaria agotada, usando BACKUP — call_groq_transcribe", flush=True)
        try:
            return _transcribe(backup_key)
        except Exception as exc2:
            print(f"[groq_transcribe] BACKUP falló: {type(exc2).__name__}: {exc2}", flush=True)
            return ""
    except Exception as exc:
        print(f"[groq_transcribe] Error: {type(exc).__name__}: {exc}", flush=True)
        return ""


def call_llm(prompt: str) -> str:
    provider = os.environ.get("LLM_PROVIDER", LLM_PROVIDER).strip().lower()

    if provider == "cohere":
        return call_cohere_llm(prompt)

    if provider == "groq":
        return call_groq_llm(prompt)

    print(
        f"[llm] LLM_PROVIDER desconocido: {provider}. Usando Groq por fallback.",
        flush=True,
    )
    return call_groq_llm(prompt)

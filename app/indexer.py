from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import chromadb
import httpx
import torch
from chromadb.config import Settings as ChromaSettings
from groq import Groq
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from .settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DATA_DIR,
    DB_DIR,
    EMBEDDING_MODEL,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    INDEX_EXTENSIONS,
    REINDEX_CLEAN,
    TEMPERATURE,
    TOP_K,
)

COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "hr_recruiting_docs")

_MODEL_CACHE: SentenceTransformer | None = None
_CHROMA_CLIENT: chromadb.PersistentClient | None = None
_COLLECTION: Any | None = None


def _to_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _detect_device() -> str:
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        print(f"[torch] GPU detectada: {name}")
        return "cuda"
    print("[torch] Usando CPU")
    return "cpu"


def _embedding_model() -> SentenceTransformer:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        print(f"[embeddings] Modelo: {EMBEDDING_MODEL}")
        _MODEL_CACHE = SentenceTransformer(EMBEDDING_MODEL, device=_detect_device())
    return _MODEL_CACHE


def _client() -> chromadb.PersistentClient:
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        Path(DB_DIR).mkdir(parents=True, exist_ok=True)
        _CHROMA_CLIENT = chromadb.PersistentClient(
            path=DB_DIR,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
    return _CHROMA_CLIENT


def _collection(clean: bool = False):
    global _COLLECTION
    client = _client()
    if clean:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"[chroma] Coleccion eliminada: {COLLECTION_NAME}")
        except Exception:
            pass
        _COLLECTION = None
    if _COLLECTION is None:
        _COLLECTION = client.get_or_create_collection(name=COLLECTION_NAME)
        print(f"[chroma] Coleccion activa: {COLLECTION_NAME}")
    return _COLLECTION


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return _read_pdf(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    clean = " ".join((text or "").split())
    if not clean:
        return []

    chunk_size = max(chunk_size, 200)
    overlap = min(max(overlap, 0), chunk_size - 1)
    step = chunk_size - overlap

    chunks = []
    for start in range(0, len(clean), step):
        chunk = clean[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(clean):
            break
    return chunks


def _iter_source_files(data_dir: str) -> list[Path]:
    base = Path(data_dir)
    if not base.exists():
        return []
    allowed = {ext.lower() for ext in INDEX_EXTENSIONS}
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in allowed
    )


def build_index(data_dir: str | None = None, db_dir: str | None = None):
    if db_dir:
        os.environ["DB_DIR"] = db_dir

    data_dir = data_dir or DATA_DIR
    chunk_size = _to_int(CHUNK_SIZE, 800)
    chunk_overlap = _to_int(CHUNK_OVERLAP, 150)

    files = _iter_source_files(data_dir)
    if not files:
        raise RuntimeError(f"No se encontraron documentos indexables en {data_dir}")

    collection = _collection(clean=REINDEX_CLEAN)
    model = _embedding_model()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for path in files:
        text = _read_document(path)
        rel_path = str(path.relative_to(data_dir))
        for index, chunk in enumerate(_chunk_text(text, chunk_size, chunk_overlap)):
            digest = hashlib.sha1(f"{rel_path}:{index}:{chunk[:80]}".encode("utf-8")).hexdigest()
            ids.append(digest)
            documents.append(chunk)
            metadatas.append({"source": rel_path, "chunk": index})

    if not documents:
        raise RuntimeError("Los documentos encontrados no tienen texto extraible.")

    embeddings = model.encode(documents, show_progress_bar=True).tolist()
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print(f"[index] {len(documents)} chunks indexados desde {len(files)} archivo(s).")
    return {"documents": len(files), "chunks": len(documents), "collection": COLLECTION_NAME}


def retrieve_context_for_guardrail(
    user_query: str,
    db_dir: str | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    if db_dir:
        os.environ["DB_DIR"] = db_dir

    k = _to_int(top_k, _to_int(TOP_K, 3))
    k = max(k, 1)

    collection = _collection()
    count = collection.count()
    if count <= 0:
        return []
    k = min(k, count)

    query_embedding = _embedding_model().encode(user_query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "distances", "metadatas"],
    )

    docs = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    out = []
    for doc, distance, metadata, chunk_id in zip(docs, distances, metadatas, ids):
        score = 1 / (1 + float(distance or 0))
        out.append(
            {
                "score": score,
                "text": doc[:1000],
                "source": (metadata or {}).get("source"),
                "id": chunk_id,
            }
        )
    return out


def get_retriever(db_dir: str | None = None, top_k: int | None = None):
    class Retriever:
        def retrieve(self, query: str):
            return retrieve_context_for_guardrail(query, db_dir=db_dir, top_k=top_k)

    return Retriever()


def call_llm(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Error: falta configurar GROQ_API_KEY."

    try:
        http_client = httpx.Client(trust_env=False)
        client = Groq(api_key=api_key, http_client=http_client)
        print(f"[groq] Modelo: {GROQ_MODEL}")

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=GROQ_MAX_TOKENS,
        )
        return completion.choices[0].message.content or ""
    except Exception as exc:
        print(f"[groq] Error: {type(exc).__name__}: {exc}")
        return "Tuvimos un problema tecnico al procesar tu solicitud. Podrias intentar de nuevo?"

# services/common/kg_common/ingest.py
import io
import os
import re
import time
import uuid
import itertools
from typing import List, Tuple, Iterable, Dict, Any

import redis
import requests
from pdfminer.high_level import extract_text

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .llm import complete, embed
from requests.auth import HTTPBasicAuth

FUSEKI_USER = os.getenv("FUSEKI_USER") or None
FUSEKI_PASSWORD = os.getenv("FUSEKI_PASSWORD") or None

# -------------------- Config --------------------
REDIS_URL   = os.getenv("REDIS_URL", "redis://redis:6379/0")
#FUSEKI_BASE = os.getenv("FUSEKI_URL", "http://fuseki:3030/kg")
QDRANT_URL  = os.getenv("QDRANT_URL", "http://qdrant:6333")
QCOLLECTION = os.getenv("QDRANT_COLLECTION", "docs")

_r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# replace the FUSEKI_BASE line + insert helpers
RAW_FUSEKI = os.getenv("FUSEKI_URL", "http://fuseki:3030/kg").rstrip("/")

def _fuseki_auth():
    if FUSEKI_USER and FUSEKI_PASSWORD:
        return HTTPBasicAuth(FUSEKI_USER, FUSEKI_PASSWORD)
    return None


def _fuseki_base():
    if re.search(r"/[^/]+$", RAW_FUSEKI):
        return RAW_FUSEKI
    return RAW_FUSEKI + "/kg"


# lazy client so env overrides (if any) are respected at runtime
_Q: QdrantClient | None = None
def _q() -> QdrantClient:
    global _Q
    if _Q is None:
        _Q = QdrantClient(url=QDRANT_URL, timeout=15)  # prefer HTTP; stable for Compose
    return _Q

# -------------------- Small helpers --------------------
def _doc_set(doc_id: str, **fields):
    key = f"doc:{doc_id}"
    fields.setdefault("updated_at", str(int(time.time())))
    _r.hset(key, mapping=fields)

def _progress(doc_id: str, phase: str, info: str = ""):
    _doc_set(doc_id, status=phase, info=info)

def _read_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return (extract_text(io.BytesIO(data)) or "").strip()
    return data.decode("utf-8", errors="ignore")

def _chunk_text(text: str, max_tokens: int = 450, overlap: int = 50) -> List[str]:
    # simple whitespace chunker approximating tokens by words
    words = re.findall(r"\S+", text)
    if not words:
        return []
    chunks: List[str] = []
    step = max(max_tokens - overlap, 1)
    for i in range(0, len(words), step):
        piece = " ".join(words[i:i + max_tokens]).strip()
        if piece:
            chunks.append(piece)
    return chunks

# -------------------- Triple extraction --------------------
TRIPLE_SYS = (
    "You extract knowledge graph triples from the user's text. "
    "Return 3–10 of the most salient triples only. "
    "Use normalized, compact subjects and predicates. "
    "OUTPUT FORMAT: one triple per line strictly as:\n"
    "(subject) | (predicate) | (object)\n"
    "Do not include commentary, numbering, or blank lines."
)

_PAT_EQ = re.compile(r'\b([A-Z][A-Za-z0-9 _-]{2,})\s+is\s+(an?|the)?\s*([A-Za-z0-9 _-]{2,})', re.I)
_PAT_OF = re.compile(r'\b([A-Z][A-Za-z0-9 _-]{2,})\s+of\s+([A-Z][A-Za-z0-9 _-]{2,})', re.I)

def extract_triples_llm(text: str) -> List[str]:
    """
    Ask the local LLM for triples. Keep it conservative to reduce model stress.
    """
    try:
        # shorter prompt slice + small max_tokens keeps within tiny models' ctx
        raw = complete(TRIPLE_SYS, text[:3000], max_tokens=64, temperature=0.1)
        lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
        return [ln for ln in lines if "|" in ln]
    except Exception:
        # be resilient to model hiccups
        return []

def extract_triples_rule(text: str) -> List[str]:
    triples: List[str] = []
    for m in itertools.islice(_PAT_EQ.finditer(text), 20):
        s, _, o = m.groups()
        triples.append(f"{s.strip()} | is_a | {o.strip()}")
    for m in itertools.islice(_PAT_OF.finditer(text), 20):
        a, b = m.groups()
        triples.append(f"{a.strip()} | of | {b.strip()}")
    return triples

def _sparql_insert_triples(triples: Iterable[Tuple[str, str, str]]):
    """
    Insert triples into Fuseki (simple INSERT DATA).
    """
    triples = list(triples)
    if not triples:
        return

    #update_url = f"{FUSEKI_BASE}/update"
    update_url = _fuseki_base() + "/update"

    def ex_uri(x: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", x).strip("_") or "x"
        return f"<http://example.org/{slug}>"

    def obj_form(x: str) -> str:
        if re.fullmatch(r"-?\d+(\.\d+)?", x):
            return x
        if x.startswith("http://") or x.startswith("https://"):
            return f"<{x}>"
        return '"' + x.replace('"', '\\"') + '"'

    triples_nt = [f"{ex_uri(s)} {ex_uri(p)} {obj_form(o)} ." for s, p, o in triples]
    sparql = "INSERT DATA { " + " ".join(triples_nt) + " }"

    # application/x-www-form-urlencoded with 'update' is fine for Fuseki
    #resp = requests.post(update_url, data={"update": sparql}, timeout=30)
    #resp.raise_for_status()
    resp = requests.post(update_url, data={"update": sparql}, timeout=30, auth=_fuseki_auth())
    resp.raise_for_status()

# -------------------- Qdrant helpers --------------------
def _ensure_qdrant_collection(dim: int):
    """
    Ensure collection exists with the given dimension; recreate if missing.
    """
    q = _q()
    try:
        info = q.get_collection(QCOLLECTION)
        # If size mismatches, recreate (avoid subtle 400s later).
        current_dim = None
        try:
            # qdrant_client>=1.7 exposes vectors config in info if needed;
            # otherwise just recreate to be safe when dimensions differ.
            # We keep the simple path: recreate unconditionally if needed.
            pass
        except Exception:
            pass
        # Already exists; assume correct unless you *know* it changed.
        return
    except Exception:
        # (not found or cannot fetch) -> recreate
        pass

    q.recreate_collection(
        collection_name=QCOLLECTION,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )

def _next_point_uuid(doc_id: str) -> str:
    """
    Qdrant requires id as unsigned int or UUID.
    We use a stable UUIDv5: namespace=NAMESPACE_URL, name=f"{doc_id}-{seq}".
    """
    seq = _r.incr(f"doc:{doc_id}:seq")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}-{seq}"))

def upsert_vector(doc_id: str, vector: List[float], payload: Dict[str, Any]):
    """
    Upsert a single embedding to Qdrant with a UUIDv5 point id.
    Ensures the embedding is a flat list[float].
    """
    # Normalize vector -> flat list[float]
    if isinstance(vector, list) and vector and isinstance(vector[0], list):
        vector = vector[0]
    try:
        vector = [float(x) for x in vector]
    except Exception as e:
        raise TypeError(f"Embedding must be convertible to list[float]: {e}")

    if not vector:
        raise ValueError("Empty embedding vector")

    _ensure_qdrant_collection(len(vector))
    point_id = _next_point_uuid(doc_id)

    _q().upsert(
        collection_name=QCOLLECTION,
        points=[
            qmodels.PointStruct(
                id=point_id,                 # UUID string (valid point id)
                vector=vector,
                payload={"doc_id": doc_id, **(payload or {})},
            )
        ],
        wait=True,
    )

# -------------------- Main pipeline --------------------
def process_document(filename: str, data: bytes, doc_id: str):
    """
    Ingest pipeline:
      1) parse -> chunks
      2) extract a few triples (LLM, fallback to rules) -> Fuseki
      3) embed each chunk -> Qdrant
    Writes progress to Redis at key 'doc:{doc_id}'.
    """
    _progress(doc_id, "received", filename)

    text = _read_text(filename, data)
    if not text.strip():
        _progress(doc_id, "failed", "Empty or unreadable text")
        raise ValueError("Empty or unreadable text")

    chunks = _chunk_text(text)
    _progress(doc_id, "parsed", f"chunks={len(chunks)}")

    # --- triples (sample from the first chunk; fast, avoids long contexts) ---
    triples_parsed: List[Tuple[str, str, str]] = []
    sample_text = chunks[0] if chunks else ""
    if sample_text:
        triples_text = extract_triples_llm(sample_text)
        if not triples_text:
            triples_text = extract_triples_rule(sample_text)
        for ln in triples_text:
            parts = [p.strip(" ()") for p in ln.split("|")]
            if len(parts) == 3 and all(parts):
                triples_parsed.append((parts[0], parts[1], parts[2]))

    try:
        if triples_parsed:
            _sparql_insert_triples(triples_parsed)
            _progress(doc_id, "kg_updated", f"triples={len(triples_parsed)}")
        else:
            _progress(doc_id, "kg_skipped", "no triples extracted")
    except Exception as e:
        _progress(doc_id, "kg_skipped", f"error={type(e).__name__}")

    # --- embeddings ---
    total = 0
    for ch in chunks:
        try:
            vec = embed(ch)
            # embed() must return flat list[float] or [[...]]
            if isinstance(vec, list) and vec and isinstance(vec[0], list):
                vec = vec[0]
            if not isinstance(vec, list) or (vec and not isinstance(vec[0], (float, int))):
                raise TypeError("Embedding must be a flat list[float]")
            upsert_vector(doc_id, vec, payload={"text": ch})
            total += 1
        except Exception as e:
            # keep going on individual chunk failures
            _progress(doc_id, "embed_warning", f"{type(e).__name__}: chunk_skipped")

    _progress(doc_id, "vectordb_updated", f"chunks_indexed={total}")
    _progress(doc_id, "done", "ok")
    return {"doc_id": doc_id, "triples": len(triples_parsed), "chunks": total}

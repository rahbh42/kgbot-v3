# services/common/kg_common/query.py
import os
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .llm import embed, complete

QDRANT_URL   = os.getenv("QDRANT_URL", "http://qdrant:6333")
QCOLLECTION  = os.getenv("QDRANT_COLLECTION", "docs")
TOP_K        = int(os.getenv("TOP_K", "8"))

_q = QdrantClient(url=QDRANT_URL)

QA_SYS = (
    "You answer using ONLY the provided CONTEXT. "
    "If the answer is not in the context, say: \"I don't know based on the provided documents.\" "
    "Be concise."
)

def _embed_one(text: str) -> List[float]:
    vec = embed(text)
    # normalize nested [[...]] → [...]
    if isinstance(vec, list) and vec and isinstance(vec[0], list):
        vec = vec[0]
    if not isinstance(vec, list) or (vec and not isinstance(vec[0], (float, int))):
        raise ValueError("Embedding must be a flat list[float]")
    return [float(x) for x in vec]

def search(query: str, top_k: int = TOP_K):
    v = _embed_one(query)
    # Qdrant HTTP client expects plain list[float]
    hits = _q.search(
        collection_name=QCOLLECTION,
        query_vector=v,
        limit=top_k,
        with_payload=True
    )
    return hits

def answer(question: str, top_k: int = TOP_K) -> Dict:
    hits = search(question, top_k=top_k)
    contexts: List[str] = []
    for h in hits:
        p = getattr(h, "payload", {}) or {}
        t = p.get("text")
        if isinstance(t, str) and t.strip():
            contexts.append(t.strip())
    ctx_joined = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts[:top_k]))

    user = f"CONTEXT:\n{ctx_joined}\n\nQUESTION: {question}\nANSWER:"
    out = complete(QA_SYS, user, max_tokens=192, temperature=0.1).strip()

    return {
        "question": question,
        "answer": out,
        "contexts": contexts[:top_k]
    }

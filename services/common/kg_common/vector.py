import os
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")
VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "1024"))  # adjust to your embedding size
DISTANCE = os.getenv("QDRANT_DISTANCE", "Cosine")

def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)

def ensure_collection(client: QdrantClient, name: str = QDRANT_COLLECTION, dim: int = VECTOR_SIZE):
    dist = getattr(qm.Distance, DISTANCE, qm.Distance.COSINE)
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        return
    client.recreate_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=dim, distance=dist),
    )

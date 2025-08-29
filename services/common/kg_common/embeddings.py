from sentence_transformers import SentenceTransformer
from functools import lru_cache
from .config import EMBEDDING_MODEL

@lru_cache(maxsize=1)
def get_encoder():
    return SentenceTransformer(EMBEDDING_MODEL)

def embed_texts(texts):
    model = get_encoder()
    return model.encode(texts, normalize_embeddings=True).tolist()

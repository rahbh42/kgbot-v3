import os

LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "/models/model.gguf")
LLM_CTX_SIZE = int(os.getenv("LLM_CTX_SIZE", "4096"))
LLM_N_THREADS = int(os.getenv("LLM_N_THREADS", "4"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

FUSEKI_URL = os.getenv("FUSEKI_URL", "http://fuseki:3030")
FUSEKI_DATASET = os.getenv("FUSEKI_DATASET", "kg")
SPARQL_QUERY_URL = f"{FUSEKI_URL}/{FUSEKI_DATASET}/query"
SPARQL_UPDATE_URL = f"{FUSEKI_URL}/{FUSEKI_DATASET}/update"

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "changeme")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

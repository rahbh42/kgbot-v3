# services/api/app/main.py
import os
import uuid
import logging
from typing import Optional

import redis
import requests
from requests.auth import HTTPBasicAuth

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from celery import Celery
from pydantic import BaseModel

# ensure package import path
from . import __init__ as _  # noqa: F401

# QA / RAG function
from kg_common.query import answer as answer_fn

# metrics
from time import perf_counter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client import Counter, Histogram


# -------------------- Config --------------------
API_TOKEN   = os.getenv("API_AUTH_TOKEN", "super-secret-token")
UPLOAD_DIR  = os.getenv("UPLOAD_DIR", "/ingest")
MAX_MB      = int(os.getenv("UPLOAD_MAX_MB", "50"))

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# Celery broker/backend (Redis)
BROKER_URL  = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
BACKEND_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

# Short timeouts to avoid hangs
BROKER_URL  += "?socket_connect_timeout=3&socket_timeout=3&health_check_interval=5"
BACKEND_URL += "?socket_connect_timeout=3&socket_timeout=3&health_check_interval=5"

# Fuseki config
FUSEKI_BASE    = os.getenv("FUSEKI_URL", "http://fuseki:3030")  # base host:port
FUSEKI_DATASET = os.getenv("FUSEKI_DATASET", "kg")
FUSEKI_USER    = os.getenv("FUSEKI_USER", "admin")
FUSEKI_PASS    = os.getenv("FUSEKI_PASSWORD", os.getenv("ADMIN_PASSWORD", "admin"))

# -------------------- Celery --------------------
celery = Celery("kg_worker", broker=BROKER_URL, backend=BACKEND_URL)
celery.conf.broker_connection_retry_on_startup = True
celery.conf.broker_connection_max_retries = 3
celery.conf.broker_transport_options = {"max_retries": 3, "interval_start": 0, "interval_step": 1, "interval_max": 3}
celery.conf.result_expires = 3600


# -------------------- Metrics --------------------
log = logging.getLogger("api")
REQ_COUNT = Counter("api_requests_total", "Total API requests", ["path", "method", "status"])
REQ_LAT   = Histogram("api_request_duration_seconds", "API latency", ["path", "method"])


# -------------------- App --------------------
app = FastAPI(title="KG Chatbot API", version="0.1.0")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = perf_counter()
        try:
            response = await call_next(request)
            code = response.status_code
        except Exception:
            code = 500
            raise
        finally:
            dur = (perf_counter() - start) * 1000.0
            print(f'[api] {request.method} {request.url.path} -> {code} ({dur:.1f} ms)')
        return response

app.add_middleware(AccessLogMiddleware)


def check_auth(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid token")
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return True


# -------------------- SPARQL helpers --------------------
def _sparql_query(q: str, timeout=20):
    url = f"{FUSEKI_BASE}/{FUSEKI_DATASET}/query"
    r = requests.get(url, params={"query": q}, timeout=timeout)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    return r.json() if ctype.startswith("application/sparql-results+json") else r.text

def _sparql_update(u: str, timeout=30):
    url = f"{FUSEKI_BASE}/{FUSEKI_DATASET}/update"
    auth = HTTPBasicAuth(FUSEKI_USER, FUSEKI_PASS) if FUSEKI_USER or FUSEKI_PASS else None
    r = requests.post(url, data={"update": u}, auth=auth, timeout=timeout)
    r.raise_for_status()
    return True


# -------------------- Models --------------------
class AskBody(BaseModel):
    question: str
    top_k: int = int(os.getenv("TOP_K", "8"))

class ChatBody(BaseModel):
    message: str
    top_k: int = int(os.getenv("TOP_K", "8"))


# -------------------- Routes --------------------
@app.post("/api/ask")
def ask(body: AskBody, authorization: Optional[str] = Header(None)):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "question is empty")
    t0 = perf_counter()
    try:
        out = answer_fn(q, top_k=body.top_k)
    except Exception as e:
        log.exception("ask failed")
        raise HTTPException(500, f"ask failed: {e!r}")
    dt = (perf_counter() - t0) * 1000
    print(f"[api] ASK '{q[:80]}' -> {dt:.1f} ms, ctx={len(out.get('contexts', []))}")
    return out


@app.post("/api/chat")
def chat(body: ChatBody, authorization: Optional[str] = Header(None)):
    """Compatibility endpoint: forwards to the same logic as /api/ask."""
    q = (body.message or "").strip()
    if not q:
        raise HTTPException(400, "message is empty")
    t0 = perf_counter()
    try:
        out = answer_fn(q, top_k=body.top_k)
    except Exception as e:
        log.exception("ask failed")
        raise HTTPException(500, f"ask failed: {e!r}")
    dt = (perf_counter() - t0) * 1000
    print(f"[api] CHAT '{q[:80]}' -> {dt:.1f} ms, ctx={len(out.get('contexts', []))}")
    return out


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/metrics_prom")
def metrics_prom():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/api/metrics", response_class=PlainTextResponse)
def metrics_text():
    # keep a simple text endpoint (used by some dashboards)
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), _ok: bool = Depends(check_auth)):
    allowed = (".txt", ".md", ".pdf")
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(400, f"Only {allowed} supported")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    doc_id = uuid.uuid4().hex
    safe_name = f"{doc_id}__{os.path.basename(file.filename)}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)

    # Stream to disk with size guard
    size = 0
    with open(dest_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_MB * 1024 * 1024:
                out.close()
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
                raise HTTPException(413, f"File exceeds {MAX_MB}MB limit")
            out.write(chunk)

    # Quick broker/worker sanity check
    try:
        _ = celery.control.ping(timeout=1.0)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {e}")

    # Enqueue background processing; worker signature is (filename, doc_id)
    try:
        task = celery.send_task("tasks.process_path", args=[dest_path, doc_id])
        return {"task_id": task.id, "doc_id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Queue send failed: {e}")


@app.get("/api/doc/{doc_id}")
def doc_status(doc_id: str):
    """Return ingestion status from Redis."""
    data = _r.hgetall(f"doc:{doc_id}")
    if not data:
        raise HTTPException(404, "Unknown doc_id")
    return data


@app.get("/api/graph")
def graph_overview(limit: int = 50):
    """Lightweight peek at the KG (first N triples)."""
    try:
        limit = max(1, min(int(limit), 1000))
    except Exception:
        limit = 50
    q = f"SELECT ?s ?p ?o WHERE {{ ?s ?p ?o }} LIMIT {limit}"
    try:
        data = _sparql_query(q)
        out = []
        if isinstance(data, dict) and "results" in data:
            for b in data["results"].get("bindings", []):
                s = b.get("s", {}).get("value")
                p = b.get("p", {}).get("value")
                o = b.get("o", {}).get("value")
                if s and p and o:
                    out.append([s, p, o])
        return {"triples": out, "limit": limit}
    except Exception as e:
        raise HTTPException(502, f"Fuseki error: {e}")


@app.get("/api/graph/triples")
def graph_triples(limit: int = 100):
    """Explicit triples endpoint used by the UI Graph tab."""
    try:
        limit = max(1, min(int(limit), 1000))
    except Exception:
        limit = 100
    q = f"SELECT ?s ?p ?o WHERE {{ ?s ?p ?o }} LIMIT {limit}"
    try:
        data = _sparql_query(q)
        out = []
        if isinstance(data, dict) and "results" in data:
            for b in data["results"].get("bindings", []):
                s = b.get("s", {}).get("value")
                p = b.get("p", {}).get("value")
                o = b.get("o", {}).get("value")
                if s and p and o:
                    out.append([s, p, o])
        return {"triples": out, "limit": limit}
    except Exception as e:
        raise HTTPException(502, f"Fuseki error: {e}")


@app.post("/api/graph/clear")
def graph_clear(_ok: bool = Depends(check_auth)):
    """Wipe default graph; requires admin creds if Fuseki is secured."""
    try:
        _sparql_update("CLEAR DEFAULT")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, f"Fuseki error: {e}")

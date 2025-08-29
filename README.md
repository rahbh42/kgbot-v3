# KG-Chatbot (CPU-only, Local LLMs, Dockerized, Traefik + Prometheus/Grafana + Web UI)

A production-ready reference implementation for a **Knowledge-Graph-powered chatbot** that:
- Ingests arbitrary unstructured text files (txt/md/pdf)
- Extracts entities/relations as triples (local LLM, CPU-only)
- Builds/updates an RDF knowledge graph (Apache Jena Fuseki + SPARQL)
- Indexes document snippets in a vector DB (Qdrant)
- Answers **direct** (SPARQL) and **inferential** (Hybrid RAG) questions
- **One-click** deployment with Docker Compose
- **Traefik** reverse proxy, **Prometheus/Grafana** observability, and a small **web UI**

## Quick Start

1. Install Docker + Docker Compose.
2. Put a GGUF model in `./models/model.gguf` (e.g., Llama 3.1 Instruct 8B Q4_K_M).
3. `cp .env.example .env` and set `API_AUTH_TOKEN`.
4. `docker compose up -d --build`
5. Visit:
   - **Web UI**: http://localhost/ (set your Bearer token in the UI)
   - **API docs**: http://localhost/api/docs
   - **Grafana**: http://localhost/grafana (user/pass: `admin/admin`)
   - **Prometheus**: http://localhost/prometheus
   - **Traefik dashboard**: http://localhost:8082

## Endpoints
- `POST /api/upload` (multipart): `file` (txt, md, pdf). Returns `task_id`, `doc_id`.
- `GET /api/job/{task_id}`: task state.
- `POST /api/ask`: `{ "question": "...", "top_k": 8 }` → returns `{ answer, sparql, provenance }`
- `GET /api/metrics`: Prometheus
- `GET /api/health`

## Services
- **traefik**: Reverse proxy + routing
- **fuseki**: RDF triple store (SPARQL)
- **qdrant**: Vector DB
- **redis**: Queue backend
- **api**: FastAPI app (auth, upload, ask, job status, metrics)
- **worker**: Celery worker (ingestion, triple extraction, KG+vector upserts, metrics @ :9808)
- **prometheus**, **grafana**: monitoring
- **web**: React static web UI

## Scale
```bash
docker compose up -d --scale api=3 --scale worker=4

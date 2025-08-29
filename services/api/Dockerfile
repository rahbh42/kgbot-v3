FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1


# 1) System toolchain BEFORE pip install
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build git wget curl && \
    rm -rf /var/lib/apt/lists/*

# 2) CPU-only flags for llama.cpp (API also uses model for /api/ask)
ENV CMAKE_ARGS="-DLLAMA_CUBLAS=OFF -DLLAMA_METAL=OFF -DLLAMA_CUDA=OFF -DLLAMA_CLBLAST=OFF" \
    FORCE_CMAKE=1

WORKDIR /app

# 3) Python build helpers
RUN pip install --no-cache-dir --upgrade pip setuptools wheel scikit-build-core cmake ninja

# 4) Requirements (shared)
COPY services/common/requirements.txt /app/common/requirements.txt
RUN pip install --no-cache-dir -r /app/common/requirements.txt

# 5) Shared lib + import path
COPY services/common /app/common
ENV PYTHONPATH=/app/common

# 6) API app
COPY services/api/app /app/app

# 7) Ensure package marker (defensive)
RUN python - <<'PY'
import pathlib; p = pathlib.Path("/app/app/__init__.py")
p.parent.mkdir(parents=True, exist_ok=True); p.touch()
print("api init ensured")
PY

# 8) Start API with access logs
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--access-log", "--proxy-headers", "--forwarded-allow-ips=*"]

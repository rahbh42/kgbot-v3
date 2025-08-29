FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# 1) System toolchain BEFORE pip install
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build git wget curl && \
    rm -rf /var/lib/apt/lists/*

# 2) CPU-only build flags for llama.cpp (even if a wheel is used, harmless)
ENV CMAKE_ARGS="-DLLAMA_CUBLAS=OFF -DLLAMA_METAL=OFF -DLLAMA_CUDA=OFF -DLLAMA_CLBLAST=OFF" \
    FORCE_CMAKE=1

WORKDIR /app

# 3) Python build helpers up-to-date (helps scikit-build-core find cmake/ninja)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel scikit-build-core cmake ninja

# 4) Requirements (shared)
COPY services/common/requirements.txt /app/common/requirements.txt
RUN pip install --no-cache-dir -r /app/common/requirements.txt

# 5) Shared lib + import path
COPY services/common /app/common
ENV PYTHONPATH=/app/common

# 6) Worker app
COPY services/worker/app /app/app

# 7) Ensure packages (defensive; creates __init__.py if missing)
RUN python - <<'PY'
import pathlib
for p in ["app", "../common/kg_common"]:
    f = pathlib.Path("/app")/p/"__init__.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch()
print("init files ensured")
PY

# 8) Run celery (module:attr)
CMD ["celery", "-A", "app.worker:celery_app", "worker", "--loglevel=info"]

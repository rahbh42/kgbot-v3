#!/usr/bin/env bash
set -euo pipefail

# ---------- config ----------
NAMED_VOLUMES=(fuseki-data qdrant-data grafana-data prometheus-data ingest-data)
SERVICES_UP=(traefik fuseki qdrant redis api worker web prometheus grafana)
# ----------------------------

have() { command -v "$1" >/dev/null 2>&1; }

# Pick compose command
if have docker && docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif have docker-compose; then
  COMPOSE="docker-compose"
else
  echo "❌ Neither 'docker compose' nor 'docker-compose' is installed."
  echo "   Install the Docker Compose plugin or the legacy docker-compose binary."
  exit 1
fi

echo "👉 Using: $COMPOSE"

# Sanity checks
if [[ ! -f docker-compose.yml ]]; then
  echo "❌ docker-compose.yml not found in $(pwd)"
  exit 1
fi

# Validate YAML
echo "🔎 Validating compose file..."
$COMPOSE config >/dev/null

# Optional: verify .env presence
if [[ ! -f .env ]]; then
  echo "⚠️  .env file not found. Continuing, but services may miss required env vars."
fi

# Stop stack and remove containers + anon volumes
echo "🛑 Bringing stack down..."
$COMPOSE down -v || true

# Remove named volumes (only if they exist)
echo "🧹 Removing named volumes (if present)..."
for vol in "${NAMED_VOLUMES[@]}"; do
  if docker volume inspect "$vol" >/dev/null 2>&1; then
    echo "   - removing volume: $vol"
    docker volume rm -f "$vol" >/dev/null
  else
    # sometimes compose prefixes project name; try to match and remove those too
    MATCHES=$(docker volume ls --format '{{.Name}}' | grep -E "(^|_)${vol}$" || true)
    if [[ -n "$MATCHES" ]]; then
      while IFS= read -r v; do
        echo "   - removing volume: $v"
        docker volume rm -f "$v" >/dev/null || true
      done <<< "$MATCHES"
    else
      echo "   - $vol not found, skipping"
    fi
  fi
done

# Prune build cache to force clean rebuild
echo "🧽 Pruning build cache..."
docker builder prune -af >/dev/null

# Fresh build
echo "🏗️  Building images (no cache)..."
$COMPOSE build --no-cache

# Bring up services
echo "🚀 Starting services: ${SERVICES_UP[*]} ..."
$COMPOSE up -d "${SERVICES_UP[@]}"

echo ""
echo "✅ Stack is starting. Current status:"
$COMPOSE ps
echo ""

# Quick tips
cat <<'TIP'

🔍 Useful checks:
  - Traefik dashboard:  http://localhost:8082
  - Web UI:             http://localhost/
  - API health:         curl -sS http://localhost/api/health
  - Follow logs:        docker compose logs -f traefik api worker web
  - If uploads hang:    ensure /ingest volume is mounted and worker is running:
                          docker compose ps
                          docker compose logs -f worker

If you use the legacy CLI, replace 'docker compose' with 'docker-compose' in the logs command.
TIP

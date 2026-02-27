#!/usr/bin/env bash
# Run Flask backend on the HOST (for ONVIF camera discovery).
# Use with: docker compose -f docker-compose.yml -f docker-compose.local-backend.yml up -d
# Then run this script from the project root.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
ENV_FILE="$PROJECT_ROOT/.env"

cd "$PROJECT_ROOT"

# Load .env (simple key=value, no export in file)
if [ -f "$ENV_FILE" ]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
    fi
  done < "$ENV_FILE"
fi

export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-surveillance_secure_pwd}"
export DATABASE_URL="postgresql://surveillance:${POSTGRES_PASSWORD}@localhost:5435/surveillance"
export FLASK_PORT=5002
export GO2RTC_HOST=localhost
export GO2RTC_PORT=1984

if [ ! -f "$BACKEND_DIR/app.py" ]; then
  echo "Backend not found at $BACKEND_DIR" >&2
  exit 1
fi

echo "Starting backend on http://0.0.0.0:5002 (ONVIF discovery available)"
echo "Database: localhost:5435 (ensure Postgres container is running)"
cd "$BACKEND_DIR"
exec python app.py

#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$REPO_ROOT/docker-compose.test.yml"
COMPOSE_PROJECT="trace-llmops-test"

cleanup() {
    if [ "${KEEP_TEST_DATABASE:-0}" = "1" ]; then
        echo "KEEP_TEST_DATABASE=1：保留测试 PostgreSQL 供排查。"
        return
    fi
    docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans
}

trap cleanup EXIT INT TERM

docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d --wait

export TEST_DATABASE_URL="postgresql://llmops_test:llmops_test@127.0.0.1:55432/llmops_test?client_encoding=utf8"
export SQLALCHEMY_DATABASE_URI="$TEST_DATABASE_URL"
export JWT_SECRET_KEY="integration-test-secret-key-32-bytes"
export WTF_CSRF_ENABLED="False"
export SQLALCHEMY_ECHO="False"
export REDIS_HOST="127.0.0.1"
export REDIS_PORT="1"
export WEAVIATE_HOST="127.0.0.1"
export WEAVIATE_PORT="1"
export LANGSMITH_TRACING="false"
export TRANSFORMERS_OFFLINE="1"
export HF_HUB_OFFLINE="1"

cd "$REPO_ROOT/llmops-api"
uv run flask --app app.http.app:create_app db upgrade
uv run pytest test/integration

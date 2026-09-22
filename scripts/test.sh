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

cd "$REPO_ROOT/llmops-api"
uv run --offline --no-sync python ../scripts/robustness_baseline.py migrate
uv run --offline --no-sync python ../scripts/robustness_baseline.py integration

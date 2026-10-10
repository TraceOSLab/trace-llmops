#!/usr/bin/env sh
# Run on Tencent Cloud: pull through its internal mirror, keeping Compose's tags.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

COMPOSE_IMAGES=$(docker compose -f compose.prod.yaml config --images)
BUILD_IMAGES=$(awk '$1 == "FROM" { print $2 }' llmops-api/Dockerfile llmops-web/Dockerfile)

printf '%s\n%s\n' "$COMPOSE_IMAGES" "$BUILD_IMAGES" | sort -u |
while IFS= read -r service_image; do
    case "$service_image" in
        cr.weaviate.io/semitechnologies/*)
            mirror_image="mirror.ccs.tencentyun.com/${service_image#cr.weaviate.io/}"
            ;;
        python:*|node:*|nginx:*|postgres:*|redis:*)
            mirror_image="mirror.ccs.tencentyun.com/library/${service_image}"
            ;;
        *)
            # API/web are built locally; do not pull their project tags.
            continue
            ;;
    esac
    docker pull "$mirror_image"
    docker tag "$mirror_image" "$service_image"
done

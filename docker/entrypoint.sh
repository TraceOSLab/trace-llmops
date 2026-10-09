#!/bin/bash

# 启用错误检查
set -e

# docker compose run 可执行一次性迁移、模型下载等命令。
if [[ "$#" -gt 0 ]]; then
  exec "$@"
fi

# 是否启用迁移数据 将数据库前一同步
if [[ "${MODE:-api}" == "api" && "${MIGRATION_ENABLED:-false}" == "true" ]]; then
  echo "Runnable migrations"
  flask --app app.http.app:create_app db upgrade
fi

# 检测运行模式执行不同脚本 celery / api
if [[ "${MODE:-api}" == "celery" ]]; then
  # Celery
  exec celery -A app.http.app:celery worker \
    --pool "${CELERY_WORKER_CLASS:-prefork}" \
    --concurrency "${CELERY_WORKER_AMOUNT:-1}" \
    --loglevel "${CELERY_LOG_LEVEL:-INFO}"
elif [[ "${MODE:-api}" == "api" ]]; then
  # FLASK 区分开发环境与生产环境不同脚本
  if [[ "${FLASK_ENV:-production}" == "development" ]]; then
    exec flask --app app.http.app:create_app run \
      --host="${LLMOPS_BIND_ADDRESS:-0.0.0.0}" \
      --port="${LLMOPS_PORT:-5001}" --debug
  else
    exec gunicorn \
      --bind "${LLMOPS_BIND_ADDRESS:-0.0.0.0}:${LLMOPS_PORT:-5001}" \
      --workers "${SERVER_WORKER_AMOUNT:-1}" \
      --worker-class "${SERVER_WORKER_CLASS:-gthread}" \
      --threads "${SERVER_THREAD_AMOUNT:-8}" \
      --timeout "${GUNICORN_TIMEOUT:-600}" \
      --access-logfile - \
      --error-logfile - \
      'app.http.app:create_app()'
  fi
else
  echo "Unsupported MODE: ${MODE}" >&2
  exit 1
fi

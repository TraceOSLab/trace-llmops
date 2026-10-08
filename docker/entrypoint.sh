#!/bin/bash

# 启用错误检查
set -e

# 是否启用迁移数据 将数据库前一同步
if [[ "${MIGRATION_ENABLED}" == "true" ]]; then
  echo "Runnable migrations"
  flask --app app.http.app db upgrade
fi

# 检测运行模式执行不同脚本 celery / api
if [[ "${MODE}" == "celery" ]]; then
  # Celery
  celery -A app.http.app.celery worker -P ${CELERY_WORKER_CLASS:-prefork} -C ${CELERY_WORKER_AMOUNT:-1} --loglevel WARNING
else
  # FLASK 区分开发环境与生产环境不同脚本
  if [[ "${FLASK_ENV}" == "development" ]]; then
    flask run --host=${LLMOPS_BIND_ADDRESS:-0.0.0.0} --port=${LLMOPS_PORT:5001} --debug
  else
    gunicorn \
      --bind "${LLMOPS_BIND_ADDRESS:-0.0.0.0} --port=${LLMOPS_PORT:-5001}" \
      --workers ${SERVER_WORKER_AMOUNT:-1} \
      --worker-class ${SERVER_WORKER_CLASS:-gthread} \
      --threads ${SERVER_THREAD_AMOUNT:-2} \
      --timeout ${GUNICORN_TIMEOUT:-600} \
      --preload \
      app.http.app:app
  fi
fi

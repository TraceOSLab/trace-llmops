FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.11-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy \
  UV_PYTHON_DOWNLOADS=never \
  UV_COMPILE_BYTECODE=1
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*
COPY llmops-api/pyproject.toml llmops-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
  PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  HF_HOME=/app/storage/huggingface \
  TIKTOKEN_CACHE_DIR=/app/storage/tiktoken
# 文档解析依赖：libmagic、PDF、OCR、Office；模型缓存另外准备。
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  ca-certificates libmagic1 libglib2.0-0 libgl1 libgomp1 \
  poppler-utils tesseract-ocr tesseract-ocr-chi-sim libreoffice \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --gid 10001 llmops \
  && useradd --uid 10001 --gid llmops --create-home llmops
COPY --from=build --chown=llmops:llmops /app/.venv /app/.venv
COPY --chown=llmops:llmops llmops-api/ ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
  && mkdir -p /app/storage /app/internal/core/embeddings \
  && chown -R llmops:llmops /app/storage /app/internal/core/embeddings
USER llmops
EXPOSE 5001
ENTRYPOINT ["/entrypoint.sh"]

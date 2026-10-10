FROM node:24-alpine AS build

WORKDIR /app
ENV npm_config_registry=https://mirrors.cloud.tencent.com/npm/
RUN npm install --global pnpm@11.10.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY llmops-web/package.json ./llmops-web/package.json
RUN pnpm --filter youyou-llmops-web... install --frozen-lockfile

COPY llmops-web ./llmops-web
ARG WEB_API_BASE_URL
RUN test -n "$WEB_API_BASE_URL" \
    && VITE_API_BASE_URL="$WEB_API_BASE_URL" pnpm --filter youyou-llmops-web build

FROM nginx:1.27-alpine
COPY llmops-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/llmops-web/dist /usr/share/nginx/html
EXPOSE 3000

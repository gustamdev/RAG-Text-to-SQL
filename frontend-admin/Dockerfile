# syntax=docker/dockerfile:1
# Contexto de build = raiz do repo (o admin importa components/ui e lib de ../frontend por alias).

# --- build ---
FROM node:24-alpine AS build
WORKDIR /app
# Dependências vêm do package-lock da loja; o admin usa as mesmas (node_modules compartilhado, uma só cópia do React).
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend/ ./frontend/
COPY frontend-admin/ ./frontend-admin/
RUN cd frontend-admin && ln -sfn ../frontend/node_modules node_modules && npm run build

# --- runtime ---
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY frontend-admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend-admin/dist /usr/share/nginx/html
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:8081/ >/dev/null || exit 1

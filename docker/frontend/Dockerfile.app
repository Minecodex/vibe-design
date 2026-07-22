# syntax=docker/dockerfile:1.7-labs
ARG FRONTEND_BASE_IMAGE=kakj/xscz-frontend-base:latest
FROM ${FRONTEND_BASE_IMAGE} AS dev

WORKDIR /app

COPY docker/frontend/docker-dev-entrypoint.sh /docker-dev-entrypoint.sh
RUN sed -i 's/\r$//' /docker-dev-entrypoint.sh && chmod +x /docker-dev-entrypoint.sh

EXPOSE 5173

ENTRYPOINT ["/docker-dev-entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM ${FRONTEND_BASE_IMAGE} AS builder

WORKDIR /app

COPY frontend/package*.json ./

RUN current_hash=$(sha256sum package-lock.json | awk '{print $1}') && \
    base_hash=$(cat /opt/xscz/metadata/frontend-package-lock.sha256 2>/dev/null || true) && \
    if [ "$current_hash" != "$base_hash" ]; then \
        npm install --registry=https://registry.npmmirror.com; \
    fi && \
    echo "$current_hash" > /app/node_modules/.package-lock.sha256

COPY frontend/ .

RUN npm run build

FROM nginx:1.27-alpine AS production

COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh
COPY --from=builder /app/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -qO- http://localhost/health || exit 1

CMD ["/docker-entrypoint.sh"]

# syntax=docker/dockerfile:1.7-labs
ARG BACKEND_BASE_IMAGE=kakj/xscz-backend-base:arm64-latest
FROM ${BACKEND_BASE_IMAGE} AS builder

ARG PROTECT_MODE=plain
ARG TARGETPLATFORM
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_DEFAULT_TIMEOUT=180
ARG PIP_RETRIES=10

WORKDIR /src

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/runtime ./runtime
COPY backend/setup.py ./setup.py
COPY backend/app ./app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    if [ "$PROTECT_MODE" = "secure" ]; then \
        printf '%s\n' \
            'Acquire::Retries "5";' \
            'Acquire::http::Timeout "30";' \
            'Acquire::https::Timeout "30";' \
            > /etc/apt/apt.conf.d/99mirror-retries; \
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
            printf '%s\n' \
                'Types: deb' \
                'URIs: https://mirrors.aliyun.com/debian' \
                'Suites: bookworm bookworm-updates' \
                'Components: main' \
                'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
                '' \
                'Types: deb' \
                'URIs: https://mirrors.aliyun.com/debian-security' \
                'Suites: bookworm-security' \
                'Components: main' \
                'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
                > /etc/apt/sources.list.d/debian.sources; \
        fi; \
        if [ -f /etc/apt/sources.list ]; then \
            printf '%s\n' \
                'deb https://mirrors.aliyun.com/debian bookworm main' \
                'deb https://mirrors.aliyun.com/debian bookworm-updates main' \
                'deb https://mirrors.aliyun.com/debian-security bookworm-security main' \
                > /etc/apt/sources.list; \
        fi; \
        rm -f /etc/apt/apt.conf.d/docker-clean; \
    fi

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    if [ "$PROTECT_MODE" = "secure" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends build-essential && \
        rm -rf /var/lib/apt/lists/*; \
    fi

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ "$PROTECT_MODE" = "secure" ]; then \
        python -m pip install --disable-pip-version-check --progress-bar off \
            --index-url "$PIP_INDEX_URL" \
            $(if [ -n "$PIP_EXTRA_INDEX_URL" ]; then printf -- '--extra-index-url %s' "$PIP_EXTRA_INDEX_URL"; fi) \
            --default-timeout "$PIP_DEFAULT_TIMEOUT" \
            --retries "$PIP_RETRIES" \
            Cython setuptools wheel; \
    fi

RUN if [ "$PROTECT_MODE" = "secure" ]; then \
        python setup.py build_ext --inplace && \
        python -m runtime.secure_build validate /src/app; \
    fi && \
    python -m compileall -b -f /src/app && \
    find /src -type d -name '__pycache__' -prune -exec rm -rf {} + && \
    python -m runtime.secure_build prune /src/app

FROM ${BACKEND_BASE_IMAGE} AS dev

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_DEFAULT_TIMEOUT=180
ARG PIP_RETRIES=10

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=${PIP_DEFAULT_TIMEOUT} \
    PIP_RETRIES=${PIP_RETRIES} \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libvips42 ripgrep bubblewrap file && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-dev.txt ./requirements-dev.txt
COPY backend/runtime/__init__.py ./runtime/__init__.py
COPY backend/runtime/dev_requirements_fingerprint.py ./runtime/dev_requirements_fingerprint.py
COPY backend/runtime/incremental_pip_sync.py ./runtime/incremental_pip_sync.py
COPY backend/runtime/installed_python_packages.py ./runtime/installed_python_packages.py

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pending="$(python -m runtime.incremental_pip_sync requirements.txt requirements-dev.txt)" && \
    if [ -n "$pending" ]; then \
        python -m pip install --disable-pip-version-check --progress-bar off \
            --index-url "$PIP_INDEX_URL" \
            $(if [ -n "$PIP_EXTRA_INDEX_URL" ]; then printf -- '--extra-index-url %s' "$PIP_EXTRA_INDEX_URL"; fi) \
            --default-timeout "$PIP_DEFAULT_TIMEOUT" \
            --retries "$PIP_RETRIES" \
            $pending; \
    fi && \
    python -m playwright install --with-deps chromium && \
    chown -R appuser:appgroup /ms-playwright && \
    python -m runtime.dev_requirements_fingerprint requirements.txt requirements-dev.txt > /usr/local/share/backend-dev-requirements.sha256

COPY backend/runtime ./runtime
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY docker/backend/docker-dev-entrypoint.sh /usr/local/bin/backend-dev-entrypoint

RUN sed -i 's/\r$//' /usr/local/bin/backend-dev-entrypoint && \
    chmod +x /usr/local/bin/backend-dev-entrypoint

EXPOSE 8000

ENTRYPOINT ["backend-dev-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM ${BACKEND_BASE_IMAGE} AS production

ARG PROTECT_MODE=plain
ARG TARGETPLATFORM
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_DEFAULT_TIMEOUT=180
ARG PIP_RETRIES=10

ENV APP_PROTECT_MODE=${PROTECT_MODE} \
    APP_TARGET_PLATFORM=${TARGETPLATFORM} \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libvips42 ripgrep bubblewrap file && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
COPY backend/runtime/__init__.py ./runtime/__init__.py
COPY backend/runtime/incremental_pip_sync.py ./runtime/incremental_pip_sync.py
COPY backend/runtime/installed_python_packages.py ./runtime/installed_python_packages.py

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pending="$(python -m runtime.incremental_pip_sync requirements.txt)" && \
    if [ -n "$pending" ]; then \
        python -m pip install --disable-pip-version-check --progress-bar off \
            --index-url "$PIP_INDEX_URL" \
            $(if [ -n "$PIP_EXTRA_INDEX_URL" ]; then printf -- '--extra-index-url %s' "$PIP_EXTRA_INDEX_URL"; fi) \
            --default-timeout "$PIP_DEFAULT_TIMEOUT" \
            --retries "$PIP_RETRIES" \
            $pending; \
    fi && \
    python -m playwright install --with-deps chromium && \
    chown -R appuser:appgroup /ms-playwright

COPY --from=builder --chown=appuser:appgroup /src/alembic.ini .
COPY --from=builder --chown=appuser:appgroup /src/alembic ./alembic
COPY --from=builder --chown=appuser:appgroup /src/app ./app

USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-6}"]

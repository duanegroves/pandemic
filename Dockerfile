# syntax=docker/dockerfile:1

# ---- Stage 1: build the React frontend --------------------------------------------------------
# Runs on the build machine's native platform: the output is static files, so there's no need to
# emulate arm64 here (that would be slow in CI).
FROM --platform=$BUILDPLATFORM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- Stage 2: Python server ------------------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install ".[server]"

COPY --from=web /web/dist /app/web/dist

# Run as an unprivileged user; /data holds saved rooms (mount a volume there).
RUN useradd --create-home --uid 1000 pandemic && mkdir -p /data && chown pandemic:pandemic /data
USER pandemic

ENV PANDEMIC_WEB_DIST=/app/web/dist \
    PANDEMIC_DATA_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/meta', timeout=4)"
CMD ["python", "-m", "pandemic.server", "--host", "0.0.0.0", "--port", "8000"]

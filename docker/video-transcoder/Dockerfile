# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Build the Python environment
# =============================================================================
FROM python:3.12-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies (binutils provides 'strip' to shrink .so binaries)
RUN apk add --no-cache \
    build-base \
    cargo \
    libffi-dev \
    python3-dev \
    binutils

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy only packaging metadata and source code
COPY pyproject.toml README.md ./
COPY src ./src
COPY assets ./assets

# Install the package without upgrading pip, then aggressively clean /venv
RUN pip install --no-cache-dir ".[api]" \
    # 1. Remove pip, setuptools, and wheel from the runtime venv (~20MB saved)
    && pip uninstall -y pip setuptools wheel \
    # 2. Remove all __pycache__, .pyc, and .pyo files
    && find /venv -type d -name "__pycache__" -exec rm -rf {} + \
    && find /venv -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete \
    # 3. Remove test suites and docs bundled inside third-party packages
    && find /venv -type d \( -name "tests" -o -name "test" -o -name "docs" \) -exec rm -rf {} + \
    # 4. Strip debug symbols from compiled C/Rust shared libraries (.so)
    && (find /venv -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true)


# =============================================================================
# Stage 2: Runtime image
# =============================================================================
FROM python:3.12-alpine AS runtime

ARG APP_VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Video Transcoder" \
      org.opencontainers.image.description="FFmpeg video transcoding API and web UI" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH" \
    UPLOAD_DIR=/storage/uploads \
    TEMP_DIR=/storage/temp \
    OUTPUT_DIR=/storage/outputs \
    FFMPEG_PATH=ffmpeg \
    FFPROBE_PATH=ffprobe \
    PORT=8000

# Install only runtime packages
RUN apk add --no-cache ffmpeg curl \
    && addgroup -g 1000 appuser \
    && adduser -u 1000 -G appuser -S -D -s /bin/sh appuser

# Copy the stripped virtual environment
COPY --from=builder /venv /venv

WORKDIR /app
COPY docker/video-transcoder/entrypoint.sh /app/entrypoint.sh

RUN chmod 755 /app/entrypoint.sh \
    && mkdir -p /storage/uploads /storage/outputs /storage/temp \
    && chown -R appuser:appuser /app /storage

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/readiness" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]

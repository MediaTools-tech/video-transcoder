#!/bin/sh
set -eu

mkdir -p "${UPLOAD_DIR:-/storage/uploads}" \
         "${TEMP_DIR:-/storage/temp}" \
         "${OUTPUT_DIR:-/storage/outputs}"

LOG_LEVEL=info
case "$(printf '%s' "${DEBUG:-false}" | tr '[:upper:]' '[:lower:]')" in
    true|1|yes|on) LOG_LEVEL=debug ;;
esac

exec uvicorn video_transcoder.api.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --log-level "$LOG_LEVEL" \
    --proxy-headers

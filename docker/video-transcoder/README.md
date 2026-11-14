# Video Transcoder Docker Image

The Docker image runs the headless FastAPI service and web UI. It uses the same
`src/video_transcoder/core` engine as the desktop/PyInstaller build, so codec,
audio, container, and FFmpeg behavior stay consistent between both delivery
formats.

## Quick start

The workflow publishes `ghcr.io/baladockerbytes/video-transcoder` and, when
`DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` are configured, the same image on Docker
Hub. Branch pushes get branch and commit tags; `main` also gets `latest` and a
version tag. A newly created GHCR package is private by default; change its
visibility in the package settings if anonymous pulls are required.

Pull the published image:

```bash
docker pull docker pull baladockerbytes/video-transcoder:latest
```

Run it with persistent storage:

```bash
mkdir -p storage/uploads storage/outputs storage/temp
docker run --rm -p 8000:8000 \
  -v "$(pwd)/storage:/storage" \
  baladockerbytes/video-transcoder:latest
```

Open <http://localhost:8000>. API documentation is at
<http://localhost:8000/docs> and <http://localhost:8000/redoc>.

## Build locally

From the repository root:

```bash
docker build \
  -f docker/video-transcoder/Dockerfile \
  -t video-transcoder:local \
  .
```

Or use Compose from this directory:

```bash
docker compose up --build
```

The Compose file builds from the repository root so the image always contains
the current `src/video_transcoder` code. No `.env` file is required; set any
overrides in your shell (Compose also reads a local `.env` for variable
substitution if present).

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `8000` | Container HTTP port |
| `HOST_PORT` | `8000` | Host port used by Compose |
| `DEBUG` | `false` | Enable debug mode |
| `MAX_CONCURRENT_JOBS` | `2` | Number of simultaneous FFmpeg jobs |
| `UPLOAD_DIR` | `/storage/uploads` | Uploaded source files |
| `TEMP_DIR` | `/storage/temp` | In-progress transcode files |
| `OUTPUT_DIR` | `/storage/outputs` | Finished outputs |
| `FFMPEG_PATH` | `ffmpeg` | FFmpeg executable |
| `FFPROBE_PATH` | `ffprobe` | FFprobe executable |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |

## Storage and permissions

The container runs as UID/GID `1000`. When bind-mounting a host directory on
Linux, make it writable by that user:

```bash
mkdir -p storage/uploads storage/outputs storage/temp
sudo chown -R 1000:1000 storage
```

On Docker Desktop for Windows/macOS, the default bind mount normally works
without this step.

## Operational notes

- Jobs are stored in memory. The entrypoint intentionally runs **one** Uvicorn
  worker; scaling to multiple workers or replicas requires shared job/storage
  state first.
- Uploaded, temporary, and output files live under `/storage`. Mount it as a
  volume to keep results after the container is replaced. Jobs and files stay
  until removed through the web UI's **Delete** action,
  `DELETE /api/jobs/{job_id}`, or clearing the volume. Deleting a job does not
  remove a copy already downloaded to the user's computer.
- Uploads are streamed to disk without an application-level size limit. Make
  sure the mounted storage has enough free space.
- FFmpeg is installed in the image and is not updated at container startup.
  Rebuild or pull a newer image to update FFmpeg. The runtime uses Alpine's
  FFmpeg package; verify codec availability if you depend on less common
  encoders.
- The image exposes `/api/health` and `/api/readiness` for container and
  orchestrator health checks.
- The service has no authentication. Expose it only on a trusted network or
  put an authenticating reverse proxy in front of it.

## Tests

```bash
python -m pip install -e ".[api]" httpx
PYTHONPATH=src python -m unittest tests.test_api -v
```

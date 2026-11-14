import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from video_transcoder import __version__
from video_transcoder.api.config import settings
from video_transcoder.api.routers import health, jobs, upload
from video_transcoder.api.services import storage
from video_transcoder.api.services.job_manager import job_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage.ensure_storage_dirs()
    yield
    job_manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(upload.router, prefix="/api", tags=["upload"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])

    if settings.frontend_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(settings.frontend_dir), html=True),
            name="frontend",
        )
    else:
        logger.warning("Frontend directory not found: %s", settings.frontend_dir)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("video_transcoder.api.main:app", host="0.0.0.0", port=8000)

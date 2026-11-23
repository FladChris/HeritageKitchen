import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.routing import Match, Mount

from app.api.dependencies import DbSession
from app.api.routes import (
    auth_router,
    categories_router,
    favorites_router,
    health_router,
    recipe_comments_router,
    recipe_images_router,
    recipe_ratings_router,
    recipes_router,
    settings_router,
    users_router,
)
from app.core import db, run_migrations, settings
from app.models.recipe_image_model import RecipeImage
from app.services.recipe_image_storage import retry_recipe_file_deletions
from app.services.smtp_service import revoke_invalid_test


def create_app() -> None:
    database = make_url(settings.database_url)
    logging.getLogger("uvicorn.error").info(
        "Database: %s (%s)",
        database.get_backend_name(),
        database.database if database.get_backend_name() == "sqlite" else "external",
    )
    run_migrations()
    with Session(db.engine) as session:
        revoke_invalid_test(session)
    Path(settings.recipe_images_dir).mkdir(parents=True, exist_ok=True)
    retry_recipe_file_deletions(db.engine)


async def _retry_pending_recipe_image_deletions() -> None:
    while True:
        await asyncio.sleep(60)
        await run_in_threadpool(retry_recipe_file_deletions, db.engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_app()
    cleanup = asyncio.create_task(_retry_pending_recipe_image_deletions())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url=None,
    redoc_url=None,
)
app.include_router(auth_router, prefix="/api")
app.include_router(categories_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(health_router)
app.include_router(recipe_comments_router, prefix="/api")
app.include_router(recipe_images_router, prefix="/api")
app.include_router(recipe_ratings_router, prefix="/api")
app.include_router(recipes_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(users_router, prefix="/api")

media_files = StaticFiles(directory=settings.recipe_images_dir, check_dir=False)


@app.api_route(
    f"{settings.media_url_prefix}/{{path:path}}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
async def serve_media(path: str, request: Request, db_session: DbSession) -> Response:
    parts = path.split("/")
    if any(char in path for char in "\\:\x00") or any(
        not part or part.endswith((".", " ")) for part in parts
    ):
        raise HTTPException(404)
    if parts[0] not in {"categories", "profiles"}:
        public_path = f"{settings.media_url_prefix}/{path}"
        current_image = await run_in_threadpool(
            db_session.scalar, select(RecipeImage.id).where(RecipeImage.file_path == public_path).limit(1)
        )
        if current_image is None:
            raise HTTPException(404)
    return await media_files.get_response(os.path.join(*parts), request.scope)


@app.middleware("http")
async def prevent_read_caching(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    protected_paths = (
        "/api/recipes",
        "/api/categories",
        "/api/recipe-images",
        "/api/favorites",
        "/api/settings",
        settings.media_url_prefix,
    )
    if any(path == prefix or path.startswith(f"{prefix}/") for prefix in protected_paths):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/docs")
async def scalar_docs():
    return get_scalar_api_reference(
        scalar_favicon_url="https://api.iconify.design/mdi/book-open-page-variant.svg",
    )


BACKEND_PATHS = {"api", "media", "health", "docs", "openapi.json"}


class SPAMount(Mount):
    def matches(self, scope):
        # Do not mask the router's 405 response for a real backend endpoint.
        if scope.get("path", "").strip("/").split("/", 1)[0] in BACKEND_PATHS:
            return Match.NONE, {}
        return super().matches(scope)


class SPAStaticFiles(StaticFiles):
    """Serve the build, falling back only for safe HTML navigation requests."""

    async def check_config(self) -> None:
        # Backend-only development works before the first frontend build.
        if self.directory and Path(self.directory).is_dir():
            await super().check_config()

    async def get_response(self, path: str, scope) -> Response:
        raw_path = scope.get("raw_path", b"").decode("latin-1").split("?", 1)[0]
        decoded = raw_path
        for _ in range(5):
            value = unquote(decoded)
            if value == decoded:
                break
            decoded = value
        if "\\" in decoded or ".." in decoded.split("/") or "\x00" in decoded:
            raise HTTPException(404)

        first_segment = path.strip("/").split("/", 1)[0]
        if first_segment in BACKEND_PATHS:
            raise HTTPException(404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        else:
            if path in {".", "index.html"} or path.endswith("/index.html"):
                response.headers["Cache-Control"] = "no-cache"
            if path == "service-worker.js":
                response.headers["Cache-Control"] = "no-cache"
            return response

        accept = dict(scope["headers"]).get(b"accept", b"*/*").decode("latin-1")
        if (
            scope["method"] not in {"GET", "HEAD"}
            or Path(path).suffix
            or first_segment == "_app"
            or not any(value in accept for value in ("text/html", "*/*"))
        ):
            raise HTTPException(404)
        response = await super().get_response("index.html", scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Last: registered API/media routes retain their own status codes and handlers.
app.router.routes.append(
    SPAMount(
        "/",
        app=SPAStaticFiles(
            directory=os.environ.get(
                "SPA_DIR", str(Path(__file__).resolve().parents[2] / "site" / "build")
            ),
            html=True,
            check_dir=False,
        ),
        name="spa",
    )
)

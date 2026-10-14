"""FastAPI application entrypoint for ReVolt Platform."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from src.apps.api.revolt_routes import router as revolt_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan management."""
    print("ReVolt Platform initialized successfully.")
    yield
    print("ReVolt Platform shutting down.")


def create_app() -> FastAPI:
    """Creates and configures the ReVolt FastAPI application."""
    app = FastAPI(
        title="ReVolt — AI-Powered Lithium-Ion Battery Reuse & Recycling Management Platform",
        description="Give Every Battery a Second Life. Official RMK ReVolt Platform Finalist Prototype.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Allow local CORS for testing and development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoints
    @app.get("/health", tags=["Health"])
    @app.get("/health/liveness", tags=["Health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "service": "revolt"}

    @app.get("/health/readiness", tags=["Health"])
    async def readiness() -> dict[str, str]:
        return {"status": "ready", "platform": "ReVolt"}

    # Include API routes
    app.include_router(revolt_router)

    # Static files mounting
    static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
    if not static_dir.exists():
        static_dir = Path("src/apps/web/static").resolve()

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return FileResponse("REVOLT_README.md")

    return app


app = create_app()

if __name__ == "__main__":
    import os
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.apps.api.main:app", host=host, port=port, reload=False)


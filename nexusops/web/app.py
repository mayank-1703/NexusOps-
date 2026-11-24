"""FastAPI application factory for the NexusOps Control Plane."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from nexusops.config import settings
from nexusops.protocol.transport_http import router as mcp_router
from nexusops.tools import register_all_tools
from nexusops.web.routes_api import api_router

logger = logging.getLogger("nexusops.app")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    logger.info("Initializing NexusOps Control Plane (v%s)...", settings.server_version)
    register_all_tools()
    logger.info("Registered all infrastructure tools into MCP catalog.")
    yield
    logger.info("Shutting down NexusOps Control Plane...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="NexusOps Control Plane",
        description="Autonomous AI Infrastructure Control Plane via Model Context Protocol (MCP)",
        version=settings.server_version,
        lifespan=lifespan,
    )

    # Allow cross-origin requests for web agent testing
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static assets
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Include MCP and API routes
    app.include_router(mcp_router)
    app.include_router(api_router)

    # Root route serves the Control Plane Web UI
    @app.get("/", include_in_schema=False)
    async def serve_index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"status": "NexusOps MCP Server Online", "version": settings.server_version}

    return app


app = create_app()

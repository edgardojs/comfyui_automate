"""FastAPI application entry point for the ComfyUI Sprite Character Prompt Generator."""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.history import router as history_router
from app.api.presets import router as presets_router
from app.api.prompts import router as prompts_router
from app.api.comfyui import router as comfyui_router
from app.api.characters import router as characters_router
from app.api.references import router as references_router
from app.api.training_presets import router as training_presets_router
from app.api.lora import router as lora_router
from app.api.storage import router as storage_router
from app.core.logging_config import setup_logging, set_request_id, get_request_id, clear_request_id
from app.core.rate_limiter import rate_limit_middleware
from app.db.database import init_db

# Initialize structured logging
setup_logging()

# CORS origins — configurable via CORS_ORIGINS env var (comma-separated)
# Defaults to common local dev servers
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")]

# Log level — configurable via LOG_LEVEL env var (DEBUG, INFO, WARNING, ERROR, CRITICAL)
# Defaults to INFO
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Configure root logger level
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)
logger.info("Log level set to %s", LOG_LEVEL)

# Maximum request body size (10 MB)
MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize database tables on startup."""
    await init_db()
    yield


app = FastAPI(
    title="ComfyUI Sprite Character Prompt Generator",
    description="API for generating structured positive and negative prompts for 2D game sprite character concepts.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware — applies general API rate limits (100/min)
# and adds X-RateLimit-* headers to all responses.
app.middleware("http")(rate_limit_middleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add a request ID to every request for tracing across logs."""
    # Use X-Request-ID header if provided, otherwise generate a new one
    request_id = request.headers.get("X-Request-ID") or set_request_id()
    if not request.headers.get("X-Request-ID"):
        set_request_id(request_id)

    # Add request ID to response headers
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    # Clear request ID after request completes
    clear_request_id()
    return response


@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    """Reject requests with body larger than MAX_REQUEST_BODY_SIZE.

    Checks Content-Length header first for efficiency, then also enforces
    the limit on streaming/chunked bodies by reading up to the limit.
    """
    # Fast path: check Content-Length header
    if request.headers.get("content-length"):
        try:
            content_length = int(request.headers["content-length"])
            if content_length > MAX_REQUEST_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Maximum size is {MAX_REQUEST_BODY_SIZE // (1024 * 1024)} MB."},
                )
        except (ValueError, TypeError):
            pass

    # For chunked/streaming bodies (no Content-Length), consume and enforce limit
    if not request.headers.get("content-length") and request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        if len(body) > MAX_REQUEST_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large. Maximum size is {MAX_REQUEST_BODY_SIZE // (1024 * 1024)} MB."},
            )

    return await call_next(request)

# Register API routers
app.include_router(prompts_router)
app.include_router(presets_router)
app.include_router(history_router)
app.include_router(comfyui_router)
app.include_router(characters_router)
app.include_router(references_router)
app.include_router(training_presets_router)
app.include_router(lora_router)
app.include_router(storage_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}

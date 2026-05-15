"""FastAPI application entry point for the ComfyUI Sprite Character Prompt Generator."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db

# CORS origins — configurable via CORS_ORIGINS env var (comma-separated)
# Defaults to common local dev servers
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")


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


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}

"""
MetaHarmonizer Dashboard — FastAPI Application

Main entry point. Registers all routers and initialises the database.
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import export, harmonize, mappings, ontology, quality


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database and pre-warm the ML engine on startup."""
    init_db()

    # Pre-warm SchemaMapEngine in a background thread so the server
    # starts accepting requests immediately.  The engine loads the
    # SentenceTransformer model (~90 MB) and dictionaries once;
    # subsequent /harmonize uploads reuse the cached engine.
    def _warm():
        from app.services.harmonizer import pre_warm
        pre_warm()

    t = threading.Thread(target=_warm, daemon=True)
    t.start()

    yield


app = FastAPI(
    title="MetaHarmonizer Dashboard API",
    description="Automated metadata harmonization for cBioPortal — curator review dashboard backend.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the React dev server and Docker frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(harmonize.router)
app.include_router(mappings.router)
app.include_router(quality.router)
app.include_router(export.router)
app.include_router(ontology.router)


@app.get("/", tags=["health"])
async def root():
    return {
        "service": "MetaHarmonizer Dashboard API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}

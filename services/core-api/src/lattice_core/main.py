"""Lattice core API — application factory & wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lattice_shared.logging import configure_logging

from lattice_core.config import get_settings
from lattice_core.routers import (
    audit,
    auth,
    catalog,
    change_requests,
    graph,
    importexport,
    inventory,
    items,
    locations,
    map_buildings,
    search,
    users,
)
from lattice_core.seed import init_db

logger = configure_logging("lattice_core")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database …")
    init_db()
    logger.info("Lattice core API ready.")
    yield


app = FastAPI(
    title="Lattice — Core API",
    version="0.1.0",
    description="Hierarchical hardware asset tracking: setups, assemblies and cards.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth.router,
    users.router,
    items.router,
    change_requests.router,
    inventory.router,
    locations.router,
    map_buildings.router,
    catalog.router,
    search.router,
    graph.router,
    audit.router,
    importexport.router,
):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "core-api"}

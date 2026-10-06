"""Lattice core API — application factory & wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from lattice_shared.logging import configure_logging

from lattice_core.config import get_settings
from lattice_core.errors import DomainError
from lattice_core.routers import (
    audit,
    auth,
    catalog,
    change_requests,
    documents,
    field_groups,
    graph,
    importexport,
    inventory,
    items,
    locations,
    map_buildings,
    search,
    templates,
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
    description=(
        "Hierarchical hardware asset tracking: setups, assemblies and cards, each "
        "created from a template."
    ),
    lifespan=lifespan,
)

@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    """A broken domain rule is the caller's fault, not a server fault.

    Routes used to each remember their own `except DomainError` — and the ones
    that forgot (PATCH /items among them) turned a perfectly good explanation
    like "'X' is not a known project" into a bare 500. Handling it centrally
    means a new route cannot regress this again.
    """
    content: dict = {"detail": str(exc)}
    if exc.errors:
        # Structured per-field / per-cell problems (forms, Excel import).
        content["errors"] = exc.errors
    return JSONResponse(status_code=400, content=content)


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
    templates.router,
    field_groups.router,
    items.router,
    documents.router,
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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import settings
from app.connectors import registry
from app.database import AsyncSessionLocal, engine
from app.models import *  # noqa: F401, F403  — ensures models are registered
from app.routers import chat, integrations, organizations, users


async def seed_connectors() -> None:
    """Seed the connectors table from the in-code registry."""
    from app.models.integration import Connector

    async with AsyncSessionLocal() as session:
        for connector_cls in registry.all_connectors():
            instance = connector_cls()
            seed = instance.to_seed_dict()
            existing = await session.execute(
                select(Connector).where(Connector.key == seed["key"])
            )
            if not existing.scalar_one_or_none():
                session.add(Connector(**seed))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    registry.discover()
    await seed_connectors()
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="AmbyChat API",
    version="0.1.0",
    description="Multi-tenant SaaS platform — Integration Hub & AI Chat",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api/v1")
app.include_router(organizations.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logging_config import setup_logging
from app.config import settings
from app.database import engine, init_db
from app.routers import sessions, documents, messages, knowledge
from app.services.mcp_client import mcp_file_client

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.mcp_enabled:
        try:
            await mcp_file_client.start()
        except Exception:
            # Keep non-file workflows available; the tool will retry lazily and
            # surface a normal tool error if it is called while unavailable.
            logger.exception("MCP file client failed to start")
    # Sync BM25 index from existing Chroma data (for Phase 2 → Phase 3 migration)
    try:
        from app.services.bm25_index import sync_from_chroma
        count = sync_from_chroma("knowledge_base")
        if count > 0:
            logger.info("BM25 index ready: %d chunks", count)
    except Exception:
        logger.warning("BM25 index sync failed", exc_info=True)
    try:
        yield
    finally:
        if mcp_file_client.started:
            await mcp_file_client.close()
        await engine.dispose()


app = FastAPI(
    title="ResearchMate API",
    description="智能科研助手后端 API",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(messages.router)
app.include_router(knowledge.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "ResearchMate"}

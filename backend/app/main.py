from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import sessions, documents, messages, knowledge


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Sync BM25 index from existing Chroma data (for Phase 2 → Phase 3 migration)
    try:
        from app.services.bm25_index import sync_from_chroma
        count = sync_from_chroma("knowledge_base")
        if count > 0:
            import logging
            logging.getLogger("uvicorn").info(f"BM25 index synced: {count} chunks indexed")
    except Exception:
        pass
    yield


app = FastAPI(
    title="ResearchMate API",
    description="智能科研助手后端 API",
    version="0.1.0",
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

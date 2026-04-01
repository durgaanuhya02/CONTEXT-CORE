"""ContextCore FastAPI Backend — no database required."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import query, risk, graph, audit, compliance, ingest
import db as database

app = FastAPI(title="ContextCore API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://context-core-olive.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    if database.is_enabled():
        database.init_schema()
        print("[Startup] PostgreSQL connected and schema ready")
    try:
        import chroma_store, store
        if chroma_store.is_enabled():
            count = chroma_store.get_collection_count()
            nodes = store.get_nodes()
            if count < len(nodes):
                chroma_store.index_nodes(nodes)
                print(f"[Startup] ChromaDB indexed {len(nodes)} nodes")
            else:
                print(f"[Startup] ChromaDB already has {count} nodes")
    except Exception as e:
        print(f"[Startup] ChromaDB error: {e}")

app.include_router(query.router,      prefix="/query",      tags=["Query"])
app.include_router(risk.router,       prefix="/risk",        tags=["Risk"])
app.include_router(graph.router,      prefix="/graph",       tags=["Graph"])
app.include_router(audit.router,      prefix="/audit-log",   tags=["Audit"])
app.include_router(compliance.router, prefix="/compliance",  tags=["Compliance"])
app.include_router(ingest.router,     prefix="/ingest",      tags=["Ingest"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "ContextCore", "storage": ["NetworkX/JSON", "ChromaDB", "in-memory"]}

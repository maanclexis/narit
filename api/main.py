"""NARIT Legal Graph — FastAPI entrypoint."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must come before any os.environ reads

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.db import get_driver, close_driver
from api.routers import health, statutes, cases, doctrines, procedures, firs
from api import analyze, contribute


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Neo4j connectivity on startup; close driver on shutdown."""
    get_driver().verify_connectivity()
    yield
    close_driver()


app = FastAPI(
    title="NARIT Legal Graph API",
    description="Indian Criminal Law knowledge graph — NDPS, BNS, BNSS, BSA, Limitation Act, Police Manuals",
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

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(statutes.router)
app.include_router(statutes.section_router)
app.include_router(cases.router)
app.include_router(doctrines.router)
app.include_router(procedures.router)
app.include_router(firs.router)
app.include_router(analyze.router)
app.include_router(contribute.router)

# ── Static Files ───────────────────────────────────────────────────────
# 20261024-003819 — search_aliases HITL
from api.aliases import router as _aliases_router
app.include_router(_aliases_router)

# Static SPA mount must be LAST — it's a catch-all that would shadow any
# route registered after it (this is why POST /commit/aliases 405'd).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# TEMP DEBUG
@app.get("/debug/env")
def _debug_env():
    import os
    out = {}
    for k in ["NEO4J_URI", "NEO4J_USER", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE", "GEMINI_API_KEY", "GEMINI_MODEL"]:
        v = os.getenv(k)
        out[k] = f"set(len={len(v)})" if v else "MISSING"
    try:
        from api.db import get_session
        with get_session() as s:
            r = s.run("RETURN 1 AS ok").single()
        out["neo4j_probe"] = f"OK: {r['ok']}"
    except Exception as e:
        out["neo4j_probe"] = f"FAIL: {type(e).__name__}: {str(e)[:300]}"
    return out

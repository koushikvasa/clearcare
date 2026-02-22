# main.py
# ─────────────────────────────────────────────────────
# Entry point for the ClearCare FastAPI backend.
# Creates the app, configures CORS, and registers routes.
# Run with: uvicorn main:app --reload
# ─────────────────────────────────────────────────────

from contextlib import asynccontextmanager
from fastapi import FastAPI  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]

from config import FRONTEND_URL, ENVIRONMENT, validate_config
from routes.estimate import router as estimate_router
from routes.voice import router as voice_router
from routes.image import router as image_router


# ── Lifespan ──────────────────────────────────────────
# This runs ONCE when the server starts, and ONCE when it stops.
# @asynccontextmanager makes it work with FastAPI's lifespan system.
# Everything before `yield` = startup. Everything after = shutdown.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────
    print("\n ClearCare backend starting...")
    validate_config()                          # warn if any keys missing
    print(f"Environment: {ENVIRONMENT}")
    print(f"Allowed origin: {FRONTEND_URL}")
    print("Backend ready\n")
    yield
    # ── Shutdown ──────────────────────────────────────
    print("\nClearCare backend shutting down")


# ── App instance ──────────────────────────────────────
# This is the FastAPI application object.
# title/description/version show up in the auto-generated API docs
# at http://localhost:8000/docs (free with FastAPI — very useful)
app = FastAPI(
    title="ClearCare API",
    description="AI Medicare Cost Navigator — estimates your out-of-pocket costs",
    version="1.0.0",
    lifespan=lifespan,
)


# ── CORS Middleware ───────────────────────────────────
# Middleware wraps every request/response that passes through the app.
# CORSMiddleware specifically handles cross-origin rules.
#
# allow_origins: which frontend URLs can call this backend
# allow_methods: which HTTP methods are allowed (GET, POST etc.)
# allow_headers: which request headers are allowed
# allow_credentials: whether cookies can be sent cross-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://clearcare-orpin.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],                       # allow all HTTP methods
    allow_headers=["*"],                       # allow all headers
)


# ── Routes ────────────────────────────────────────────
# include_router plugs each route file into the app.
# prefix means all routes in estimate.py will start with /api/estimate
# tags group them in the auto-generated docs at /docs
app.include_router(estimate_router, prefix="/api/estimate", tags=["Estimate"])
app.include_router(voice_router,    prefix="/api/voice",    tags=["Voice"])
app.include_router(image_router,    prefix="/api/image",    tags=["Image"])


# ── Health check ──────────────────────────────────────
# A simple endpoint Railway and Vercel use to confirm the server is alive.
# Also useful for you to test the server is running.
# GET http://localhost:8000/health → {"status": "ok"}
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ClearCare API",
        "environment": ENVIRONMENT,
        "version": "1.0.0"
    }


# ── Root ──────────────────────────────────────────────
# What you see if you visit http://localhost:8000 directly
@app.get("/")
def root():
    return {
        "message": "ClearCare API",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/health"
    }

# ── Start ─────────────────────────────────────────────
if __name__ == "__main__":
    import os
    import uvicorn  # type: ignore[reportMissingImports]
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)    
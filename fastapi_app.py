from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from rag_core import RAGEngine, InMemorySessionStore
from utils import load_settings

# ---------------------------------------------------------------------------
# Logging setup — structured logs for GCP Cloud Run
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY")  # Set this in your .env and GCP Secret Manager
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str = Security(api_key_header)):
    if not API_KEY:
        # If API_KEY is not configured at all, block everything
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: API_KEY not set."
        )
    if key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API key. Pass it as X-API-Key header."
        )


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Request / Response models with strict validation
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000,
                         description="User message (max 2000 chars)")
    session_id: Optional[str] = Field(
        None,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-]+$",   # only safe characters allowed
        description="Optional session ID. Auto-generated if not provided."
    )
    max_words_memory: int = Field(
        5000,
        ge=100,
        le=20000,
        description="Max words to retain in conversation memory (100–20000)"
    )


class ChatResponse(BaseModel):
    answer: str
    session_id: str


# ---------------------------------------------------------------------------
# Startup: load settings and initialize engine/store
# ---------------------------------------------------------------------------
def _prompt_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "prompts", "system.md")


settings = load_settings()
engine = RAGEngine(settings, prompt_path=_prompt_path())
store = InMemorySessionStore()

logger.info("RAGEngine and SessionStore initialized successfully.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Session 1 RAG API",
    description="FastAPI wrapper for the session_1 RAG engine.",
    version="0.1.0",
)

# Register rate limiter error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# CORS Middleware — restrict to your actual frontend domain
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
# Example .env entry: ALLOWED_ORIGINS=https://your-frontend.com,https://your-app.run.app
# If empty, defaults to no origins allowed (safe default)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        f"{request.method} {request.url.path} "
        f"| status={response.status_code} "
        f"| duration={duration:.3f}s "
        f"| client={request.client.host if request.client else 'unknown'}"
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handler — never leak stack traces to client
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", summary="Health check")
def health():
    """Public health check endpoint — no auth required."""
    logger.info("Health check called.")
    return {"status": "ok"}


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with the RAG engine",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")   # max 10 requests per IP per minute
def chat(req: ChatRequest, request: Request):
    """
    Send a message to the RAG engine and get a response.
    Requires X-API-Key header.
    Rate limited to 10 requests/minute per IP.
    """
    message = req.message.strip()
    # Extra safety — already validated by pydantic but belt-and-suspenders
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    # Generate server-side session ID if not provided — prevents session hijacking
    session_id = (req.session_id or "").strip() or str(uuid.uuid4())

    logger.info(f"Chat request | session_id={session_id} | message_length={len(message)}")

    history = store.get_history(session_id)

    try:
        answer = engine.ask(
            message,
            history=history,
            max_words_memory=req.max_words_memory
        )
    except Exception as e:
        logger.error(f"RAGEngine error for session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Failed to get a response from the AI engine. Please try again."
        )

    logger.info(f"Chat response | session_id={session_id} | answer_length={len(answer)}")
    return ChatResponse(answer=answer, session_id=session_id)

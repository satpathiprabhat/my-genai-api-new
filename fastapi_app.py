from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rag_core import RAGEngine, InMemorySessionStore
from utils import load_settings


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    max_words_memory: int = 5000


class ChatResponse(BaseModel):
    answer: str
    session_id: str


def _prompt_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "prompts", "system.md")


settings = load_settings()
engine = RAGEngine(settings, prompt_path=_prompt_path())
store = InMemorySessionStore()

app = FastAPI(
    title="Session 1 RAG API",
    description="FastAPI wrapper for the session_1 RAG engine.",
    version="0.1.0",
)


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, summary="Chat with the RAG engine")
def chat(req: ChatRequest):
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    session_id = (req.session_id or "default").strip() or "default"
    history = store.get_history(session_id)

    answer = engine.ask(message, history=history, max_words_memory=req.max_words_memory)
    return ChatResponse(answer=answer, session_id=session_id)

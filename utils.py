from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage


# ================================
# Settings / Env
# ================================
@dataclass(frozen=True)
class Settings:
    google_api_key: str
    file_search_store_name: str
    model_name: str = "gemini-2.5-flash"


def load_settings() -> Settings:
    load_dotenv()

    key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not (key and len(key) > 10):
        raise RuntimeError(
            "GOOGLE_API_KEY not found (or looks wrong). Put it in .env as GOOGLE_API_KEY=..."
        )

    store = (os.getenv("FILE_SEARCH_STORE_NAME") or "").strip()
    if not store:
        raise RuntimeError(
            "FILE_SEARCH_STORE_NAME not found. Put it in .env as FILE_SEARCH_STORE_NAME=fileSearchStores/..."
        )

    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    return Settings(google_api_key=key, file_search_store_name=store, model_name=model)


# ================================
# Memory helpers (keep last ~N words)
# ================================
def _count_words(msg) -> int:
    text = getattr(msg, "content", "") or ""
    if isinstance(text, list):
        text = " ".join(
            [b.get("text", "") if isinstance(b, dict) else str(b) for b in text]
        )
    return len(str(text).split())


def trim_history_to_words(
    chat_history: ChatMessageHistory,
    max_words: int = 5000,
) -> List:
    msgs = chat_history.messages
    total = 0
    kept = []
    for m in reversed(msgs):
        w = _count_words(m)
        if total + w > max_words:
            break
        kept.append(m)
        total += w
    return list(reversed(kept))


def build_transcript(past_messages: List) -> str:
    lines = []
    for m in past_messages:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        lines.append(f"{role}: {getattr(m, 'content', '')}")
    return "\n".join(lines).strip()


def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

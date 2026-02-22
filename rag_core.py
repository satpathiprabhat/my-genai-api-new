"""
Core RAG + memory engine (no FastAPI, no Gradio).

Usage (CLI test):
    python rag_core.py

Later (FastAPI):
    from rag_core import RAGEngine, InMemorySessionStore
"""

from __future__ import annotations

from typing import Dict

from google import genai
from google.genai import types

from langchain_community.chat_message_histories import ChatMessageHistory

from utils import Settings, load_settings, trim_history_to_words, build_transcript, load_prompt


# ================================
# Session store (so API can use session_id later)
# ================================
class InMemorySessionStore:
    """
    Simple in-memory store: session_id -> ChatMessageHistory
    Later you can replace this with Redis/DB without changing the engine.
    """

    def __init__(self):
        self._store: Dict[str, ChatMessageHistory] = {}

    def get_history(self, session_id: str) -> ChatMessageHistory:
        if session_id not in self._store:
            self._store[session_id] = ChatMessageHistory()
        return self._store[session_id]

    def clear(self, session_id: str) -> None:
        self._store[session_id] = ChatMessageHistory()


# ================================
# Core engine
# ================================
class RAGEngine:
    def __init__(self, settings: Settings, prompt_path: str = "prompts/system.md"):
        self.settings = settings
        self.base_prompt = load_prompt(prompt_path)

        self.client = genai.Client(api_key=settings.google_api_key)

        self.file_search_tool = types.Tool(
            file_search=types.FileSearch(
                file_search_store_names=[settings.file_search_store_name]
            )
        )

    def ask(
        self,
        question: str,
        history: ChatMessageHistory,
        max_words_memory: int = 5000,
    ) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        past = trim_history_to_words(history, max_words=max_words_memory)
        transcript = build_transcript(past)

        prompt = f"""
{self.base_prompt}

Conversation so far (UNTRUSTED):
{transcript if transcript else "(no prior context)"}

User message (UNTRUSTED):
{question}

Answer now.
""".strip()

        resp = self.client.models.generate_content(
            model=self.settings.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[self.file_search_tool],
                # thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )

        answer = (resp.text or "").strip()

        # Update memory AFTER we get the answer
        history.add_user_message(question)
        history.add_ai_message(answer)

        return answer


# ================================
# CLI sanity test (optional)
# ================================
def _cli():
    settings = load_settings()
    print("Loaded:")
    print("  GEMINI_MODEL:", settings.model_name)
    print("  STORE_NAME:", settings.file_search_store_name)
    print("  GOOGLE_API_KEY length:", len(settings.google_api_key))

    engine = RAGEngine(settings)
    history = ChatMessageHistory()

    print("\nType your question. Type 'exit' to quit.\n")
    while True:
        q = input("You: ").strip()
        if q.lower() in {"exit", "quit"}:
            break
        ans = engine.ask(q, history=history, max_words_memory=5000)
        print("\nAssistant:", ans, "\n")


if __name__ == "__main__":
    _cli()

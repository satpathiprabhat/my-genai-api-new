# CLAUDE.md — my-genai-api

## Project Overview

A RAG (Retrieval-Augmented Generation) chatbot API built with FastAPI and Google Gemini. The model uses a File Search tool to ground answers in uploaded documents. Deployed as a Docker container to a GCP VM via GitHub Actions CI/CD.

## Project Structure

```
my-genai-api/
├── fastapi_app.py          # HTTP API layer (FastAPI)
├── rag_core.py             # Core RAG engine + in-memory session store
├── utils.py                # Settings loader, memory helpers, prompt loader
├── prompts/system.md       # System prompt for the LLM
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container definition (python:3.10-slim)
└── .github/workflows/
    └── deploy.yml          # CI/CD: build → push to Docker Hub → SSH deploy to VM
```

## Architecture

- **`fastapi_app.py`**: Exposes `GET /health` and `POST /chat`. Handles API key auth (`X-API-Key` header), rate limiting (10 req/min/IP via slowapi), CORS, request logging middleware, and global exception handling.
- **`rag_core.py`**: `RAGEngine` wraps the Google Gemini client with a File Search tool. `InMemorySessionStore` maps `session_id → ChatMessageHistory` (lost on restart).
- **`utils.py`**: Loads env vars into a frozen `Settings` dataclass. `trim_history_to_words()` keeps only the most recent messages within a word budget (sliding window from the end).

## Environment Variables

Required in `.env` (never commit this file):

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key |
| `FILE_SEARCH_STORE_NAME` | Gemini file search store name (`fileSearchStores/...`) |
| `GEMINI_MODEL` | Model name (default: `gemini-2.5-flash`) |
| `API_KEY` | Secret key clients must send in `X-API-Key` header |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (e.g. `https://your-app.com`) |

## Running Locally

```bash
pip install -r requirements.txt
uvicorn fastapi_app:app --reload --port 8000
```

Test the API:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"message": "Hello", "session_id": "test-session"}'
```

## Docker

```bash
docker build -t my-genai-api .
docker run -p 8000:8000 --env-file .env my-genai-api
```

## CI/CD Pipeline

Defined in `.github/workflows/deploy.yml`. Triggers on push to `main`:
1. Builds and pushes Docker image to Docker Hub with two tags: `latest` and short git SHA
2. SSHes into the VM, pulls the new image, replaces the running container on port 80, and prunes old images

Required GitHub Secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `VM_IP`, `VM_USERNAME`, `VM_SSH_KEY`

## Key Conventions

- **Model**: Default is `gemini-2.5-flash`; override with `GEMINI_MODEL` env var
- **Session memory**: In-memory only — sessions are lost on container restart. Replace `InMemorySessionStore` with Redis/DB for persistence
- **History trimming**: Word-based sliding window from the most recent messages; default 5000 words, max 20000
- **Prompt injection protection**: Conversation history and user messages are labelled `UNTRUSTED` in the prompt; system prompt instructs the model to ignore override attempts
- **Error handling**: Stack traces are never returned to clients; all unhandled exceptions return a generic 500 message
- **Git remote**: Named `github` (not `origin`) — use `git push github main`

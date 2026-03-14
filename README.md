# AI Microservices Platform

A production-ready Python microservices platform demonstrating async architecture,
JWT authentication, LLM inference with streaming, vector search, and background task processing.

[![CI](https://github.com/mufazzalshokh/ai-microservices-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mufazzalshokh/ai-microservices-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Tests](https://img.shields.io/badge/tests-50%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Architecture

```
                        ┌─────────────┐
                        │    nginx    │  rate limiting, reverse proxy
                        └──────┬──────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌────────────────┐ ┌────────────┐ ┌─────────────────┐
     │  api-gateway   │ │ ai-service │ │document-service │
     │  :8000         │ │ :8001      │ │ :8002           │
     │                │ │            │ │                 │
     │  JWT auth      │ │ OpenAI     │ │ File upload     │
     │  register/login│ │ streaming  │ │ chunking        │
     │  token refresh │ │ SSE        │ │ pgvector search │
     └───────┬────────┘ └────────────┘ └────────┬────────┘
             │                                   │
             └──────────────┬────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
     ┌──────────────┐ ┌─────────┐ ┌────────────────┐
     │  PostgreSQL  │ │  Redis  │ │ worker-service │
     │  + pgvector  │ │         │ │                │
     │              │ │  broker │ │ Celery tasks   │
     │  users       │ │  cache  │ │ doc processing │
     │  documents   │ │         │ │ AI summaries   │
     │  vectors     │ └─────────┘ │ periodic jobs  │
     └──────────────┘             └────────────────┘
```

## Services

| Service | Port | Responsibility |
|---|---|---|
| api-gateway | 8000 | JWT auth, request routing, user management |
| ai-service | 8001 | LLM inference, streaming SSE, prompt templates |
| document-service | 8002 | File upload, text chunking, pgvector semantic search |
| worker-service | — | Celery async tasks, document processing, AI summaries |
| nginx | 80 | Rate limiting (10 req/s), reverse proxy |
| PostgreSQL + pgvector | 5432 | Persistent storage + vector embeddings |
| Redis | 6379 | Celery broker + result backend |

## Tech Stack

- **Framework**: FastAPI (async), Pydantic v2, SQLAlchemy 2.0 async
- **Auth**: JWT access tokens (30 min) + refresh token rotation (7 days), bcrypt password hashing
- **AI/LLM**: OpenAI API, streaming via Server-Sent Events, prompt template engine
- **Vector search**: pgvector with cosine similarity (`<=>` operator), text-embedding-ada-002
- **Background tasks**: Celery 5 with Redis broker, exponential retry backoff
- **Observability**: Structured JSON logging via structlog
- **Infrastructure**: Docker Compose, nginx rate limiting, pgvector extension
- **CI**: GitHub Actions — lint + 50 tests on every push

## Quick Start

### Prerequisites

- Docker Desktop
- An OpenAI API key

### 1. Clone and configure

```bash
git clone https://github.com/mufazzalshokh/ai-microservices-platform.git
cd ai-microservices-platform
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, JWT_SECRET_KEY, OPENAI_API_KEY
```

### 2. Start the stack

```bash
docker compose up --build
```

All services start with health checks. PostgreSQL initialises with pgvector extension and schema automatically.

### 3. Verify

```bash
curl http://localhost:8000/health   # api-gateway
curl http://localhost:8001/health   # ai-service
curl http://localhost:8002/health   # document-service
```

### 4. Try the API

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Password1"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Password1"}'

# Chat with LLM (use token from login)
curl -X POST http://localhost:8001/api/v1/inference/prompt \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain async/await in Python", "max_tokens": 200}'

# Streaming response
curl -X POST http://localhost:8001/api/v1/inference/prompt/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a haiku about microservices"}'

# Upload a document
curl -X POST http://localhost:8002/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@README.md"

# Semantic search
curl -X POST http://localhost:8002/api/v1/documents/search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "what is the tech stack", "top_k": 3}'
```

## API Documentation

Interactive docs available when running:

- api-gateway: http://localhost:8000/docs
- ai-service: http://localhost:8001/docs
- document-service: http://localhost:8002/docs

## Development

### Run tests locally

```bash
# Create venv
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# source .venv/bin/activate     # Linux / Mac

# Install deps
pip install -r requirements-dev.txt
pip install -e shared/

# Run all 50 tests
pytest tests/ -v
```

### Lint

```bash
ruff check .
```

## Key Design Decisions

**Why one PostgreSQL instance for all services?**
This is a development/demo setup. In production each service would own its schema with separate connection pools, enforcing bounded contexts at the DB level. The shared instance here keeps local setup simple without changing the application code patterns.

**Why Celery instead of FastAPI BackgroundTasks?**
`BackgroundTasks` runs in the same process — if the worker crashes, the task is lost. Celery tasks persist in Redis, survive restarts, retry on failure, and scale horizontally by adding workers. For document embedding (which calls OpenAI and can take 30+ seconds) this reliability matters.

**Why pgvector instead of a dedicated vector database?**
pgvector keeps the stack simple (one less service) while supporting production workloads up to tens of millions of vectors. Migrating to Pinecone or Qdrant later requires only changing `VectorStore` in document-service — the rest of the system is unaffected.

**Why refresh token rotation?**
Each refresh token is single-use. When rotated, the old token is invalidated in the DB. If an attacker steals a refresh token and uses it after the legitimate user has already refreshed, the second use is detected and both tokens are invalidated — forcing re-login.

## Project Structure

```
ai-microservices-platform/
├── api-gateway/          # FastAPI auth service
│   └── app/
│       ├── routers/      # auth, health endpoints
│       ├── services/     # AuthService (register, login, refresh, logout)
│       ├── middleware/   # JWT verification dependency
│       └── models.py     # SQLAlchemy User, RefreshToken
├── ai-service/           # LLM inference service
│   └── app/
│       ├── routers/      # inference endpoints (chat, stream, templates)
│       ├── services/     # LLMService, PromptManager
│       └── schemas.py    # ChatRequest, ChatResponse, StreamChunk
├── document-service/     # Document + vector search service
│   └── app/
│       ├── routers/      # upload, list, search endpoints
│       ├── services/     # DocumentService, VectorStore, chunker
│       └── models.py     # SQLAlchemy Document, DocumentChunk (pgvector)
├── worker-service/       # Celery async worker
│   └── app/
│       ├── tasks/        # document_tasks, ai_tasks
│       └── celery_app.py # Celery config, beat schedule
├── shared/               # Shared library (installed as package)
│   └── shared/
│       ├── auth.py       # JWT create/decode, bcrypt hashing
│       ├── models.py     # Pydantic base models, APIResponse[T]
│       ├── exceptions.py # Typed HTTP exceptions
│       └── logging.py    # structlog JSON configuration
├── infra/
│   └── init.sql          # PostgreSQL schema + pgvector setup
├── nginx/
│   └── nginx.conf        # Rate limiting, reverse proxy
├── tests/                # 50 tests, zero infrastructure required
│   ├── test_gateway/
│   ├── test_ai_service/
│   ├── test_document_service/
│   └── test_worker_service/
├── docker-compose.yml
├── .github/workflows/ci.yml
└── requirements-dev.txt
```

## License

MIT

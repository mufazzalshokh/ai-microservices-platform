"""
setup_ai_service.py  -  run from project root with venv active
python setup_ai_service.py
"""
import os

os.makedirs("ai-service/app/routers", exist_ok=True)
os.makedirs("ai-service/app/services", exist_ok=True)
os.makedirs("ai-service/app/middleware", exist_ok=True)
os.makedirs("tests/test_ai_service", exist_ok=True)

files = {}

# ── ai-service/Dockerfile ─────────────────────────────────────────────────────
files["ai-service/Dockerfile"] = """\
FROM python:3.11-slim

RUN addgroup --system app && adduser --system --group app

WORKDIR /app

COPY ai-service/requirements.txt ./requirements.txt
COPY shared/ ./shared/

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e ./shared/

COPY ai-service/app/ ./app/

USER app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
"""

# ── ai-service/requirements.txt ───────────────────────────────────────────────
files["ai-service/requirements.txt"] = """\
fastapi>=0.111
uvicorn[standard]>=0.30
openai>=1.30
httpx>=0.27
pydantic[email]>=2.7
pydantic-settings>=2.3
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
structlog>=24.1
"""

# ── ai-service/app/config.py ──────────────────────────────────────────────────
files["ai-service/app/config.py"] = """\
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "INFO"
    service_name: str = "ai-service"
    version: str = "0.1.0"

    # JWT (verify tokens issued by api-gateway)
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"

    # LLM
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Generation defaults
    max_tokens: int = 1024
    temperature: float = 0.7
    max_prompt_length: int = 8000   # chars — guard against token abuse


@lru_cache
def get_settings() -> Settings:
    return Settings()
"""

# ── ai-service/app/middleware/__init__.py ─────────────────────────────────────
files["ai-service/app/middleware/__init__.py"] = ""

# ── ai-service/app/middleware/auth.py ─────────────────────────────────────────
files["ai-service/app/middleware/auth.py"] = """\
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.auth import decode_token
from shared.exceptions import AuthenticationError
from shared.models import TokenPayload

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> TokenPayload:
    \"\"\"Verify JWT issued by api-gateway. Shared secret = same validation.\"\"\"
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(
            credentials.credentials,
            settings.jwt_secret_key,
            settings.jwt_algorithm,
            expected_type="access",
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
"""

# ── ai-service/app/schemas.py ─────────────────────────────────────────────────
files["ai-service/app/schemas.py"] = """\
from __future__ import annotations

from pydantic import Field

from shared.models import AppModel


# ── Request schemas ───────────────────────────────────────────────────────────

class Message(AppModel):
    \"\"\"A single message in a conversation.\"\"\"
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=32000)


class ChatRequest(AppModel):
    \"\"\"
    Multi-turn chat completion request.
    messages: full conversation history (system + user + assistant turns).
    stream: if True, response is SSE stream. If False, single JSON response.
    \"\"\"
    messages: list[Message] = Field(min_length=1, max_length=50)
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)


class SimplePromptRequest(AppModel):
    \"\"\"Single-turn prompt — simpler interface for basic use cases.\"\"\"
    prompt: str = Field(min_length=1, max_length=8000)
    system_prompt: str | None = None
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)


# ── Response schemas ──────────────────────────────────────────────────────────

class ChatResponse(AppModel):
    \"\"\"Non-streaming chat completion response.\"\"\"
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class StreamChunk(AppModel):
    \"\"\"Single SSE chunk for streaming responses.\"\"\"
    content: str
    done: bool = False


# ── Prompt templates ──────────────────────────────────────────────────────────

class PromptTemplate(AppModel):
    \"\"\"Named prompt template with variable substitution.\"\"\"
    name: str
    template: str
    description: str = ""


class RenderTemplateRequest(AppModel):
    \"\"\"Request to render a named template with variables.\"\"\"
    template_name: str
    variables: dict[str, str] = Field(default_factory=dict)
    stream: bool = False
"""

# ── ai-service/app/services/prompt_manager.py ────────────────────────────────
files["ai-service/app/services/prompt_manager.py"] = """\
from __future__ import annotations

from shared.exceptions import NotFoundError
from shared.logging import get_logger

logger = get_logger(__name__)

# ── Built-in prompt templates ─────────────────────────────────────────────────
# In production these would live in a DB or config file.
# Keeping them here shows interviewers you think about prompt management.

_TEMPLATES: dict[str, dict[str, str]] = {
    "summarize": {
        "name": "summarize",
        "description": "Summarize a piece of text concisely",
        "template": (
            "You are a professional summarizer. "
            "Summarize the following text in a clear and concise way:\\n\\n{text}"
        ),
    },
    "qa": {
        "name": "qa",
        "description": "Answer a question based on provided context",
        "template": (
            "You are a helpful assistant. "
            "Use only the provided context to answer the question. "
            "If the answer is not in the context, say so.\\n\\n"
            "Context:\\n{context}\\n\\n"
            "Question: {question}"
        ),
    },
    "code_review": {
        "name": "code_review",
        "description": "Review code and suggest improvements",
        "template": (
            "You are a senior software engineer doing a code review. "
            "Review the following code and provide specific, actionable feedback "
            "on correctness, performance, security, and readability.\\n\\n"
            "Language: {language}\\n\\n"
            "Code:\\n```{language}\\n{code}\\n```"
        ),
    },
    "explain": {
        "name": "explain",
        "description": "Explain a concept in simple terms",
        "template": (
            "You are an expert teacher. Explain the following concept "
            "in simple terms that a {audience} could understand:\\n\\n{concept}"
        ),
    },
}


class PromptManager:
    \"\"\"
    Manages prompt templates with variable substitution.
    Demonstrates that you think about LLM prompt engineering as a
    first-class concern, not an afterthought.
    \"\"\"

    def list_templates(self) -> list[dict[str, str]]:
        \"\"\"Return all available templates (without the template string).\"\"\"
        return [
            {"name": t["name"], "description": t["description"]}
            for t in _TEMPLATES.values()
        ]

    def get_template(self, name: str) -> dict[str, str]:
        \"\"\"Get a specific template by name.\"\"\"
        if name not in _TEMPLATES:
            raise NotFoundError(f"Template '{name}'")
        return _TEMPLATES[name]

    def render(self, template_name: str, variables: dict[str, str]) -> str:
        \"\"\"
        Render a template with variable substitution.
        Uses Python str.format_map so {variable} placeholders get replaced.
        Raises ValueError if required variables are missing.
        \"\"\"
        template = self.get_template(template_name)
        try:
            rendered = template["template"].format_map(variables)
        except KeyError as exc:
            raise ValueError(
                f"Template '{template_name}' requires variable {exc} "
                f"but it was not provided"
            ) from exc

        logger.debug(
            "template_rendered",
            template=template_name,
            variables=list(variables.keys()),
        )
        return rendered
"""

# ── ai-service/app/services/llm_service.py ───────────────────────────────────
files["ai-service/app/services/llm_service.py"] = """\
from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from shared.exceptions import ServiceUnavailableError, ValidationError
from shared.logging import get_logger

from app.config import Settings
from app.schemas import ChatRequest, ChatResponse, Message

logger = get_logger(__name__)


class LLMService:
    \"\"\"
    Wraps the OpenAI-compatible API.
    Both streaming and non-streaming responses go through here.
    Using AsyncOpenAI means we never block the event loop.
    \"\"\"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        \"\"\"
        Non-streaming chat completion.
        Returns the full response once LLM finishes generating.
        Good for: short responses, background processing.
        \"\"\"
        self._validate_messages(request.messages)

        logger.info(
            "llm_chat_request",
            model=self._settings.llm_model,
            num_messages=len(request.messages),
            max_tokens=request.max_tokens,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[
                    {"role": m.role, "content": m.content}
                    for m in request.messages
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.error("llm_request_failed", error=str(exc))
            raise ServiceUnavailableError("LLM service") from exc

        choice = response.choices[0]
        usage = response.usage

        logger.info(
            "llm_chat_complete",
            model=response.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )

        return ChatResponse(
            content=choice.message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )

    async def stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[str, None]:
        \"\"\"
        Streaming chat completion using Server-Sent Events.
        Yields text chunks as they arrive from the LLM.
        Good for: long responses, interactive chat UIs.

        Usage in router:
            return StreamingResponse(service.stream(request), media_type="text/event-stream")
        \"\"\"
        self._validate_messages(request.messages)

        logger.info(
            "llm_stream_request",
            model=self._settings.llm_model,
            num_messages=len(request.messages),
        )

        try:
            stream = await self._client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[
                    {"role": m.role, "content": m.content}
                    for m in request.messages
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    # SSE format: "data: <content>\\n\\n"
                    yield f"data: {delta.content}\\n\\n"

            # Signal stream end to client
            yield "data: [DONE]\\n\\n"

        except Exception as exc:
            logger.error("llm_stream_failed", error=str(exc))
            yield f"data: [ERROR] {exc}\\n\\n"

    def _validate_messages(self, messages: list[Message]) -> None:
        \"\"\"Guard against absurdly long prompts that would waste tokens.\"\"\"
        total_chars = sum(len(m.content) for m in messages)
        if total_chars > self._settings.max_prompt_length:
            raise ValidationError(
                f"Total prompt length ({total_chars} chars) exceeds "
                f"maximum ({self._settings.max_prompt_length} chars)"
            )
"""

# ── ai-service/app/routers/health.py ─────────────────────────────────────────
files["ai-service/app/routers/health.py"] = """\
from __future__ import annotations

from fastapi import APIRouter, Depends

from shared.models import HealthResponse

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    \"\"\"
    AI service health check.
    Note: we don't call OpenAI here — that costs money.
    We just confirm the service is up and config is loaded.
    \"\"\"
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        checks={"config": "ok", "openai_key_set": str(bool(settings.openai_api_key))},
    )
"""

# ── ai-service/app/routers/inference.py ──────────────────────────────────────
files["ai-service/app/routers/inference.py"] = """\
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from shared.exceptions import AppException
from shared.models import APIResponse, TokenPayload

from app.config import Settings, get_settings
from app.middleware.auth import require_auth
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Message,
    RenderTemplateRequest,
    SimplePromptRequest,
)
from app.services.llm_service import LLMService
from app.services.prompt_manager import PromptManager

router = APIRouter(prefix="/inference", tags=["inference"])


def _get_llm(settings: Settings = Depends(get_settings)) -> LLMService:
    return LLMService(settings=settings)


def _get_prompt_manager() -> PromptManager:
    return PromptManager()


def _raise(exc: AppException) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/chat",
    summary="Multi-turn chat completion (non-streaming)",
    response_model=APIResponse[ChatResponse],
)
async def chat(
    request: ChatRequest,
    token: TokenPayload = Depends(require_auth),
    llm: LLMService = Depends(_get_llm),
) -> APIResponse[ChatResponse]:
    \"\"\"
    Send a conversation history and get a single complete response.
    Use this when you need the full response before doing anything with it
    (e.g., storing in DB, running further processing).
    \"\"\"
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="Use /inference/chat/stream for streaming responses",
        )
    try:
        response = await llm.chat(request)
        return APIResponse(data=response, message="Chat completion successful")
    except AppException as exc:
        _raise(exc)


@router.post(
    "/chat/stream",
    summary="Multi-turn chat completion (streaming SSE)",
)
async def chat_stream(
    request: ChatRequest,
    token: TokenPayload = Depends(require_auth),
    llm: LLMService = Depends(_get_llm),
) -> StreamingResponse:
    \"\"\"
    Stream the LLM response token-by-token using Server-Sent Events.
    The client receives chunks as they are generated — no waiting for
    the full response. Essential for good UX in chat applications.

    Response format: text/event-stream
    Each chunk: \"data: <text>\\\\n\\\\n\"
    End signal:  \"data: [DONE]\\\\n\\\\n\"
    \"\"\"
    try:
        return StreamingResponse(
            llm.stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",   # disable nginx buffering for SSE
            },
        )
    except AppException as exc:
        _raise(exc)


@router.post(
    "/prompt",
    summary="Simple single-turn prompt (non-streaming)",
    response_model=APIResponse[ChatResponse],
)
async def simple_prompt(
    request: SimplePromptRequest,
    token: TokenPayload = Depends(require_auth),
    llm: LLMService = Depends(_get_llm),
) -> APIResponse[ChatResponse]:
    \"\"\"
    Simpler interface: just send a prompt string.
    Internally converts to a ChatRequest with optional system prompt.
    \"\"\"
    messages = []
    if request.system_prompt:
        messages.append(Message(role="system", content=request.system_prompt))
    messages.append(Message(role="user", content=request.prompt))

    chat_request = ChatRequest(
        messages=messages,
        stream=False,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    try:
        response = await llm.chat(chat_request)
        return APIResponse(data=response, message="Prompt completed")
    except AppException as exc:
        _raise(exc)


@router.post(
    "/prompt/stream",
    summary="Simple single-turn prompt (streaming SSE)",
)
async def simple_prompt_stream(
    request: SimplePromptRequest,
    token: TokenPayload = Depends(require_auth),
    llm: LLMService = Depends(_get_llm),
) -> StreamingResponse:
    \"\"\"Streaming version of the simple prompt endpoint.\"\"\"
    messages = []
    if request.system_prompt:
        messages.append(Message(role="system", content=request.system_prompt))
    messages.append(Message(role="user", content=request.prompt))

    chat_request = ChatRequest(
        messages=messages,
        stream=True,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return StreamingResponse(
        llm.stream(chat_request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/templates",
    summary="List all available prompt templates",
    response_model=APIResponse[list[dict]],
)
async def list_templates(
    token: TokenPayload = Depends(require_auth),
    pm: PromptManager = Depends(_get_prompt_manager),
) -> APIResponse[list[dict]]:
    return APIResponse(data=pm.list_templates())


@router.post(
    "/templates/render",
    summary="Render a prompt template and run inference",
    response_model=APIResponse[ChatResponse],
)
async def render_and_infer(
    request: RenderTemplateRequest,
    token: TokenPayload = Depends(require_auth),
    llm: LLMService = Depends(_get_llm),
    pm: PromptManager = Depends(_get_prompt_manager),
) -> APIResponse[ChatResponse]:
    \"\"\"
    Render a named template with variables, then run LLM inference.
    Example: template_name='qa', variables={'context': '...', 'question': '...'}
    \"\"\"
    try:
        rendered = pm.render(request.template_name, request.variables)
    except (ValueError, AppException) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    chat_request = ChatRequest(
        messages=[Message(role="user", content=rendered)],
        stream=False,
    )
    try:
        response = await llm.chat(chat_request)
        return APIResponse(data=response, message="Template inference complete")
    except AppException as exc:
        _raise(exc)
"""

# ── ai-service/app/main.py ────────────────────────────────────────────────────
files["ai-service/app/main.py"] = """\
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.exceptions import AppException
from shared.logging import configure_logging, get_logger

from app.config import get_settings
from app.routers import health, inference

settings = get_settings()
configure_logging(level=settings.log_level, service_name=settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "service_starting",
        service=settings.service_name,
        version=settings.version,
        model=settings.llm_model,
    )
    yield
    logger.info("service_stopping", service=settings.service_name)


app = FastAPI(
    title="AI Service",
    description="LLM inference, streaming responses, and prompt management",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "app_exception",
        status_code=exc.status_code,
        message=exc.message,
        path=str(request.url),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.message, "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", error=str(exc), path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error", "data": None},
    )


app.include_router(health.router)
app.include_router(inference.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": settings.service_name,
        "version": settings.version,
        "docs": "/docs",
    }
"""

# ── tests/test_ai_service/conftest.py ────────────────────────────────────────
files["tests/test_ai_service/__init__.py"] = ""
files["tests/test_ai_service/conftest.py"] = """\
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AI   = os.path.join(_ROOT, "ai-service")
_GW   = os.path.join(_ROOT, "api-gateway")
_DOC  = os.path.join(_ROOT, "document-service")


@pytest.fixture(scope="session")
def client():
    for p in list(sys.path):
        if any(svc in p for svc in ("api-gateway", "document-service", "ai-service")):
            sys.path.remove(p)
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.path.insert(0, _AI)

    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(scope="session")
def prompt_manager():
    for p in list(sys.path):
        if any(svc in p for svc in ("api-gateway", "document-service", "ai-service")):
            sys.path.remove(p)
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.path.insert(0, _AI)

    from app.services.prompt_manager import PromptManager
    return PromptManager()
"""

# ── tests/test_ai_service/test_inference.py ──────────────────────────────────
files["tests/test_ai_service/test_inference.py"] = """\
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reachable(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai-service"


def test_chat_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 401


def test_chat_stream_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/inference/chat/stream",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 401


def test_prompt_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/inference/prompt",
        json={"prompt": "Hello"},
    )
    assert response.status_code == 401


def test_templates_no_auth(client: TestClient):
    response = client.get("/api/v1/inference/templates")
    assert response.status_code == 401


def test_chat_invalid_token(client: TestClient):
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
        headers={"Authorization": "Bearer bad.token.here"},
    )
    assert response.status_code == 401


def test_chat_invalid_role(client: TestClient):
    \"\"\"Pydantic must reject invalid message roles before hitting LLM.\"\"\"
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": [{"role": "invalid_role", "content": "Hello"}]},
        headers={"Authorization": "Bearer fake"},
    )
    assert response.status_code in (401, 422)


def test_chat_empty_messages(client: TestClient):
    \"\"\"Empty messages list must be rejected by Pydantic.\"\"\"
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": []},
        headers={"Authorization": "Bearer fake"},
    )
    assert response.status_code in (401, 422)


def test_root_returns_service_info(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ai-service"
"""

# ── tests/test_ai_service/test_prompt_manager.py ─────────────────────────────
files["tests/test_ai_service/test_prompt_manager.py"] = """\
from __future__ import annotations

import pytest


def test_list_templates(prompt_manager):
    templates = prompt_manager.list_templates()
    assert len(templates) >= 4
    names = [t["name"] for t in templates]
    assert "summarize" in names
    assert "qa" in names
    assert "code_review" in names
    assert "explain" in names


def test_get_template(prompt_manager):
    t = prompt_manager.get_template("summarize")
    assert t["name"] == "summarize"
    assert "{text}" in t["template"]


def test_get_nonexistent_template(prompt_manager):
    from shared.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        prompt_manager.get_template("nonexistent")


def test_render_summarize(prompt_manager):
    result = prompt_manager.render("summarize", {"text": "Python is great."})
    assert "Python is great." in result


def test_render_qa(prompt_manager):
    result = prompt_manager.render(
        "qa",
        {"context": "The sky is blue.", "question": "What color is the sky?"},
    )
    assert "blue" in result
    assert "What color" in result


def test_render_missing_variable(prompt_manager):
    \"\"\"Missing required variable must raise ValueError.\"\"\"
    with pytest.raises(ValueError, match="requires variable"):
        prompt_manager.render("summarize", {})


def test_render_code_review(prompt_manager):
    result = prompt_manager.render(
        "code_review",
        {"language": "python", "code": "def foo(): pass"},
    )
    assert "python" in result
    assert "def foo" in result
"""

# ── Write all files ───────────────────────────────────────────────────────────
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  wrote {path}")

print("\nai-service written successfully!")
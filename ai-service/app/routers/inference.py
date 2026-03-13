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
    """
    Send a conversation history and get a single complete response.
    Use this when you need the full response before doing anything with it
    (e.g., storing in DB, running further processing).
    """
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
    """
    Stream the LLM response token-by-token using Server-Sent Events.
    The client receives chunks as they are generated — no waiting for
    the full response. Essential for good UX in chat applications.

    Response format: text/event-stream
    Each chunk: "data: <text>\\n\\n"
    End signal:  "data: [DONE]\\n\\n"
    """
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
    """
    Simpler interface: just send a prompt string.
    Internally converts to a ChatRequest with optional system prompt.
    """
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
    """Streaming version of the simple prompt endpoint."""
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
    """
    Render a named template with variables, then run LLM inference.
    Example: template_name='qa', variables={'context': '...', 'question': '...'}
    """
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

from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from shared.exceptions import ServiceUnavailableError, ValidationError
from shared.logging import get_logger

from app.config import Settings
from app.schemas import ChatRequest, ChatResponse, Message

logger = get_logger(__name__)


class LLMService:
    """
    Wraps the OpenAI-compatible API.
    Both streaming and non-streaming responses go through here.
    Using AsyncOpenAI means we never block the event loop.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Non-streaming chat completion.
        Returns the full response once LLM finishes generating.
        Good for: short responses, background processing.
        """
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
        """
        Streaming chat completion using Server-Sent Events.
        Yields text chunks as they arrive from the LLM.
        Good for: long responses, interactive chat UIs.

        Usage in router:
            return StreamingResponse(service.stream(request), media_type="text/event-stream")
        """
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
                    # SSE format: "data: <content>\n\n"
                    yield f"data: {delta.content}\n\n"

            # Signal stream end to client
            yield "data: [DONE]\n\n"

        except Exception as exc:
            logger.error("llm_stream_failed", error=str(exc))
            yield f"data: [ERROR] {exc}\n\n"

    def _validate_messages(self, messages: list[Message]) -> None:
        """Guard against absurdly long prompts that would waste tokens."""
        total_chars = sum(len(m.content) for m in messages)
        if total_chars > self._settings.max_prompt_length:
            raise ValidationError(
                f"Total prompt length ({total_chars} chars) exceeds "
                f"maximum ({self._settings.max_prompt_length} chars)"
            )

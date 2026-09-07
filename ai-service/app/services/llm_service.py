from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
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
                messages=_provider_messages(request.messages),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.error("llm_request_failed")
            raise ServiceUnavailableError("LLM service") from exc

        if not isinstance(response, ChatCompletion) or not response.choices:
            raise ServiceUnavailableError("LLM service")
        choice = response.choices[0]
        usage = response.usage

        logger.info(
            "llm_chat_complete",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )

        return ChatResponse(
            content=choice.message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
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
                messages=_provider_messages(request.messages),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )

            if not isinstance(stream, AsyncStream):
                raise ServiceUnavailableError("LLM service")
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    # SSE format: "data: <content>\n\n"
                    yield f"data: {delta.content}\n\n"

            # Signal stream end to client
            yield "data: [DONE]\n\n"

        except Exception:
            logger.error("llm_stream_failed")
            yield "data: [ERROR] LLM service unavailable\n\n"

    def _validate_messages(self, messages: list[Message]) -> None:
        """Guard against absurdly long prompts that would waste tokens."""
        total_chars = sum(len(m.content) for m in messages)
        if total_chars > self._settings.max_prompt_length:
            raise ValidationError(
                f"Total prompt length ({total_chars} chars) exceeds "
                f"maximum ({self._settings.max_prompt_length} chars)"
            )


def _provider_messages(messages: list[Message]) -> list[ChatCompletionMessageParam]:
    result: list[ChatCompletionMessageParam] = []
    for message in messages:
        if message.role == "system":
            result.append({"role": "system", "content": message.content})
        elif message.role == "user":
            result.append({"role": "user", "content": message.content})
        else:
            result.append({"role": "assistant", "content": message.content})
    return result

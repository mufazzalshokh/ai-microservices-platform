from __future__ import annotations

from pydantic import Field

from shared.models import AppModel


# ── Request schemas ───────────────────────────────────────────────────────────

class Message(AppModel):
    """A single message in a conversation."""
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=32000)


class ChatRequest(AppModel):
    """
    Multi-turn chat completion request.
    messages: full conversation history (system + user + assistant turns).
    stream: if True, response is SSE stream. If False, single JSON response.
    """
    messages: list[Message] = Field(min_length=1, max_length=50)
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)


class SimplePromptRequest(AppModel):
    """Single-turn prompt — simpler interface for basic use cases."""
    prompt: str = Field(min_length=1, max_length=8000)
    system_prompt: str | None = None
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)


# ── Response schemas ──────────────────────────────────────────────────────────

class ChatResponse(AppModel):
    """Non-streaming chat completion response."""
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class StreamChunk(AppModel):
    """Single SSE chunk for streaming responses."""
    content: str
    done: bool = False


# ── Prompt templates ──────────────────────────────────────────────────────────

class PromptTemplate(AppModel):
    """Named prompt template with variable substitution."""
    name: str
    template: str
    description: str = ""


class RenderTemplateRequest(AppModel):
    """Request to render a named template with variables."""
    template_name: str
    variables: dict[str, str] = Field(default_factory=dict)
    stream: bool = False

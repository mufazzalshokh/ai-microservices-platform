import asyncio
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from shared.models import APIResponse, TokenPayload

from app.config import Settings, get_settings
from app.middleware.auth import _bearer, require_scopes
from app.services.document_agent import UserDeps, create_document_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)


class AgentAnswer(BaseModel):
    answer: str


@lru_cache
def get_agent() -> Agent[UserDeps, str]:
    return create_document_agent(get_settings())


@router.post("/query", response_model=APIResponse[AgentAnswer])
async def query(
    request: AgentQuery,
    token: Annotated[
        TokenPayload,
        Depends(require_scopes("ai:agent", "mcp:invoke", "documents:read", "documents:search")),
    ],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    agent: Annotated[Agent[UserDeps, str], Depends(get_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> APIResponse[AgentAnswer]:
    try:
        async with asyncio.timeout(settings.agent_timeout_seconds):
            result = await agent.run(
                request.question,
                deps=UserDeps(credentials.credentials),
                usage_limits=UsageLimits(request_limit=6, tool_calls_limit=6),
            )
        return APIResponse(data=AgentAnswer(answer=result.output))
    except Exception:
        # SDK/provider errors can contain transport details; never return or log them.
        raise HTTPException(status_code=503, detail="Document assistant unavailable") from None

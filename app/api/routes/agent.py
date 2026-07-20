"""LangChain GM agent API routes."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agent.gm_agent import gm_agent

router = APIRouter(prefix="/agent", tags=["GM Agent"])


class AgentRequest(BaseModel):
    message: str = Field(..., description="Natural language query about roster management")
    team_context: str | None = Field(default=None, description="Optional team abbreviation for context")


class AgentResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]]
    mode: str


@router.post("/chat", response_model=AgentResponse)
async def agent_chat(request: AgentRequest) -> AgentResponse:
    result = await gm_agent.process(request.message, request.team_context)
    return AgentResponse(**result)


@router.get("/status")
async def agent_status() -> dict[str, Any]:
    return {
        "agent_available": gm_agent.is_available,
        "mode": "langchain" if gm_agent.is_available else "fallback",
        "model": getattr(gm_agent.llm, "model", None) or getattr(gm_agent.llm, "model_name", None),
        "provider": "gemini" if gm_agent.is_available else None,
    }

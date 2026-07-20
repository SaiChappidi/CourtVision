"""LangChain GM agent with tool-calling loop."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agent.tools import ALL_TOOLS
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CourtVision, an autonomous NBA General Manager AI agent.
Your role is to evaluate NBA rosters, optimize minute allocations, and project team performance.

You have access to tools that let you:
- Fetch team rosters and player stats
- Update minute allocations (must total ≤ 240 minutes per game)
- Run Monte Carlo season simulations (1000 iterations)
- Search for players
- Compare roster scenarios

When a user asks about roster changes:
1. First fetch the current roster
2. Analyze the impact of proposed changes
3. Update minute allocations if requested
4. Run a simulation to project outcomes
5. Provide clear, data-driven recommendations

Always respond with structured analysis including projected wins, playoff probability, and key insights.
Use 3-letter team abbreviations (LAL, BOS, GSW, etc.)."""


def _extract_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


class GMAgent:
    """LLM-guided agent loop for NBA roster management."""

    def __init__(self):
        self.llm = None
        self.agent = None
        if settings.gemini_api_key:
            self._initialize()

    def _initialize(self) -> None:
        self.llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
        )
        self.agent = self.llm.bind_tools(ALL_TOOLS)
        logger.info("GM Agent initialized with Gemini model %s", settings.gemini_model)

    @property
    def is_available(self) -> bool:
        return self.agent is not None

    async def process(self, user_input: str, team_context: str | None = None) -> dict[str, Any]:
        if not self.is_available:
            return await self._fallback_process(user_input, team_context)

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        if team_context:
            messages.append(SystemMessage(content=f"Current team context: {team_context}"))
        messages.append(HumanMessage(content=user_input))

        tool_calls_log: list[dict] = []
        max_iterations = 8

        try:
            for _ in range(max_iterations):
                response = await self.agent.ainvoke(messages)
                messages.append(response)

                if not response.tool_calls:
                    return {
                        "response": _extract_content(response.content),
                        "tool_calls": tool_calls_log,
                        "mode": "agent",
                    }

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_fn = next((t for t in ALL_TOOLS if t.name == tool_name), None)

                    if tool_fn:
                        try:
                            result = await tool_fn.ainvoke(tool_args)
                            tool_calls_log.append({
                                "tool": tool_name,
                                "args": tool_args,
                                "result": result[:500] if isinstance(result, str) else str(result)[:500],
                            })
                            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
                        except Exception as exc:
                            logger.error("Tool %s failed: %s", tool_name, exc)
                            messages.append(ToolMessage(content=f"Error: {exc}", tool_call_id=tool_call["id"]))

            return {
                "response": "Reached maximum agent iterations. Partial analysis completed.",
                "tool_calls": tool_calls_log,
                "mode": "agent",
            }
        except Exception as exc:
            logger.error("Gemini agent failed, using fallback: %s", exc)
            result = await self._fallback_process(user_input, team_context)
            result["response"] = (
                f"*Gemini unavailable ({exc}). Showing simulation-based analysis instead.*\n\n"
                f"{result['response']}"
            )
            return result

    async def _fallback_process(self, user_input: str, team_context: str | None = None) -> dict[str, Any]:
        """Rule-based fallback when Gemini API key is not configured."""
        from app.models.simulation import SimulationRequest
        from app.services.roster_service import roster_service
        from app.simulator.monte_carlo import simulator

        lower = user_input.lower()
        tool_calls_log: list[dict] = []

        team_abbr = team_context
        if not team_abbr:
            for abbr in ["LAL", "BOS", "GSW", "MIA", "DEN", "MIL", "PHX", "DAL", "OKC", "NYK"]:
                if abbr.lower() in lower:
                    team_abbr = abbr
                    break
            if not team_abbr:
                team_abbr = "LAL"

        chart = await roster_service.get_roster(team_abbr)
        tool_calls_log.append({"tool": "get_team_roster", "args": {"team_abbreviation": team_abbr}})

        request = SimulationRequest(team_abbreviation=team_abbr)
        result = await simulator.simulate(chart, request)
        tool_calls_log.append({"tool": "run_season_simulation", "args": {"team_abbreviation": team_abbr}})

        response = (
            f"**{result.team_name} Analysis**\n\n"
            f"- Team Rating: {result.team_rating}/100\n"
            f"- Projected Record: {result.season_projection.mean_wins:.1f}W - "
            f"{82 - result.season_projection.mean_wins:.1f}L "
            f"({result.season_projection.win_pct:.1%})\n"
            f"- Playoff Probability: {result.playoff_projection.playoff_probability:.1%}\n"
            f"- Win Range (10th-90th pctile): "
            f"{result.season_projection.percentile_10:.0f}-{result.season_projection.percentile_90:.0f} wins\n\n"
            f"Top Contributors:\n"
        )
        for p in result.roster_summary[:5]:
            response += f"  • {p['name']} ({p['position']}): {p['minutes']} min, {p['ppg']} PPG, rating {p['rating']}\n"

        return {"response": response, "tool_calls": tool_calls_log, "mode": "fallback"}


gm_agent = GMAgent()

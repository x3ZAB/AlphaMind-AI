from typing import Any

from app.llm.base import LLMStepResponse, ToolDefinition
from app.llm.errors import LLMProviderError
from app.llm.prompts import ALPHAMIND_SYSTEM_PROMPT
from app.models.llm_configuration import UserLLMConfiguration
from app.tools.registry import ToolRegistry

MAX_TOOL_CALL_ROUNDS = 5


class AIAgent:
    def __init__(
        self,
        llm_service: Any,
        tool_registry: ToolRegistry | None = None,
        system_prompt: str | None = None,
        max_rounds: int = MAX_TOOL_CALL_ROUNDS,
    ) -> None:
        self.llm_service = llm_service
        self.tool_registry = tool_registry or ToolRegistry()
        self.system_prompt = system_prompt or ALPHAMIND_SYSTEM_PROMPT
        self.max_rounds = max_rounds

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                input_schema=t.input_schema,
            )
            for t in self.tool_registry.list_tools()
        ]

    async def _call_llm_step(
        self,
        configuration: Any,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        interaction_id: str | None = None,
    ) -> LLMStepResponse:
        """Call the LLM service through its public contract, supporting generate_step and generate."""
        if hasattr(self.llm_service, "generate_step"):
            try:
                res = await self.llm_service.generate_step(
                    configuration,
                    messages,
                    tools=tools,
                    interaction_id=interaction_id,
                )
                if isinstance(res, LLMStepResponse):
                    return res
                if isinstance(res, str):
                    return LLMStepResponse(content=res, tool_calls=[])
            except (AttributeError, TypeError):
                pass

        if hasattr(self.llm_service, "generate"):
            res = await self.llm_service.generate(
                configuration,
                messages,
            )
            if isinstance(res, LLMStepResponse):
                return res
            if isinstance(res, str):
                return LLMStepResponse(content=res, tool_calls=[])

        raise LLMProviderError("LLM service does not support generate_step or generate")

    async def run(
        self,
        configuration: UserLLMConfiguration,
        user_request: str,
    ) -> str:
        tools = self._get_tool_definitions()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_request},
        ]

        interaction_id: str | None = None

        for _ in range(self.max_rounds):
            step = await self._call_llm_step(
                configuration,
                messages,
                tools=tools,
                interaction_id=interaction_id,
            )

            if step.interaction_id:
                interaction_id = step.interaction_id

            if not step.tool_calls:
                return step.content if step.content is not None else ""

            messages.append({
                "role": "assistant",
                "content": step.content,
                "tool_calls": step.tool_calls,
            })

            for call in step.tool_calls:
                tool_result = await self.tool_registry.execute(
                    call.name,
                    call.arguments,
                )

                messages.append({
                    "role": "tool",
                    "call_id": call.id,
                    "name": call.name,
                    "content": tool_result,
                })

        return "I reached the maximum number of tool execution rounds before producing a final answer. Please try simplifying your request."

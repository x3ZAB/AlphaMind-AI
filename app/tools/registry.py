from typing import Any

from app.tools.base import Tool
from app.tools.stock import GetCompanyTool, GetStockPriceTool, SearchCompanyTool


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.register(tool)
        else:
            self.register(GetStockPriceTool())
            self.register(GetCompanyTool())
            self.register(SearchCompanyTool())

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            return {"error": f"Unknown tool: '{name}'"}

        if not isinstance(arguments, dict):
            return {"error": f"Invalid arguments format for tool '{name}'. Expected dict."}

        required_fields = tool.input_schema.get("required", [])
        for field in required_fields:
            if field not in arguments or arguments[field] is None:
                return {"error": f"Missing required parameter '{field}' for tool '{name}'"}

        try:
            return await tool.execute(arguments)
        except Exception as exc:
            return {"error": f"Error executing tool '{name}': {str(exc)}"}

"""Tool registry — maps tool names to async handler functions + pydantic schemas."""
from __future__ import annotations

from typing import Any, Callable

import structlog

from core.models import ActionArgs, ToolResult

logger = structlog.get_logger()


class ToolNotFoundError(KeyError):
    pass


class ToolRegistry:
    """
    Registry of callable tools.

    Usage:
        registry.register("calendar.create_event", handler_fn, ActionArgs)
        result = await registry.execute("calendar.create_event", {"title": "...", ...})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}
        self._schemas: dict[str, type[ActionArgs]] = {}

    def register(
        self,
        name: str,
        handler: Callable,
        schema: type[ActionArgs] = ActionArgs,
    ) -> None:
        self._handlers[name] = handler
        self._schemas[name] = schema
        logger.debug("tool_registered", name=name)

    def registered_tools(self) -> list[str]:
        return sorted(self._handlers.keys())

    async def execute(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        if tool_name not in self._handlers:
            raise ToolNotFoundError(f"Unknown tool: '{tool_name}'. Available: {self.registered_tools()}")

        schema = self._schemas[tool_name]
        try:
            validated_args = schema(**args)
        except Exception as exc:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                error=f"Argument validation failed: {exc}",
                source="mock",
            )

        handler = self._handlers[tool_name]
        try:
            return await handler(validated_args)
        except Exception as exc:
            logger.error("tool_execution_failed", tool=tool_name, error=str(exc))
            return ToolResult(
                success=False,
                tool_name=tool_name,
                error=str(exc),
                source="mock",
            )


# Singleton — populated in main.py after all services are initialised
registry = ToolRegistry()

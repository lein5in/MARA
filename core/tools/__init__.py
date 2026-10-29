from dataclasses import dataclass, field
from typing import Any, Callable

from core.tools.registry import Registry, Tool, ToolResult, ToolError, READ, LOCAL, CONFIRM


@dataclass
class ToolContext:
    emit: Callable[[Any], None] = field(default=lambda event: None)
    agent: Any = None
    memory: Any = None


def build_registry() -> Registry:
    from core.tools import system_tools, app_tools, browser_tools, memory_tools, ui_tools

    reg = Registry()
    for module in (system_tools, app_tools, browser_tools, memory_tools, ui_tools):
        module.register(reg)
    return reg


__all__ = ["Registry", "Tool", "ToolResult", "ToolError", "ToolContext", "build_registry", "READ", "LOCAL", "CONFIRM"]

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.log import get_logger
log = get_logger(__name__)

READ = "read"
LOCAL = "local"
CONFIRM = "confirm"
RISK_LEVELS = (READ, LOCAL, CONFIRM)


@dataclass
class ToolResult:
    ok: bool
    content: Any
    summary: str = ""
    duration: float = 0.0
    untrusted: bool = False
    label: str = ""


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    properties: dict = field(default_factory=dict)
    required: list = field(default_factory=list)
    risk: str = READ
    confirm_text: Callable[[dict], tuple[str, str]] | None = None
    untrusted_output: bool = False
    summarize: Callable[[dict], str] | None = None

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.required),
            },
        }

    def confirmation(self, args: dict) -> tuple[str, str]:
        if self.confirm_text:
            return self.confirm_text(args)
        return self.name.replace("_", " ").capitalize(), "MARA wants to run this action."

    def args_summary(self, args: dict) -> str:
        if self.summarize:
            return self.summarize(args)
        parts = []
        for key, value in args.items():
            text = str(value).replace("\n", " ")
            if len(text) > 40:
                text = text[:37] + "..."
            parts.append(f"{key}={text}")
        return " ".join(parts)


class ToolError(Exception):
    pass


class Registry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.risk not in RISK_LEVELS:
            raise ValueError(f"Unknown risk level for {tool.name}: {tool.risk}")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def tool(self, name: str, description: str, properties: dict | None = None,
             required: list | None = None, risk: str = READ, **kwargs):
        def decorator(fn):
            self.register(Tool(name, description, fn, properties or {}, required or [], risk, **kwargs))
            return fn
        return decorator

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def get_schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def execute(self, name: str, args: dict, ctx: Any = None) -> ToolResult:
        start = time.perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, f"Error: unknown tool '{name}'.", "unknown tool", 0.0)
        try:
            output = tool.handler(ctx, **(args or {}))
            ok = True
        except ToolError as e:
            output, ok = f"Error: {e}", False
        except TypeError as e:
            log.warning(f"[Tool] {name} bad arguments: {e}")
            output, ok = f"Error: invalid arguments for {name}: {e}", False
        except Exception as e:
            log.exception(f"[Tool] {name} failed")
            output, ok = f"Error: {name} failed: {type(e).__name__}: {e}", False
        duration = time.perf_counter() - start
        if isinstance(output, ToolResult):
            output.duration = duration
            output.untrusted = output.untrusted or tool.untrusted_output
            return output
        if output is None:
            output = "Done."
        summary = output if isinstance(output, str) else ""
        return ToolResult(ok, output, summary[:120], duration, tool.untrusted_output and ok)

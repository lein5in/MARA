import pytest

from core.tools import build_registry, ToolContext
from core.tools.registry import Registry, Tool, ToolError, READ, LOCAL, CONFIRM


def test_all_schemas_are_valid():
    reg = build_registry()
    names = set()
    for schema in reg.get_schemas():
        assert set(schema) == {"name", "description", "input_schema"}
        assert schema["name"] not in names
        names.add(schema["name"])
        assert schema["description"].strip()
        assert schema["input_schema"]["type"] == "object"
        for req in schema["input_schema"]["required"]:
            assert req in schema["input_schema"]["properties"]
    for expected in ("get_time", "pause_mara", "open_app", "kill_process", "browser_read", "remember",
                     "reset_memory", "reset_conversation", "show_visual", "quit_mara", "set_silent", "set_vision"):
        assert expected in names


def test_risk_levels():
    reg = build_registry()
    assert all(reg.get(n).risk in (READ, LOCAL, CONFIRM) for n in reg.names())
    for name in ("kill_process", "reset_memory", "browser_delete_credentials"):
        assert reg.get(name).risk == CONFIRM
    for name in ("get_time", "get_volume", "wifi_status", "recall_memory", "find_files"):
        assert reg.get(name).risk == READ
    with pytest.raises(ValueError):
        Registry().register(Tool("x", "x", lambda ctx: None, risk="dangerous"))


def test_unknown_tool_is_error_result():
    result = Registry().execute("nope", {}, ToolContext())
    assert not result.ok and "unknown tool" in result.content


def test_handler_exception_becomes_error_result():
    reg = Registry()

    @reg.tool("boom", "explodes")
    def boom(ctx):
        raise RuntimeError("kaboom")

    @reg.tool("refuse", "tool error")
    def refuse(ctx):
        raise ToolError("not allowed")

    result = reg.execute("boom", {}, ToolContext())
    assert not result.ok and "kaboom" in result.content and result.duration >= 0
    result = reg.execute("refuse", {}, ToolContext())
    assert not result.ok and result.content == "Error: not allowed"


def test_bad_arguments_become_error_result():
    reg = Registry()

    @reg.tool("echo", "echo", {"text": {"type": "string"}}, ["text"])
    def echo(ctx, text):
        return text

    assert reg.execute("echo", {"text": "hi"}, ToolContext()).content == "hi"
    result = reg.execute("echo", {"wrong": 1}, ToolContext())
    assert not result.ok and "invalid arguments" in result.content


def test_duplicate_registration_rejected():
    reg = Registry()
    reg.register(Tool("a", "a", lambda ctx: None))
    with pytest.raises(ValueError):
        reg.register(Tool("a", "a", lambda ctx: None))


def test_untrusted_flag():
    reg = Registry()
    reg.register(Tool("read_web", "web", lambda ctx: "page", untrusted_output=True))
    assert reg.execute("read_web", {}, ToolContext()).untrusted

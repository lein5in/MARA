import io

from core.brain import Agent
from core.cli import Console
from core.tools import build_registry
from tests.fakes import FakeAnthropic, FakeMemory, tool_call, reply


def test_console_prints_and_confirms(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])
    out = io.StringIO()
    console = Console(out=out, ask=lambda prompt: "n")
    agent = Agent(client=FakeAnthropic([tool_call("kill_process", {"process": "a.exe"}, "Closing it."), reply("Kept it open.")]),
                  registry=build_registry(), memory=FakeMemory(), emit=console.handle, broker=console.broker,
                  background=False)
    agent.run_turn("close a")
    text = out.getvalue()
    assert "Closing it." in text and "Close application" in text and "kill_process" in text
    assert "Kept it open." in text

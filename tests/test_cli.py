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




def test_slow_console_confirmation_does_not_trip_watchdog(monkeypatch):
    import time
    import psutil
    from core.events import Error
    killed = []

    class _Proc:
        info = {"name": "a.exe"}

        def terminate(self):
            killed.append(True)

    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [_Proc()])
    out = io.StringIO()
    errors = []

    def slow_yes(prompt):
        time.sleep(0.6)
        return "y"

    console = Console(out=out, ask=slow_yes)

    def emit(event):
        if isinstance(event, Error):
            errors.append(event)
        console.handle(event)

    agent = Agent(client=FakeAnthropic([tool_call("kill_process", {"process": "a.exe"}), reply("Closed it.")]),
                  registry=build_registry(), memory=FakeMemory(), emit=emit, broker=console.broker,
                  background=False)
    agent.watchdog_timeout = 0.3
    agent.run_turn("close a")
    assert errors == []
    assert killed == [True]
    assert "Closed it." in out.getvalue()
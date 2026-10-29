from datetime import datetime, timedelta

import anthropic
import httpx
import pytest

from core import system
from core.brain import Agent, ConfirmationBroker, validate_history, trim_history
from core.events import (
    TextDelta, ToolStarted, ToolFinished, ConfirmationRequested, Visual, Error, Done,
    QuitRequested, ConversationReset,
)
from core.tools import build_registry
from tests.fakes import FakeAnthropic, FakeMemory, reply, tool_call, fail


def make_agent(*script, broker=None, **kwargs):
    events = []
    client = FakeAnthropic(script)
    agent = Agent(client=client, registry=kwargs.pop("registry", None) or build_registry(), memory=FakeMemory(),
                  emit=events.append, broker=broker, background=False, **kwargs)
    return agent, client, events


def sent_messages(client, call=-1):
    return client.messages.calls[call]["messages"]


def flat_text(messages):
    out = []
    for m in messages:
        content = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for b in content:
            out.append(b.get("text") or str(b.get("content", "")) or b.get("name", ""))
    return " | ".join(out)


def connection_error():
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


@pytest.fixture
def volume(monkeypatch):
    state = {"level": 0}
    monkeypatch.setattr(system, "set_volume", lambda level: state.__setitem__("level", max(0, min(100, int(level)))) or state["level"])
    return state


def test_summary_after_visual():
    agent, client, events = make_agent(
        tool_call("show_visual", {"html": "<html><body>chart</body></html>", "title": "Sales"}),
        reply("Here is the chart."),
        reply("You asked for a sales chart and I showed it."),
    )
    agent.run_turn("Show me a sales chart")
    assert any(isinstance(e, Visual) and e.title == "Sales" for e in events)
    agent.run_turn("Résume ce qu'on a dit")
    text = flat_text(sent_messages(client))
    assert "Show me a sales chart" in text and "show_visual" in text and "Here is the chart." in text
    assert validate_history(agent.history) == []


def test_summary_after_reset():
    agent, client, events = make_agent(
        reply("Hello sir."),
        tool_call("reset_conversation"),
        reply("Fresh start."),
        reply("We have not said anything yet."),
    )
    agent.run_turn("Hello")
    agent.run_turn("Start a new conversation")
    assert any(isinstance(e, ConversationReset) for e in events)
    assert agent.history == []
    agent.run_turn("Résume ce qu'on a dit")
    assert sent_messages(client) == [{"role": "user", "content": [{"type": "text", "text": "Résume ce qu'on a dit"}]}]


def test_summary_after_action(volume):
    agent, client, events = make_agent(
        tool_call("set_volume", {"level": 40}, "Setting it now."),
        reply("Volume is at forty."),
        reply("You asked me to set the volume to forty and I did."),
    )
    agent.run_turn("Volume to forty")
    assert volume["level"] == 40
    agent.run_turn("Summarise what we did")
    text = flat_text(sent_messages(client))
    assert "Volume set to 40%." in text and "Volume is at forty." in text
    assert [e.text for e in events if isinstance(e, TextDelta)][:3] == ["Setting it now.", " ", "Volume is at forty."]
    assert validate_history(agent.history) == []


def test_time_in_another_city():
    agent, client, events = make_agent(
        tool_call("get_time", {"timezone": "Asia/Tokyo"}),
        reply("It's evening in Tokyo."),
    )
    agent.run_turn("Quelle heure est-il à Tokyo ?")
    result = sent_messages(client)[-1]["content"][0]
    assert result["type"] == "tool_result" and "Asia/Tokyo" in result["content"]
    assert not result.get("is_error")


def test_pause_until_9pm():
    now = datetime.now().astimezone()
    target = now.replace(hour=21, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    agent, client, events = make_agent(
        tool_call("pause_mara", {"until": target.replace(tzinfo=None).isoformat()}),
        reply("I'll be back at nine."),
    )
    agent.run_turn("Leave me alone until 9pm")
    assert datetime.fromisoformat(agent.memory.get_pause()) == target
    assert system.is_paused(agent.memory)
    system.cancel_pause(agent.memory)


def test_quite_does_not_quit():
    agent, client, events = make_agent(reply("Glad you think so."), tool_call("quit_mara"), reply("Goodbye."))
    agent.run_turn("That's quite interesting, I won't quit now")
    assert not any(isinstance(e, QuitRequested) for e in events)
    agent.run_turn("Shut down MARA")
    assert any(isinstance(e, QuitRequested) for e in events)


def test_network_error_mid_stream_keeps_history_valid():
    agent, client, events = make_agent(
        fail(connection_error(), "Let me check"),
        reply("Here you go."),
    )
    agent.run_turn("What's up?")
    errors = [e for e in events if isinstance(e, Error)]
    assert errors and "internet" in errors[0].message
    assert validate_history(agent.history) == []
    assert "interrupted" in agent.history[-1]["content"][0]["text"]
    agent.run_turn("Try again")
    assert validate_history(agent.history) == []
    assert agent.history[-1]["content"][0]["text"] == "Here you go."


def test_error_after_tool_keeps_pairs(volume):
    agent, client, events = make_agent(
        tool_call("set_volume", {"level": 10}),
        fail(connection_error()),
        reply("OK."),
    )
    agent.run_turn("Volume ten")
    assert validate_history(agent.history) == []
    agent.run_turn("And now?")
    assert validate_history(agent.history) == []


def test_iteration_cap(volume):
    agent, client, events = make_agent(
        tool_call("get_time"), tool_call("get_time"), reply("I stopped there."),
        max_iterations=2,
    )
    agent.run_turn("Loop forever")
    assert len(client.messages.calls) == 3
    assert client.messages.calls[2]["tool_choice"] == {"type": "none"}
    assert "tool_choice" not in client.messages.calls[0]
    assert validate_history(agent.history) == []


def test_iteration_cap_when_model_still_calls_tools():
    agent, client, events = make_agent(tool_call("get_time"), tool_call("get_time"), max_iterations=1)
    agent.run_turn("Loop")
    assert validate_history(agent.history) == []
    assert "iteration limit" in flat_text(agent.history)


def _kill_setup(monkeypatch):
    killed = []

    class Proc:
        info = {"name": "spotify.exe"}

        def terminate(self):
            killed.append(True)
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [Proc()])
    return killed


@pytest.mark.parametrize("answer", [True, False])
def test_confirmation(monkeypatch, answer):
    killed = _kill_setup(monkeypatch)
    broker = ConfirmationBroker()
    agent, client, events = make_agent(
        tool_call("kill_process", {"process": "spotify.exe"}),
        reply("Done." if answer else "Okay, I left it open."),
        broker=broker,
    )
    agent.emit = lambda e: (events.append(e), isinstance(e, ConfirmationRequested) and broker.resolve(answer, e.id))
    agent.run_turn("Close Spotify")
    request = next(e for e in events if isinstance(e, ConfirmationRequested))
    assert request.tool == "kill_process" and request.args == {"process": "spotify.exe"}
    result = sent_messages(client)[-1]["content"][0]
    if answer:
        assert killed and "Closed 1" in result["content"]
    else:
        assert not killed and "Cancelled by the user" in result["content"] and result["is_error"]
    assert validate_history(agent.history) == []


def test_confirmation_timeout_refuses(monkeypatch):
    killed = _kill_setup(monkeypatch)
    agent, client, events = make_agent(
        tool_call("kill_process", {"process": "spotify.exe"}), reply("Cancelled."),
        broker=ConfirmationBroker(), confirm_timeout=0.05,
    )
    agent.run_turn("Close Spotify")
    assert not killed


def test_tool_exception_becomes_error_result():
    reg = build_registry()

    @reg.tool("explode", "test tool")
    def explode(ctx):
        raise RuntimeError("disk on fire")

    agent, client, events = make_agent(tool_call("explode"), reply("That failed."), registry=reg)
    agent.run_turn("Do the thing")
    result = sent_messages(client)[-1]["content"][0]
    assert result["is_error"] and "disk on fire" in result["content"]
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert not finished.ok
    assert any(isinstance(e, ToolStarted) for e in events)
    assert isinstance(events[-1], Done) and events[-1].text == "That failed."


def test_trim_history_keeps_pairs():
    history = []
    for i in range(5):
        history += [
            {"role": "user", "content": [{"type": "text", "text": f"q{i}"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "get_time", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "x"}]},
            {"role": "assistant", "content": [{"type": "text", "text": f"a{i}"}]},
        ]
    trimmed = trim_history(history, 2)
    assert trimmed[0]["content"][0]["text"] == "q3"
    assert len(trimmed) == 8
    assert validate_history(trimmed) == []

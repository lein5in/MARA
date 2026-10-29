import base64
import io

from PIL import Image

from core import system, brain
from core.brain import Agent, cap_images, validate_history
from core.text import SpokenFilter, clean_text
from core.tools import build_registry, ToolContext, vision_tools
from tests.fakes import FakeAnthropic, FakeMemory, reply, tool_call


def _fake_screen(monkeypatch, size=(3840, 2160)):
    calls = []
    monkeypatch.setattr(system, "active_monitor_rect", lambda: ((0, 0, size[0], size[1]), True))
    monkeypatch.setattr(system, "grab_screen", lambda bbox: calls.append(bbox) or Image.new("RGB", size, (20, 30, 40)))
    return calls


def test_encode_downscales_to_jpeg():
    data, (w, h) = vision_tools.encode_image(Image.new("RGB", (3000, 1000)))
    assert (w, h) == (1568, 523)
    img = Image.open(io.BytesIO(base64.b64decode(data)))
    assert img.format == "JPEG" and img.size == (1568, 523)
    _, small = vision_tools.encode_image(Image.new("RGB", (800, 600)))
    assert small == (800, 600)


def test_look_at_screen_hides_own_windows(monkeypatch):
    bboxes = _fake_screen(monkeypatch)
    hook_calls = []
    monkeypatch.setattr(vision_tools, "_capture_hook", hook_calls.append)
    result = build_registry().execute("look_at_screen", {}, ToolContext())
    assert result.ok and result.untrusted
    assert hook_calls == [True, False]
    assert bboxes == [(0, 0, 3840, 2160)]
    assert result.label == "primary · 1568px"
    kinds = [b["type"] for b in result.content]
    assert kinds == ["text", "image"]
    assert result.content[1]["source"]["media_type"] == "image/jpeg"


def test_capture_restores_windows_on_failure(monkeypatch):
    hook_calls = []
    monkeypatch.setattr(vision_tools, "_capture_hook", hook_calls.append)
    monkeypatch.setattr(system, "active_monitor_rect", lambda: ((0, 0, 10, 10), True))

    def broken(bbox):
        raise OSError("no display")
    monkeypatch.setattr(system, "grab_screen", broken)
    result = build_registry().execute("look_at_screen", {}, ToolContext())
    assert not result.ok and "screen capture failed" in result.content
    assert hook_calls == [True, False]


def test_follow_up_keeps_image_in_same_thread(monkeypatch):
    _fake_screen(monkeypatch, (800, 600))
    agent = Agent(client=FakeAnthropic([tool_call("look_at_screen"), reply("A terminal."),
                                        reply("It shows a Python error.")]),
                  registry=build_registry(), memory=FakeMemory(), background=False)
    agent.run_turn("What's on my screen?")
    agent.run_turn("And what does the error say?")
    sent = agent.client.messages.calls[-1]["messages"]
    images = [b for m in sent if isinstance(m["content"], list) for r in m["content"]
              if r.get("type") == "tool_result" and isinstance(r.get("content"), list)
              for b in r["content"] if b.get("type") == "image"]
    assert len(images) == 1
    assert validate_history(agent.history) == []


def test_cap_images_keeps_last_two():
    history = []
    for i in range(4):
        history += [
            {"role": "user", "content": [{"type": "text", "text": f"q{i}"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "look_at_screen", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": [
                {"type": "text", "text": "shot"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAA"}}]}]},
            {"role": "assistant", "content": [{"type": "text", "text": f"a{i}"}]},
        ]
    capped = cap_images(history, 2)
    kept = [m for m in capped if m["role"] == "user" and m["content"][0].get("type") == "tool_result"
            and any(b["type"] == "image" for b in m["content"][0]["content"])]
    assert len(kept) == 2
    assert capped[2]["content"][0]["content"][1] == brain.IMAGE_REMOVED
    assert history[2]["content"][0]["content"][1]["type"] == "image"
    assert validate_history(capped) == []


def test_vision_mode_in_dynamic_prompt():
    agent = Agent(client=FakeAnthropic([]), registry=build_registry(), memory=FakeMemory(), background=False)
    system.set_vision(True)
    assert "Vision mode is ON" in agent.dynamic_context()
    system.set_vision(False)
    assert "only when the user asks" in agent.dynamic_context()
    assert "look_at_screen" in brain.BASE_SYSTEM_PROMPT and "fix" in brain.BASE_SYSTEM_PROMPT


def test_spoken_filter_drops_code_across_deltas():
    f = SpokenFilter()
    parts = ["The loop is off by one. ``", "`python fix\n-    for i in", " range(1, n):\n+    for i in range(n):\n`", "``\nDone."]
    spoken = "".join(f.feed(p) for p in parts)
    assert "range" not in spoken and "python" not in spoken
    assert "The loop is off by one." in spoken and "Done." in spoken
    assert clean_text("Use `x` here `") == "Use x here"


def test_old_vision_pipeline_is_gone():
    assert not hasattr(brain, "ask_mara_vision_stream")
    assert not hasattr(brain, "ask_mara_vision_code")
    assert not hasattr(system, "take_screenshot_for_vision")

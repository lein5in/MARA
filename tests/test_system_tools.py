from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core import system
from core.events import ModeChanged
from core.tools import build_registry, ToolContext
from core.tools.registry import ToolError
from core.tools.system_tools import resolve_pause_target
from tests.fakes import FakeMemory


@pytest.fixture
def run():
    reg = build_registry()
    events = []
    ctx = ToolContext(emit=events.append, memory=FakeMemory())

    def _run(tool, **args):
        return reg.execute(tool, args, ctx)
    _run.events = events
    _run.ctx = ctx
    return _run


class FakeVolume:
    def __init__(self):
        self.level, self.muted = 0.5, 0

    def SetMasterVolumeLevelScalar(self, v, _):
        self.level = v

    def GetMasterVolumeLevelScalar(self):
        return self.level

    def GetMute(self):
        return self.muted

    def SetMute(self, m, _):
        self.muted = m


def test_volume(run, monkeypatch):
    vol = FakeVolume()
    monkeypatch.setattr(system, "_get_volume_interface", lambda: vol)
    assert run("set_volume", level=140).content == "Volume set to 100%."
    assert vol.level == 1.0
    run("set_mute", muted=True)
    assert run("get_volume").content == "Volume is 100% (muted)."
    assert not run("set_volume", level="loud").ok


def test_volume_unavailable(run, monkeypatch):
    def unavailable():
        raise system.SystemActionError("volume control is not available on this machine")
    monkeypatch.setattr(system, "_get_volume_interface", unavailable)
    result = run("get_volume")
    assert not result.ok and "not available" in result.content


def test_brightness(run, monkeypatch):
    calls = []
    monkeypatch.setattr(system, "_SBC_OK", True)
    monkeypatch.setattr(system, "sbc", SimpleNamespace(set_brightness=calls.append, get_brightness=lambda: [70]), raising=False)
    assert run("set_brightness", level=-5).content == "Brightness set to 0%."
    assert calls == [0]
    assert run("get_brightness").content == "Brightness is 70%."


def test_wifi(run, monkeypatch):
    out = "    Name : Wi-Fi\n    State                  : connected\n    SSID                   : HomeNet\n    BSSID   : aa\n"
    monkeypatch.setattr(system, "_netsh", lambda *a: SimpleNamespace(returncode=0, stdout=out, stderr=""))
    assert run("wifi_status").content == "WiFi connected to HomeNet."
    monkeypatch.setattr(system, "_netsh", lambda *a: SimpleNamespace(returncode=1, stdout="", stderr="no interface"))
    result = run("wifi_disconnect")
    assert not result.ok and "no interface" in result.content


def test_time_other_city(run):
    result = run("get_time", timezone="Asia/Tokyo")
    assert result.ok and "Asia/Tokyo" in result.content and "UTC+09:00" in result.content
    assert run("get_time").ok
    bad = run("get_time", timezone="Mars/Olympus")
    assert not bad.ok and "unknown timezone" in bad.content


def test_screenshot_file(run, monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(system, "SCREENSHOTS_DIR", tmp_path)
    monkeypatch.setattr(system, "_SCREENSHOT_OK", True)
    monkeypatch.setattr(system, "pyautogui", SimpleNamespace(screenshot=lambda: SimpleNamespace(save=saved.append)), raising=False)
    result = run("take_screenshot", filename="my: shot")
    assert result.ok
    assert saved == [str(tmp_path / "my_ shot.png")]


def test_silent_emits_mode(run):
    run("set_silent", on=True)
    assert system.is_silent()
    run("set_silent", on=False)
    assert run.events == [ModeChanged(True, False), ModeChanged(False, False)]


def test_pause_minutes_and_until():
    now = datetime(2026, 10, 29, 18, 0, tzinfo=timezone(timedelta(hours=-4)))
    assert resolve_pause_target(minutes=90, now=now) == now + timedelta(minutes=90)
    assert resolve_pause_target(until="2026-10-29T21:00", now=now).hour == 21
    with pytest.raises(ToolError):
        resolve_pause_target(until="2026-10-29T09:00", now=now)
    with pytest.raises(ToolError):
        resolve_pause_target(until="nine pm", now=now)
    with pytest.raises(ToolError):
        resolve_pause_target(now=now)
    with pytest.raises(ToolError):
        resolve_pause_target(minutes=10, until="2026-10-29T21:00", now=now)


def test_pause_tool_stores_until(run):
    future = (datetime.now() + timedelta(hours=3)).replace(microsecond=0).isoformat()
    result = run("pause_mara", until=future)
    assert result.ok
    assert system.is_paused(run.ctx.memory)
    system.cancel_pause(run.ctx.memory)
    assert not system.is_paused(run.ctx.memory)


def test_regex_pause_parser_is_gone():
    assert not hasattr(system, "parse_pause_duration")

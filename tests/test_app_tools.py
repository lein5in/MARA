import time

import pytest

from core.tools import app_tools, build_registry, ToolContext


@pytest.fixture
def calls(monkeypatch):
    rec = {"popen": [], "startfile": []}
    monkeypatch.setattr(app_tools, "_popen", lambda argv, **kw: rec["popen"].append(argv))
    monkeypatch.setattr(app_tools, "_startfile", lambda target: rec["startfile"].append(target))
    monkeypatch.setattr(app_tools, "_wait_for_new_window", lambda prev, timeout=0: None)
    monkeypatch.setattr(app_tools, "_foreground_window", lambda: None)
    monkeypatch.setattr(app_tools, "_registry_cache", {})
    return rec


@pytest.fixture
def run():
    reg = build_registry()
    return lambda tool, **args: reg.execute(tool, args, ToolContext())


def test_open_app_from_registry_with_spaces(run, calls, monkeypatch, tmp_path):
    exe = tmp_path / "My Apps" / "Spotify.exe"
    exe.parent.mkdir()
    exe.write_text("")
    monkeypatch.setattr(app_tools, "_registry_cache", {"spotify": str(exe)})
    result = run("open_app", name="Spotify", args=["--minimized"])
    assert result.ok
    assert calls["popen"] == [[str(exe), "--minimized"]]


def test_open_app_protocol_and_console(run, calls):
    assert run("open_app", name="settings").ok
    assert calls["startfile"] == ["ms-settings:"]
    assert run("open_app", name="powershell").ok
    assert calls["popen"][-1] == ["powershell.exe"]


def test_open_app_never_uses_shell_with_model_string(run, calls, monkeypatch):
    monkeypatch.setattr(app_tools.shutil, "which", lambda name: None)
    result = run("open_app", name="calc & del /q C:\\*")
    assert not result.ok and "no installed app" in result.content
    assert calls["popen"] == [] and calls["startfile"] == []


def test_open_path_with_spaces(run, calls, tmp_path):
    folder = tmp_path / "testing java"
    folder.mkdir()
    assert run("open_path", path=str(folder)).ok
    assert calls["startfile"] == [str(folder)]
    assert run("open_path", path="https://example.com/a b").ok
    missing = run("open_path", path=str(tmp_path / "nope"))
    assert not missing.ok


def test_scan_respects_cap_and_deadline(tmp_path):
    for i in range(20):
        (tmp_path / f"report {i}.txt").write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "report x.txt").write_text("")
    found = app_tools.scan_for(["report"], [tmp_path], False, limit=5, deadline=time.monotonic() + 5)
    assert len(found) == 5
    assert all("node_modules" not in str(p) for p in found)
    assert app_tools.scan_for(["report"], [tmp_path], False, limit=5, deadline=time.monotonic() - 1) == []


def test_find_files_falls_back_to_scan(run, monkeypatch, tmp_path):
    (tmp_path / "Testing Java").mkdir()

    def no_index(*a):
        raise OSError("no index")
    monkeypatch.setattr(app_tools, "_windows_search", no_index)
    monkeypatch.setattr(app_tools.Path, "home", classmethod(lambda cls: tmp_path))
    result = run("find_files", name="testing java", is_folder=True)
    assert result.ok and "Testing Java" in result.content


def test_kill_requires_confirmation_level():
    reg = build_registry()
    tool = reg.get("kill_process")
    title, description = tool.confirmation({"process": "spotify.exe"})
    assert tool.risk == "confirm" and "spotify.exe" in description

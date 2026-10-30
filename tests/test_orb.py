import sys

import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from PyQt5.QtWidgets import QApplication

from core import orb as orb_module


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _run(orb, seconds, now):
    for _ in range(int(seconds * 60)):
        now += 1 / 60
        orb.advance(1 / 60, now)
    return now


def test_orb_hidden_and_idle_by_default(app):
    orb = orb_module.MARAOrb()
    assert not orb._timer.isActive()
    assert not orb.isVisible()
    assert orb._target_opacity(0.0) == 0.0


def test_orb_fades_in_lingers_then_fades_out(app):
    orb = orb_module.MARAOrb()
    orb.set_state("listening")
    assert orb._timer.isActive()
    now = _run(orb, 0.35, 0.0)
    assert orb._opacity == 1.0
    orb.set_level(0.9)
    now = _run(orb, 0.3, now)
    assert orb._energy > 0.6
    orb.set_state("speaking")
    orb.set_state("idle")
    orb._hide_at = now + orb_module.LINGER_SECONDS
    now = _run(orb, 1.0, now)
    assert orb._opacity == 1.0
    _run(orb, 1.0, now)
    assert orb._opacity == 0.0
    orb._timer.stop()


def test_speaking_uses_output_level_then_synthetic(app):
    orb = orb_module.MARAOrb()
    level = {"v": 0.7}
    orb.set_output_level_source(lambda: level["v"])
    orb.set_state("speaking")
    assert orb._speech_amplitude(10.0) == 0.7
    level["v"] = 0.0
    assert orb._speech_amplitude(10.2) == 0.0
    assert orb._speech_amplitude(11.0) > 0.0
    orb._timer.stop()

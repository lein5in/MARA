import math
import time

from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QPainter, QColor, QRadialGradient, QConicalGradient, QPen, QBrush
from PyQt5.QtWidgets import QWidget, QApplication

from core.config import ORB_SIZE, ORB_IDLE_VISIBLE

FRAME_MS = 16
FADE_SECONDS = 0.3
LINGER_SECONDS = 1.5
IDLE_OPACITY = 0.45
RIPPLE_LIFE = 1.2
OUTPUT_SILENCE = 0.5

CX = CY = ORB_SIZE / 2
R = ORB_SIZE * 0.27
DOT_COUNT = 140
TILT = 0.38

PALETTES = {
    "LISTENING": ((232, 160, 180), (34, 13, 22)),
    "THINKING": ((206, 170, 228), (25, 14, 35)),
    "SPEAKING": ((242, 172, 194), (40, 14, 26)),
    "WAITING_CONFIRMATION": ((229, 181, 103), (34, 24, 9)),
    "IDLE": ((150, 105, 118), (16, 9, 12)),
    "PAUSED": ((110, 116, 130), (12, 13, 15)),
}
RESTING = {"IDLE", "PAUSED"}
ROT_SPEED = {"LISTENING": 0.35, "THINKING": 0.6, "SPEAKING": 0.4, "WAITING_CONFIRMATION": 0.15}


def _approach(value: float, target: float, rate: float, dt: float) -> float:
    return value + (target - value) * (1 - math.exp(-rate * dt))


def _mix(a, b, k: float) -> tuple:
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def _color(rgb, alpha: float = 255) -> QColor:
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0, min(255, alpha))))


def _sphere_points(n: int) -> list[tuple]:
    golden = math.pi * (3 - math.sqrt(5))
    points = []
    for i in range(n):
        y = 1 - (i + 0.5) / n * 2
        ring = math.sqrt(1 - y * y)
        a = golden * i
        points.append((math.cos(a) * ring, y, math.sin(a) * ring, (i * 0.618) % 1 * math.tau))
    return points


class MARAOrb(QWidget):

    def __init__(self):
        super().__init__()
        self._state = "IDLE"
        self._look = "IDLE"
        self._hide_at = None
        self._opacity = 0.0
        self._t = 0.0
        self._last = time.monotonic()
        self._accent, self._deep = PALETTES["IDLE"]
        self._energy = 0.0
        self._mic = 0.0
        self._rot = 0.0
        self._rot_speed = 0.0
        self._think = 0.0
        self._listen = 0.0
        self._ripples: list[float] = []
        self._last_ripple = 0.0
        self._prev_amp = 0.0
        self._output_source = None
        self._output_heard = -1.0
        self._dots = _sphere_points(DOT_COUNT)

        self._setup_window()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._frame)
        if ORB_IDLE_VISIBLE:
            self._wake()

    def _setup_window(self):
        self.setFixedSize(ORB_SIZE, ORB_SIZE)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowOpacity(0.0)

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - ORB_SIZE) // 2, screen.height() - ORB_SIZE - 52)

    def set_state(self, state: str):
        state = str(state).upper()
        state = state if state in PALETTES else "IDLE"
        if state == self._state:
            return
        self._state = state
        if state in RESTING:
            self._hide_at = time.monotonic() + LINGER_SECONDS
        else:
            self._hide_at = None
            self._look = state
            self._wake()

    def set_level(self, level: float):
        self._mic = max(0.0, min(1.0, float(level)))

    def set_output_level_source(self, source):
        self._output_source = source

    def _wake(self):
        if not self._timer.isActive():
            self._last = time.monotonic()
            self._timer.start(FRAME_MS)

    def _target_opacity(self, now: float) -> float:
        if self._state not in RESTING or (self._hide_at is not None and now < self._hide_at):
            return 1.0
        return IDLE_OPACITY if ORB_IDLE_VISIBLE else 0.0

    def _frame(self):
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        target = self.advance(dt, now)
        if self._opacity <= 0.0 and target <= 0.0:
            self._timer.stop()
            self.hide()
            self._ripples.clear()
            self._energy = self._mic = 0.0
            return
        if not self.isVisible():
            self.show()
        self.setWindowOpacity(self._opacity)
        self.update()

    def _speech_amplitude(self, now: float) -> float:
        amp = None
        if self._output_source is not None:
            try:
                amp = float(self._output_source())
            except Exception:
                amp = None
        if amp is not None and amp > 0.02:
            self._output_heard = now
        if amp is not None and now - self._output_heard < OUTPUT_SILENCE:
            return min(1.0, amp)
        t = self._t
        syllable = abs(math.sin(math.pi * 3.2 * t)) ** 1.5
        phrase = 0.65 + 0.35 * math.sin(math.tau * 0.45 * t)
        return 0.18 + 0.62 * syllable * phrase

    def _energy_target(self, now: float) -> float:
        if self._state in RESTING:
            return 0.0
        look = self._look
        if look == "LISTENING":
            return self._mic
        if look == "THINKING":
            return 0.3 + 0.14 * math.sin(math.tau * self._t / 3.2)
        if look == "SPEAKING":
            return self._speech_amplitude(now)
        return 0.22 + 0.08 * math.sin(math.tau * self._t / 1.6)

    def advance(self, dt: float, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self._t += dt
        target = self._target_opacity(now)
        step = dt / FADE_SECONDS
        if self._opacity < target:
            self._opacity = min(target, self._opacity + step)
        else:
            self._opacity = max(target, self._opacity - step)

        if self._state in RESTING and (self._hide_at is None or now >= self._hide_at):
            self._look = self._state
        accent, deep = PALETTES[self._look]
        self._accent = _mix(self._accent, accent, 1 - math.exp(-6 * dt))
        self._deep = _mix(self._deep, deep, 1 - math.exp(-6 * dt))

        wanted = self._energy_target(now)
        self._energy = _approach(self._energy, wanted, 16 if wanted > self._energy else 5, dt)
        self._rot_speed = _approach(self._rot_speed, ROT_SPEED.get(self._look, 0.08), 3, dt)
        self._rot = (self._rot + self._rot_speed * dt) % math.tau
        self._think = _approach(self._think, 1.0 if self._look == "THINKING" else 0.0, 4, dt)
        self._listen = _approach(self._listen, 1.0 if self._look == "LISTENING" else 0.0, 6, dt)

        self._ripples = [age + dt for age in self._ripples if age + dt < RIPPLE_LIFE]
        if self._look == "SPEAKING" and self._state not in RESTING:
            amp = self._energy
            if amp > 0.5 and amp > self._prev_amp + 0.01 and self._t - self._last_ripple > 0.38:
                self._ripples.append(0.0)
                self._last_ripple = self._t
            self._prev_amp = amp
        return target

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.paint_orb(p)
        p.end()

    def paint_orb(self, p: QPainter):
        accent, deep, e = self._accent, self._deep, self._energy
        center = QPointF(CX, CY)
        r = R * (1 + 0.16 * e)
        p.setPen(Qt.NoPen)

        halo_r = min(CX - 1, r * 1.75)
        edge = r / halo_r
        halo = QRadialGradient(center, halo_r)
        halo.setColorAt(0.0, _color(accent, 0))
        halo.setColorAt(edge * 0.97, _color(accent, 95 + 100 * e))
        halo.setColorAt(edge + (1 - edge) * 0.18, _color(accent, 42 + 50 * e))
        halo.setColorAt(edge + (1 - edge) * 0.5, _color(accent, 12 + 18 * e))
        halo.setColorAt(1.0, _color(accent, 0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(center, halo_r, halo_r)

        p.setBrush(Qt.NoBrush)
        for age in self._ripples:
            k = age / RIPPLE_LIFE
            rad = r + (CX - 3 - r) * (1 - (1 - k) ** 3)
            p.setPen(QPen(_color(accent, 150 * (1 - k) ** 2), 1.6 * (1 - k) + 0.4))
            p.drawEllipse(center, rad, rad)

        body = QRadialGradient(QPointF(CX - 0.3 * r, CY - 0.35 * r), r * 1.4)
        body.setColorAt(0.0, _color(_mix(deep, accent, 0.22)))
        body.setColorAt(0.6, _color(deep))
        body.setColorAt(1.0, _color(_mix(deep, accent, 0.12)))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(body))
        p.drawEllipse(center, r, r)

        glow = QRadialGradient(QPointF(CX, CY + 0.42 * r), r * 1.05)
        glow.setColorAt(0.0, _color(_mix(accent, (255, 255, 255), 0.15), 70 + 120 * e))
        glow.setColorAt(0.55, _color(accent, 20 + 50 * e))
        glow.setColorAt(1.0, _color(accent, 0))
        p.setBrush(QBrush(glow))
        p.drawEllipse(center, r, r)

        self._paint_dots(p, r)

        rim = QRadialGradient(center, r)
        rim.setColorAt(0.0, _color(accent, 0))
        rim.setColorAt(0.78, _color(accent, 0))
        rim.setColorAt(0.95, _color(accent, 55 + 70 * e))
        rim.setColorAt(1.0, _color(accent, 110 + 90 * e))
        p.setBrush(QBrush(rim))
        p.drawEllipse(center, r, r)

        if self._think > 0.01:
            orbit = r * 1.28
            arc = QConicalGradient(center, -math.degrees(self._rot * 2.2))
            arc.setColorAt(0.0, _color(accent, 0))
            arc.setColorAt(0.01, _color(accent, 200 * self._think))
            arc.setColorAt(0.3, _color(accent, 0))
            arc.setColorAt(1.0, _color(accent, 0))
            p.setPen(QPen(QBrush(arc), 1.5, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(center, orbit, orbit)
            p.setPen(Qt.NoPen)

        spec = QRadialGradient(QPointF(CX - 0.36 * r, CY - 0.42 * r), r * 0.55)
        spec.setColorAt(0.0, QColor(255, 255, 255, 34))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(spec))
        p.drawEllipse(center, r, r)

    def _paint_dots(self, p: QPainter, r: float):
        accent, e = self._accent, self._energy
        bright = _mix(accent, (255, 255, 255), 0.35)
        cos_r, sin_r = math.cos(self._rot), math.sin(self._rot)
        cos_t, sin_t = math.cos(TILT), math.sin(TILT)
        wobble = 0.13 * e * self._listen
        p.setPen(Qt.NoPen)
        for x, y, z, phase in self._dots:
            x1 = x * cos_r + z * sin_r
            z1 = -x * sin_r + z * cos_r
            y2 = y * cos_t - z1 * sin_t
            z2 = y * sin_t + z1 * cos_t
            d = 0.86 * (1 + wobble * math.sin(self._t * 7 + phase * 3))
            front = (z2 + 1) / 2
            alpha = 230 * front ** 2.4 * (0.6 + 0.4 * e)
            size = 0.35 + 0.8 * front
            p.setBrush(QBrush(_color(_mix(accent, bright, front), alpha)))
            p.drawEllipse(QPointF(CX + x1 * r * d, CY - y2 * r * d), size, size)

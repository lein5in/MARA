import math
import random
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QRadialGradient, QPen, QBrush
from core.config import ORB_SIZE, ORB_IDLE_VISIBLE


ORB_R    = 77
CX       = ORB_SIZE / 2
CY       = ORB_SIZE / 2

FADE_STEPS = 20


def _palette(front, back, edge_f, edge_b, pulse, inner, outer):
    return {
        "node_front": QColor(*front), "node_back": QColor(*back),
        "edge_front": QColor(*edge_f), "edge_back": QColor(*edge_b),
        "pulse": QColor(*pulse), "bg_inner": QColor(*inner), "bg_outer": QColor(*outer), "rim": QColor(*front),
    }


STATE_COLORS = {
    "LISTENING": _palette((232, 160, 180), (90, 45, 60), (190, 120, 140), (60, 30, 40), (245, 190, 205), (24, 10, 15), (12, 5, 8)),
    "THINKING": _palette((214, 170, 220), (70, 45, 80), (170, 130, 180), (45, 30, 55), (235, 205, 240), (18, 10, 24), (9, 5, 12)),
    "SPEAKING": _palette((245, 180, 198), (110, 55, 72), (220, 140, 162), (70, 35, 46), (255, 215, 225), (28, 12, 18), (14, 6, 9)),
    "WAITING_CONFIRMATION": _palette((229, 181, 103), (90, 70, 35), (190, 150, 85), (60, 45, 22), (240, 205, 140), (24, 18, 8), (12, 9, 4)),
    "IDLE": _palette((150, 105, 118), (50, 32, 38), (110, 75, 86), (35, 22, 27), (170, 120, 135), (14, 8, 11), (7, 4, 6)),
    "PAUSED": _palette((110, 116, 130), (40, 42, 48), (80, 85, 96), (28, 30, 34), (130, 136, 150), (10, 11, 13), (5, 5, 6)),
}

RESTING = {"IDLE", "PAUSED"}
IDLE_ALPHA = 110


class Node3D:
    def __init__(self, theta: float, phi: float):

        self.theta = theta   
        self.phi   = phi     
        self.base_r = random.uniform(2.0, 3.5)
        self.phase  = random.uniform(0, math.pi * 2)
        self.speed  = random.uniform(0.3, 0.8)

    def xyz(self):
        x = math.cos(self.phi) * math.cos(self.theta)
        y = math.cos(self.phi) * math.sin(self.theta)
        z = math.sin(self.phi)
        return x, y, z


class Pulse3D:
    def __init__(self, a: int, b: int, speed: float, size: float, color: QColor):
        self.a     = a
        self.b     = b
        self.t     = 0.0
        self.speed = speed
        self.size  = size
        self.color = color

    @property
    def done(self):
        return self.t >= 1.0

    def advance(self):
        self.t = min(1.0, self.t + self.speed)


class MARAOrb(QWidget):

    def __init__(self):
        super().__init__()
        self._state   = "IDLE"
        self._alpha   = 0
        self._tick    = 0
        self._rot_y   = 0.0    
        self._rot_x   = 0.12   
        self._nodes:  list[Node3D]  = []
        self._edges:  list[tuple]   = []
        self._pulses: list[Pulse3D] = []

        self._setup_window()
        self._gen_network()

        self._timer = QTimer()
        self._timer.timeout.connect(self._frame)
        self._timer.start(33)   


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
        x = (screen.width() - ORB_SIZE) // 2
        y = screen.height() - ORB_SIZE - 52
        self.move(x, y)


    def _gen_network(self):
        self._nodes = []


        n = 28
        golden = math.pi * (3 - math.sqrt(5))
        for i in range(n):
            y_val = 1 - (i / (n - 1)) * 2
            radius = math.sqrt(max(0, 1 - y_val * y_val))
            theta  = golden * i
            phi    = math.asin(max(-1, min(1, y_val)))

            node_theta = math.atan2(radius * math.sin(theta), radius * math.cos(theta))
            self._nodes.append(Node3D(node_theta, phi))

        self._edges = []
        max_angle = 0.72  
        for i in range(len(self._nodes)):
            for j in range(i + 1, len(self._nodes)):
                xi, yi, zi = self._nodes[i].xyz()
                xj, yj, zj = self._nodes[j].xyz()
                dot = xi*xj + yi*yj + zi*zj
                dot = max(-1.0, min(1.0, dot))
                angle = math.acos(dot)
                if angle < max_angle:
                    self._edges.append((i, j, angle))


    def _project(self, node: Node3D):
        x, y, z = node.xyz()


        ry = self._rot_y
        x2 = x * math.cos(ry) - y * math.sin(ry)
        y2 = x * math.sin(ry) + y * math.cos(ry)
        z2 = z


        rx = self._rot_x
        y3 = y2 * math.cos(rx) - z2 * math.sin(rx)
        z3 = y2 * math.sin(rx) + z2 * math.cos(rx)
        x3 = x2


        fov  = 2.8
        persp = fov / (fov + z3 * 0.3)

        px = CX + x3 * ORB_R * 0.88 * persp
        py = CY - y3 * ORB_R * 0.88 * persp


        depth = z3

        return px, py, depth, persp


    def _spawn_pulse(self):
        if not self._edges:
            return
        col = STATE_COLORS[self._state]
        i, j, _ = random.choice(self._edges)
        if random.random() > 0.5:
            i, j = j, i

        speed = {
            "LISTENING": random.uniform(0.018, 0.028),
            "THINKING":  random.uniform(0.010, 0.018),
            "SPEAKING":  random.uniform(0.030, 0.048),
        }.get(self._state, 0.008)

        self._pulses.append(Pulse3D(
            i, j, speed,
            random.uniform(2.0, 3.2),
            col["pulse"],
        ))

    def _spawn_rate(self) -> float:
        return {
            "LISTENING": 0.22,
            "THINKING":  0.32,
            "SPEAKING":  0.42,
            "WAITING_CONFIRMATION": 0.12,
            "IDLE": 0.04,
        }.get(self._state, 0.0)

    def _rot_speed(self) -> float:
        return {
            "LISTENING": 0.004,
            "THINKING":  0.009,
            "SPEAKING":  0.006,
            "WAITING_CONFIRMATION": 0.003,
        }.get(self._state, 0.0015)


    def _target_alpha(self) -> int:
        if self._state in RESTING:
            return IDLE_ALPHA if ORB_IDLE_VISIBLE else 0
        return 255

    def _step_fade(self):
        target = self._target_alpha()
        if self._alpha == target:
            return
        if target > 0 and not self.isVisible():
            self.show()
        step = 255 // FADE_STEPS
        self._alpha = min(target, self._alpha + step) if self._alpha < target else max(target, self._alpha - step)
        self.setWindowOpacity(self._alpha / 255)
        if self._alpha == 0:
            self.hide()
            self._pulses.clear()

    def set_state(self, state: str):
        state = str(state).upper()
        self._state = state if state in STATE_COLORS else "IDLE"

    def _frame(self):
        self._tick += 1
        self._step_fade()

        if self._alpha == 0:
            return

        self._rot_y += self._rot_speed()


        for p in self._pulses:
            p.advance()
        self._pulses = [p for p in self._pulses if not p.done]

        if random.random() < self._spawn_rate():
            self._spawn_pulse()

        self.update()


    def paintEvent(self, event):
        if self._alpha == 0:
            return

        col = STATE_COLORS[self._state]
        p   = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)


        bg = QRadialGradient(CX, CY, ORB_R + 8)
        c_in  = QColor(col["bg_inner"])
        c_in.setAlpha(210)
        c_out = QColor(col["bg_outer"])
        c_out.setAlpha(0)
        bg.setColorAt(0.0,  c_in)
        bg.setColorAt(0.78, c_in)
        bg.setColorAt(1.0,  c_out)
        p.setBrush(QBrush(bg))
        p.setPen(Qt.NoPen)
        p.drawEllipse(
            int(CX - ORB_R - 8), int(CY - ORB_R - 8),
            int((ORB_R + 8) * 2), int((ORB_R + 8) * 2)
        )


        projs = [self._project(n) for n in self._nodes]


        order = sorted(range(len(self._nodes)), key=lambda i: projs[i][2])


        for ei, ej, angle in self._edges:
            px1, py1, d1, _ = projs[ei]
            px2, py2, d2, _ = projs[ej]
            depth_avg = (d1 + d2) / 2


            if depth_avg < -0.1:
                visibility = 0.12 + (depth_avg + 1) * 0.08
                ec = QColor(col["edge_back"])
            else:
                visibility = 0.18 + depth_avg * 0.35
                ec = QColor(col["edge_front"])

            ec.setAlpha(int(max(0, min(255, visibility * 200)))  )
            pen = QPen(ec, 0.5 + depth_avg * 0.3)
            p.setPen(pen)
            p.drawLine(int(px1), int(py1), int(px2), int(py2))


        for pulse in self._pulses:
            px1, py1, d1, s1 = projs[pulse.a]
            px2, py2, d2, s2 = projs[pulse.b]
            t = pulse.t
            x  = px1 + (px2 - px1) * t
            y  = py1 + (py2 - py1) * t
            depth = d1 + (d2 - d1) * t
            scale = s1 + (s2 - s1) * t


            if depth < -0.2:
                continue

            vis = max(0.2, (depth + 1) / 2)
            sz  = pulse.size * scale * 0.9


            glow = QRadialGradient(x, y, sz * 3)
            gc = QColor(pulse.color)
            gc.setAlpha(int(90 * vis))
            tc = QColor(pulse.color)
            tc.setAlpha(0)
            glow.setColorAt(0, gc)
            glow.setColorAt(1, tc)
            p.setBrush(QBrush(glow))
            p.setPen(Qt.NoPen)
            p.drawEllipse(int(x - sz*3), int(y - sz*3), int(sz*6), int(sz*6))


            cc = QColor(pulse.color)
            cc.setAlpha(int(220 * vis))
            p.setBrush(QBrush(cc))
            p.drawEllipse(int(x - sz*0.7), int(y - sz*0.7), int(sz*1.4), int(sz*1.4))


        for i in order:
            n = self._nodes[i]
            px, py, depth, scale = projs[i]

            pulse_val = math.sin(self._tick * 0.025 * n.speed + n.phase)
            nr = n.base_r * scale * (1 + pulse_val * 0.1)

            is_front = depth > 0
            nc = QColor(col["node_front"] if is_front else col["node_back"])
            vis = 0.25 + ((depth + 1) / 2) * 0.75
            brightness = vis * (0.6 + pulse_val * 0.2)


            g = QRadialGradient(px, py, nr * 4)
            gc = QColor(nc)
            gc.setAlpha(int(70 * brightness))
            tc = QColor(nc)
            tc.setAlpha(0)
            g.setColorAt(0, gc)
            g.setColorAt(1, tc)
            p.setBrush(QBrush(g))
            p.setPen(Qt.NoPen)
            p.drawEllipse(int(px - nr*4), int(py - nr*4), int(nr*8), int(nr*8))


            fc = QColor(col["bg_inner"])
            fc.setAlpha(180)
            border = QColor(nc)
            border.setAlpha(int(180 * brightness))
            p.setBrush(QBrush(fc))
            p.setPen(QPen(border, 0.7))
            p.drawEllipse(int(px - nr), int(py - nr), int(nr*2), int(nr*2))


            bright_c = QColor(nc)
            bright_c.setAlpha(int(210 * brightness))
            p.setBrush(QBrush(bright_c))
            p.setPen(Qt.NoPen)
            p.drawEllipse(int(px - nr*0.4), int(py - nr*0.4), int(nr*0.8), int(nr*0.8))


        rim = QColor(col["rim"])
        rim.setAlpha(25)
        p.setPen(QPen(rim, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(
            int(CX - ORB_R - 6), int(CY - ORB_R - 6),
            int((ORB_R + 6) * 2), int((ORB_R + 6) * 2)
        )


        highlight = QRadialGradient(CX - ORB_R * 0.3, CY - ORB_R * 0.35, ORB_R * 0.55)
        hc = QColor(255, 255, 255)
        hc.setAlpha(12)
        ht = QColor(255, 255, 255)
        ht.setAlpha(0)
        highlight.setColorAt(0, hc)
        highlight.setColorAt(1, ht)
        p.setBrush(QBrush(highlight))
        p.setPen(Qt.NoPen)
        p.drawEllipse(
            int(CX - ORB_R - 6), int(CY - ORB_R - 6),
            int((ORB_R + 6) * 2), int((ORB_R + 6) * 2)
        )

        p.end()
"""Custom lightweight futuristic widgets."""

from __future__ import annotations

import math
import random
from datetime import datetime
from html import escape

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QTextCursor
from PySide6.QtWidgets import QFrame, QLabel, QTextEdit, QVBoxLayout, QWidget


class HoloPanel(QFrame):
    """Reusable glowing panel with cyan border."""

    def __init__(self, title: str, value: str = "--") -> None:
        super().__init__()
        self.setObjectName("HoloPanel")
        # Without this, QFrame subclasses ignore the stylesheet's translucent
        # background and paint the default (black) widget background instead.
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        self.title = QLabel(title.upper())
        self.title.setObjectName("PanelTitle")
        self.value = QLabel(value)
        self.value.setObjectName("PanelValue")
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class StatusPanel(QFrame):
    """Compact multi-row panel for connection/status readouts.

    Cheap to update (just label text, no repaint of graphics), used for the
    Groq/Piper/Microphone/Model connection status readout.
    """

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("HoloPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._layout = QVBoxLayout(self)
        self.title = QLabel(title.upper())
        self.title.setObjectName("PanelTitle")
        self._layout.addWidget(self.title)
        self._rows: dict[str, QLabel] = {}

    def set_rows(self, items: dict[str, str]) -> None:
        for key, value in items.items():
            row = self._rows.get(key)
            if row is None:
                row = QLabel()
                row.setObjectName("PanelRow")
                self._layout.addWidget(row)
                self._rows[key] = row
            row.setText(f"{key}: {value}")


class ChatView(QTextEdit):
    """Efficient holographic chat stream with timestamped message cards."""

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("Conversation stream")
        self.document().setDefaultStyleSheet(
            """
            body { color: #f2e9df; font-family: 'DejaVu Sans'; font-size: 15px; }
            .row { margin: 12px 0; }
            .label { font-size: 11px; letter-spacing: 1.5px; color: #ff9d3d; }
            .time { color: #8a7c6c; font-size: 10px; }
            .bubble { border-radius: 12px; padding: 10px 12px; line-height: 1.35; }
            .user { background-color: rgba(46, 28, 12, 0.85); border: 1px solid #ff8c1a; color: #fff3e6; }
            .assistant { background-color: rgba(18, 14, 10, 0.92); border: 1px solid #cc6f10; color: #fdf3e6; }
            .system { background-color: rgba(40, 30, 15, 0.85); border: 1px solid #ffbf6b; color: #fff2d6; }
            """
        )

    def add_message(self, speaker: str, text: str, role: str) -> None:
        """Append a formatted message card and scroll to the newest entry."""
        timestamp = datetime.now().strftime("%H:%M")
        safe_speaker = escape(speaker.upper())
        safe_text = escape(text).replace("\n", "<br>")
        safe_role = escape(role)
        alignment = "right" if role == "user" else "left"
        html = f"""
        <div class="row" align="{alignment}">
          <table width="78%" cellspacing="0" cellpadding="0">
            <tr><td><span class="label">{safe_speaker}</span> <span class="time">{timestamp}</span></td></tr>
            <tr><td class="bubble {safe_role}">{safe_text}</td></tr>
          </table>
        </div>
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        cursor.insertBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def begin_stream(self, speaker: str = "JARVIS", role: str = "assistant") -> None:
        """Start an assistant card that can receive streaming chunks."""
        timestamp = datetime.now().strftime("%H:%M")
        alignment = "right" if role == "user" else "left"
        html = f"""
        <div class="row" align="{alignment}">
          <table width="78%" cellspacing="0" cellpadding="0">
            <tr><td><span class="label">{escape(speaker.upper())}</span> <span class="time">{timestamp}</span></td></tr>
            <tr><td class="bubble {escape(role)}">
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_stream(self, text: str) -> None:
        """Append escaped text to the active streaming assistant card."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(escape(text).replace("\n", "<br>"))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def end_stream(self) -> None:
        """Close the active streaming assistant card."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml("</td></tr></table></div>")
        cursor.insertBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()


#: Pulse speed (timer tick, ms) per AI state. Faster ticks for active states,
#: slower/cheaper when idle. Color no longer switches per-state (the planet
#: itself continuously drifts through the black/orange/white palette below);
#: state only changes how fast it pulses/rotates.
CORE_STATE_SPEED = {
    "idle": 45,
    "listening": 28,
    "thinking": 40,
    "speaking": 24,
}

#: Warm palette stops the planet cycles through over time: deep black,
#: burnt orange, bright orange, and white highlight.
PLANET_PALETTE = [
    QColor(10, 8, 6),
    QColor(200, 90, 20),
    QColor(255, 140, 30),
    QColor(255, 200, 120),
    QColor(255, 140, 30),
    QColor(200, 90, 20),
]


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


class AICoreWidget(QWidget):
    """Animated 2D 'planet' core designed to be cheap on low-end GPUs.

    Renders a Saturn-like ringed sphere that slowly drifts through a
    black/orange/white palette. The assistant's current state
    (idle/listening/thinking/speaking) only affects how fast it pulses and
    rotates, keeping the drawing itself simple (no 3D, no heavy repaints).
    """

    def __init__(self) -> None:
        super().__init__()
        self.phase = 0.0
        self.state = "idle"
        self.setMinimumSize(260, 260)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(CORE_STATE_SPEED["idle"])

    def set_state(self, state: str) -> None:
        if state not in CORE_STATE_SPEED or state == self.state:
            return
        self.state = state
        self.timer.setInterval(CORE_STATE_SPEED[state])
        self.update()

    def _tick(self) -> None:
        self.phase = (self.phase + 0.02) % (math.tau)
        self.update()

    def _current_planet_color(self) -> QColor:
        span = len(PLANET_PALETTE) - 1
        position = (math.sin(self.phase) * 0.5 + 0.5) * span
        index = min(int(position), span - 1)
        t = position - index
        return _lerp_color(PLANET_PALETTE[index], PLANET_PALETTE[index + 1], t)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = min(self.width(), self.height()) // 4
        planet_color = self._current_planet_color()

        # Faint outer atmosphere glow.
        for index in range(3):
            alpha = 60 - index * 18
            pen = QPen(QColor(planet_color.red(), planet_color.green(), planet_color.blue(), max(alpha, 0)), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, radius + 14 + index * 10, radius + 14 + index * 10)

        ring_rect = QRectF(
            center.x() - radius * 1.9,
            center.y() - radius * 0.55,
            radius * 3.8,
            radius * 1.1,
        )

        # Back half of the ring (behind the planet).
        self._draw_ring(painter, ring_rect, planet_color, back=True)

        # Planet sphere with a radial gradient for a lit/shadowed 3D look.
        gradient = QRadialGradient(QPointF(center.x() - radius * 0.35, center.y() - radius * 0.35), radius * 1.4)
        gradient.setColorAt(0.0, planet_color.lighter(160))
        gradient.setColorAt(0.55, planet_color)
        gradient.setColorAt(1.0, QColor(8, 6, 5))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, radius, radius)

        # A couple of subtle atmospheric bands, clipped to the sphere.
        clip_path = QPainterPath()
        clip_path.addEllipse(center, radius, radius)
        painter.save()
        painter.setClipPath(clip_path)
        band_color = QColor(20, 14, 10, 90)
        painter.setPen(Qt.NoPen)
        painter.setBrush(band_color)
        band_offset = math.sin(self.phase * 1.3) * radius * 0.15
        painter.drawEllipse(
            QRectF(center.x() - radius, center.y() - radius * 0.15 + band_offset, radius * 2, radius * 0.35)
        )
        painter.restore()

        # Front half of the ring (in front of the planet).
        self._draw_ring(painter, ring_rect, planet_color, back=False)

    def _draw_ring(self, painter: QPainter, rect: QRectF, base_color: QColor, back: bool) -> None:
        ring_color = QColor(255, 235, 210, 170 if back else 220)
        pen = QPen(ring_color, 3 if back else 4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if back:
            painter.drawArc(rect, 0 * 16, 180 * 16)
        else:
            highlight = QPen(QColor(base_color.lighter(180).red(), base_color.lighter(180).green(), base_color.lighter(180).blue(), 200), 2)
            painter.drawArc(rect, 180 * 16, 180 * 16)
            painter.setPen(highlight)
            inner_rect = rect.adjusted(rect.width() * 0.12, rect.height() * 0.12, -rect.width() * 0.12, -rect.height() * 0.12)
            painter.drawArc(inner_rect, 180 * 16, 180 * 16)


class WaveformWidget(QWidget):
    """Ambient waveform visualizer for voice activity."""

    def __init__(self) -> None:
        super().__init__()
        self.samples = [0.2] * 32
        self.setMinimumHeight(80)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(80)

    def _tick(self) -> None:
        self.samples = self.samples[1:] + [random.uniform(0.15, 1.0)]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 140, 30, 190), 2))
        width = max(1, self.width() / len(self.samples))
        mid = self.height() / 2
        for index, sample in enumerate(self.samples):
            x = int(index * width + width / 2)
            half = int(sample * self.height() * 0.4)
            painter.drawLine(x, int(mid - half), x, int(mid + half))

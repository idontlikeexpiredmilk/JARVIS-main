"""Custom lightweight futuristic widgets."""

from __future__ import annotations

import math
import random
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from services.settings import AppearanceSettings, BUILT_IN_BACKGROUNDS


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


class MessageBubble(QFrame):
    """Resizable modern chat bubble that preserves natural text spacing."""

    def __init__(self, speaker: str, text: str, role: str, settings: AppearanceSettings) -> None:
        super().__init__()
        self.role = role
        self._text = ""
        self._settings = settings
        self.setObjectName(f"Bubble_{role}")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(7)

        timestamp = datetime.now().strftime("%H:%M")
        self.meta = QLabel(f"{speaker.upper()}  ·  {timestamp}")
        self.meta.setObjectName("BubbleMeta")
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text = QLabel()
        self.text.setObjectName("BubbleText")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.MarkdownText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.text.setMinimumWidth(180)
        layout.addWidget(self.meta)
        layout.addWidget(self.text)
        self.apply_settings(settings)
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._text = text
        # QLabel with MarkdownText preserves spaces/punctuation in normal text,
        # wraps long paragraphs, and gives us a future path for lightweight
        # markdown without the table-layout whitespace bugs QTextEdit had here.
        self.text.setText(text if text else " ")
        self.updateGeometry()

    def append_text(self, text: str) -> None:
        self.set_text(self._text + text)

    def apply_settings(self, settings: AppearanceSettings) -> None:
        self._settings = settings
        color = {
            "user": settings.user_bubble_color,
            "assistant": settings.assistant_bubble_color,
            "system": settings.system_bubble_color,
        }.get(self.role, settings.assistant_bubble_color)
        border = settings.accent_color if self.role != "user" else QColor(settings.accent_color).lighter(125).name()
        self.setStyleSheet(
            f"""
            QFrame#Bubble_{self.role} {{
                background: {color};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            QLabel#BubbleMeta {{
                color: {settings.accent_color};
                font-size: {max(9, settings.font_size - 4)}px;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#BubbleText {{
                color: #fff5ea;
                font-size: {settings.font_size}px;
                line-height: 145%;
                background: transparent;
            }}
            """
        )

    def set_maximum_bubble_width(self, viewport_width: int) -> None:
        self.setMaximumWidth(max(260, int(viewport_width * 0.72)))


class ChatView(QScrollArea):
    """Modern widget-based chat stream with reliable wrapping and spacing."""

    def __init__(self, settings: AppearanceSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or AppearanceSettings()
        self._stream_bubble: MessageBubble | None = None
        self._bubbles: list[MessageBubble] = []
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)

        self.container = QWidget()
        self.container.setObjectName("ChatContainer")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(18, 18, 18, 18)
        self.layout.setSpacing(14)
        self.layout.addStretch(1)
        self.setWidget(self.container)
        self.apply_settings(self.settings)

    def add_message(self, speaker: str, text: str, role: str) -> None:
        bubble = MessageBubble(speaker, text, role, self.settings)
        self._insert_bubble(bubble, role)

    def begin_stream(self, speaker: str = "JARVIS", role: str = "assistant") -> None:
        self._stream_bubble = MessageBubble(speaker, "", role, self.settings)
        self._insert_bubble(self._stream_bubble, role)

    def append_stream(self, text: str) -> None:
        if self._stream_bubble is None:
            self.begin_stream()
        assert self._stream_bubble is not None
        self._stream_bubble.append_text(text)
        self._scroll_to_bottom()

    def end_stream(self) -> None:
        self._stream_bubble = None
        self._scroll_to_bottom()

    def apply_settings(self, settings: AppearanceSettings) -> None:
        self.settings = settings
        self.setStyleSheet(
            f"""
            QScrollArea {{
                background: rgba(8, 7, 10, 128);
                border: 1px solid {settings.accent_color};
                border-radius: 16px;
            }}
            QWidget#ChatContainer {{ background: transparent; }}
            QScrollBar:vertical {{ background: rgba(255,255,255,24); width: 10px; border-radius: 5px; }}
            QScrollBar::handle:vertical {{ background: {settings.accent_color}; border-radius: 5px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """
        )
        for bubble in self._bubbles:
            bubble.apply_settings(settings)
            bubble.set_maximum_bubble_width(self.viewport().width())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        for bubble in self._bubbles:
            bubble.set_maximum_bubble_width(self.viewport().width())

    def _insert_bubble(self, bubble: MessageBubble, role: str) -> None:
        bubble.set_maximum_bubble_width(self.viewport().width())
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)
        self.layout.insertWidget(max(0, self.layout.count() - 1), row)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))


class BackgroundWidget(QWidget):
    """Low-cost themed background painter with optional slow animation."""

    def __init__(self, settings: AppearanceSettings) -> None:
        super().__init__()
        self.settings = settings
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)

    def apply_settings(self, settings: AppearanceSettings) -> None:
        self.settings = settings
        self.update()

    def _tick(self) -> None:
        if self.settings.background in {"Stars", "Aurora", "Matrix", "Abstract Waves", "Galaxy", "Nebula"}:
            self.phase = (self.phase + 0.035) % math.tau
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()
        base = QColor(self.settings.theme_color)
        painter.fillRect(rect, base)
        name = self.settings.background
        accent = QColor(self.settings.accent_color)

        if name in {"Earth", "Moon", "Mars", "Jupiter", "Saturn", "Neptune"}:
            self._paint_planet(painter, rect, name, accent)
        elif name in {"Galaxy", "Nebula", "Stars", "Black Hole"}:
            self._paint_space(painter, rect, name, accent)
        elif name == "Aurora":
            self._paint_aurora(painter, rect, accent)
        elif name == "Matrix":
            self._paint_matrix(painter, rect)
        elif name == "Circuit Board":
            self._paint_circuit(painter, rect, accent)
        else:
            self._paint_waves(painter, rect, accent)

    def _paint_planet(self, painter: QPainter, rect: QRectF, name: str, accent: QColor) -> None:
        colors = {
            "Earth": QColor(38, 120, 170),
            "Moon": QColor(145, 145, 135),
            "Mars": QColor(175, 76, 42),
            "Jupiter": QColor(196, 142, 92),
            "Saturn": QColor(204, 158, 93),
            "Neptune": QColor(52, 92, 190),
        }
        planet = colors.get(name, accent)
        center = QPointF(rect.width() * 0.82, rect.height() * 0.2)
        radius = max(rect.width(), rect.height()) * 0.22
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0, planet.lighter(150))
        gradient.setColorAt(1, QColor(planet.red() // 4, planet.green() // 4, planet.blue() // 4, 40))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, radius, radius)
        if name == "Saturn":
            painter.setPen(QPen(QColor(230, 190, 120, 95), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(center.x() - radius * 1.5, center.y() - radius * 0.35, radius * 3, radius * 0.7))

    def _paint_space(self, painter: QPainter, rect: QRectF, name: str, accent: QColor) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
        step = 47 if name != "Stars" else 34
        offset = int(self.phase * 10) % step
        for x in range(offset, int(rect.width()), step):
            for y in range((x * 7) % step, int(rect.height()), step * 2):
                painter.drawPoint(x, y)
        if name in {"Galaxy", "Nebula", "Black Hole"}:
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 60), 2))
            for i in range(4):
                painter.drawArc(QRectF(rect.center().x() - 120 - i * 45, rect.center().y() - 45 - i * 20, 240 + i * 90, 90 + i * 40), 20 * 16, 220 * 16)

    def _paint_aurora(self, painter: QPainter, rect: QRectF, accent: QColor) -> None:
        painter.setPen(QPen(QColor(accent.red(), 220, 180, 75), 3))
        for i in range(5):
            y = rect.height() * (0.2 + i * 0.1)
            path = QPainterPath(QPointF(0, y))
            path.cubicTo(rect.width() * 0.3, y + math.sin(self.phase + i) * 60, rect.width() * 0.6, y - 60, rect.width(), y + 20)
            painter.drawPath(path)

    def _paint_matrix(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor(65, 255, 120, 55), 1))
        for x in range(0, int(rect.width()), 28):
            painter.drawLine(x, 0, x, int(rect.height()))

    def _paint_circuit(self, painter: QPainter, rect: QRectF, accent: QColor) -> None:
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 75), 1))
        for x in range(24, int(rect.width()), 72):
            painter.drawLine(x, 0, x, int(rect.height()))
            for y in range(30, int(rect.height()), 90):
                painter.drawLine(x, y, min(int(rect.width()), x + 42), y)

    def _paint_waves(self, painter: QPainter, rect: QRectF, accent: QColor) -> None:
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 80), 2))
        for i in range(7):
            y = rect.height() * (0.15 + i * 0.12)
            path = QPainterPath(QPointF(0, y))
            path.cubicTo(rect.width() * 0.25, y + 40, rect.width() * 0.65, y - 40, rect.width(), y)
            painter.drawPath(path)



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

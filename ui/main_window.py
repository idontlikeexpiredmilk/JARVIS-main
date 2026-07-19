"""Main PySide6 user interface for the JARVIS assistant."""

from __future__ import annotations

import datetime as dt
import importlib.util

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai.groq import GroqClient
from ai.memory import ConversationMemory
from ai.provider import AIProvider
from config import CONFIG
from system.commands import CommandRouter
from system.monitor import SystemMonitor
from system.weather import WeatherService, WeatherSnapshot
from ui.animations import StartupSequencer
from ui.widgets import AICoreWidget, ChatView, HoloPanel, StatusPanel, WaveformWidget
from voice.listener import VoiceListener
from voice.speaker import Speaker


class WeatherWorker(QObject):
    """Runs the blocking weather HTTP call off the GUI thread."""

    finished = Signal(object)

    def __init__(self, service: WeatherService) -> None:
        super().__init__()
        self.service = service

    @Slot()
    def run(self) -> None:
        self.finished.emit(self.service.fetch())


class AIWorker(QObject):
    """Runs blocking provider calls away from the GUI thread."""

    finished = Signal(str)

    def __init__(self, prompt: str, client: AIProvider, memory: ConversationMemory) -> None:
        super().__init__()
        self.prompt = prompt
        self.client = client
        self.memory = memory

    @Slot()
    def run(self) -> None:
        self.finished.emit(self.client.generate(self.prompt, self.memory))


class VoiceBridge(QObject):
    """Qt signal bridge for callbacks emitted by the Python microphone thread.

    VoiceListener uses threading.Thread, so it must never call MainWindow methods
    directly. Emitting these signals lets Qt queue delivery back to the GUI
    thread where MainWindow owns widgets and creates QThread children.
    """

    command_received = Signal(str)
    status_changed = Signal(str)
    state_changed = Signal(str)


class MainWindow(QMainWindow):
    """Cinematic but lightweight assistant shell."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JARVIS Desktop Assistant")
        self._size_to_screen()
        self.monitor = SystemMonitor()
        self.weather_service = WeatherService()
        self.memory = ConversationMemory(max_turns=CONFIG.max_memory_turns)
        self.groq = GroqClient()
        self.commands = CommandRouter()
        self.ai_thread: QThread | None = None
        self.weather_thread: QThread | None = None
        self.voice_bridge = VoiceBridge(self)
        self.speaker = Speaker(self.voice_bridge.status_changed.emit, self.voice_bridge.state_changed.emit)
        self.voice_bridge.command_received.connect(self.handle_prompt)
        self.voice_bridge.status_changed.connect(self.set_status)
        self.voice_bridge.state_changed.connect(self._set_core_state)
        self.voice_listener = VoiceListener(
            self.voice_bridge.command_received.emit,
            self.voice_bridge.status_changed.emit,
            self.voice_bridge.state_changed.emit,
        )
        self._build_ui()
        self._apply_theme()
        self._wire_timers()
        self._refresh_connection_status()
        self.startup = StartupSequencer(self.set_status)
        self.startup.start()

    def _size_to_screen(self) -> None:
        """Fit the window to the real screen, falling back to 1366x768.

        A fixed size that's larger than the actual resolution forces Qt to
        squeeze/clip the layout to fit, which is what produced the stray
        black regions in panels and the "randomly zooms in" feel. This reads
        the real available screen geometry (e.g. 1366x768 on a typical
        Chromebook) and sizes/centers the window to it; if no screen can be
        detected yet, it falls back to 1366x768 directly instead of guessing.
        """
        fallback_width, fallback_height = 1366, 768
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(640, min(fallback_width, available.width()))
            height = max(480, min(fallback_height, available.height()))
            self.resize(width, height)
            self.move(available.center() - self.rect().center())
        else:
            self.resize(fallback_width, fallback_height)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)

        left = QVBoxLayout()
        self.time_panel = HoloPanel("Time", "--:--")
        self.date_panel = HoloPanel("Date", "--")
        self.weather_panel = HoloPanel("Weather", "Unavailable")
        self.location_panel = HoloPanel("Location", CONFIG.weather_location or "Not set")
        self.cpu_panel = HoloPanel("CPU", "--%")
        self.ram_panel = HoloPanel("RAM", "--%")
        self.disk_panel = HoloPanel("Disk", "--%")
        self.net_panel = HoloPanel("Network", "--")
        self.battery_panel = HoloPanel("Battery", "--")
        self.connection_panel = StatusPanel("Connections")
        for panel in [
            self.time_panel,
            self.date_panel,
            self.weather_panel,
            self.location_panel,
            self.cpu_panel,
            self.ram_panel,
            self.disk_panel,
            self.net_panel,
            self.battery_panel,
            self.connection_panel,
        ]:
            left.addWidget(panel)
        left.addStretch()

        center = QVBoxLayout()
        self.status = QLabel("Booting JARVIS...")
        self.status.setObjectName("StatusLabel")
        self.core = AICoreWidget()
        self.waveform = WaveformWidget()
        center.addWidget(self.status)
        center.addWidget(self.core, stretch=2)
        center.addWidget(self.waveform)

        right = QVBoxLayout()
        self.chat = ChatView()
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command or question...")
        self.send_button = QPushButton("Transmit")
        self.voice_button = QPushButton("Voice")
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.voice_button)
        right.addWidget(self.chat)
        right.addLayout(input_row)

        main.addLayout(left, stretch=1)
        main.addLayout(center, stretch=2)
        main.addLayout(right, stretch=2)

        self.send_button.clicked.connect(self._submit_input)
        self.input.returnPressed.connect(self._submit_input)
        self.voice_button.clicked.connect(self.voice_listener.start)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #08070a; color: #f2e9df; font-family: 'DejaVu Sans'; }
            #StatusLabel { color: #ff9d3d; font-size: 22px; letter-spacing: 2px; padding: 12px; }
            QTextEdit, QLineEdit { background: rgba(18, 14, 10, 210); border: 1px solid #cc6f10; border-radius: 8px; padding: 10px; color: #fdf3e6; }
            QPushButton { background: #241408; border: 1px solid #ff8c1a; border-radius: 8px; padding: 10px 16px; color: #ffd8a8; }
            QPushButton:hover { background: #3a2410; }
            #HoloPanel { border: 1px solid #cc6f10; border-radius: 10px; background: rgba(20, 14, 8, 170); margin: 5px; }
            #PanelTitle { color: #ff9d3d; font-size: 12px; letter-spacing: 2px; }
            #PanelValue { color: #ffffff; font-size: 24px; font-weight: 600; }
            #PanelRow { color: #f0d3ae; font-size: 12px; padding-top: 2px; }
            """
        )

    def _wire_timers(self) -> None:
        self.system_timer = QTimer(self)
        self.system_timer.timeout.connect(self._refresh_system)
        self.system_timer.start(1000)
        self._refresh_system()

        # Weather requires a network call, so it runs rarely and off-thread,
        # unlike the cheap local psutil stats refreshed every second above.
        if self.weather_service.enabled:
            self.weather_timer = QTimer(self)
            self.weather_timer.timeout.connect(self._refresh_weather)
            self.weather_timer.start(max(1, CONFIG.weather_refresh_minutes) * 60_000)
            self._refresh_weather()
        else:
            self.weather_panel.set_value("Disabled")

    @Slot()
    def _submit_input(self) -> None:
        prompt = self.input.text().strip()
        self.input.clear()
        self.handle_prompt(prompt)

    @Slot(str)
    def handle_prompt(self, prompt: str) -> None:
        if not prompt:
            return
        self.chat.add_message("USER", prompt, "user")
        if prompt.lower() in {"clear memory", "reset conversation"}:
            self.memory.clear()
            self._respond("Conversation memory cleared.")
            return
        command = self.commands.handle(prompt)
        if command.handled:
            self._respond(command.message)
            return
        self.set_status("Consulting Groq AI core...")
        self.core.set_state("thinking")
        self._start_ai_worker(prompt)

    def _start_ai_worker(self, prompt: str) -> None:
        self.ai_thread = QThread(self)
        self.ai_worker = AIWorker(prompt, self.groq, self.memory)
        worker = self.ai_worker
        worker.moveToThread(self.ai_thread)
        self.ai_thread.started.connect(worker.run)
        worker.finished.connect(self._respond)
        worker.finished.connect(self.ai_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        self.ai_thread.start()

    @Slot(str)
    def _respond(self, text: str) -> None:
        self.chat.add_message("JARVIS", text, "assistant")
        self.set_status("Systems online.")
        self.speaker.speak(text)

    @Slot(str)
    def set_status(self, text: str) -> None:
        self.status.setText(text)

    @Slot()
    def _refresh_system(self) -> None:
        now = dt.datetime.now()
        self.time_panel.set_value(now.strftime("%H:%M:%S"))
        self.date_panel.set_value(now.strftime("%a, %b %d"))

        snap = self.monitor.snapshot()
        self.cpu_panel.set_value(f"{snap.cpu_percent:.0f}%")
        self.ram_panel.set_value(f"{snap.ram_percent:.0f}%")
        self.disk_panel.set_value(f"{snap.disk_percent:.0f}%")
        self.net_panel.set_value(snap.network_label)
        self.battery_panel.set_value(snap.battery_label)

    def _refresh_weather(self) -> None:
        self.weather_thread = QThread(self)
        self.weather_worker = WeatherWorker(self.weather_service)
        worker = self.weather_worker
        worker.moveToThread(self.weather_thread)
        self.weather_thread.started.connect(worker.run)
        worker.finished.connect(self._apply_weather)
        worker.finished.connect(self.weather_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.weather_thread.finished.connect(self.weather_thread.deleteLater)
        self.weather_thread.start()

    @Slot(object)
    def _apply_weather(self, snapshot: WeatherSnapshot | None) -> None:
        if snapshot is None:
            self.weather_panel.set_value("Unavailable")
            return
        self.weather_panel.set_value(f"{snapshot.temperature_label} {snapshot.description}")
        self.location_panel.set_value(snapshot.location)

    def _refresh_connection_status(self) -> None:
        """Probe connection/engine availability once (cheap, no network calls)."""
        groq_status = "Configured" if self.groq.configured else "No API key"
        mic_status = "Available" if importlib.util.find_spec("speech_recognition") is not None else "Not installed"
        self.connection_panel.set_rows(
            {
                "Groq": groq_status,
                "Microphone": mic_status,
                "Model": CONFIG.groq_model,
            }
        )

    @Slot(str)
    def _set_core_state(self, state: str) -> None:
        self.core.set_state(state)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.voice_listener.stop()
        self.speaker.stop()
        super().closeEvent(event)

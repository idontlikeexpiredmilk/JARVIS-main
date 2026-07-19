"""Main PySide6 user interface for the JARVIS assistant."""

from __future__ import annotations

import datetime as dt
import importlib.util
import os

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ai.groq import GroqClient
from ai.memory import ConversationMemory
from config import CONFIG
from system.commands import CommandRouter
from system.monitor import SystemMonitor
from system.weather import WeatherService, WeatherSnapshot
from services.settings import AppearanceSettings, BUILT_IN_BACKGROUNDS, SettingsService
from services.terminal import TerminalPlan, TerminalService
from ui.animations import StartupSequencer
from ui.widgets import AICoreWidget, BackgroundWidget, ChatView, HoloPanel, StatusPanel, WaveformWidget
from voice.listener import VoiceListener
from voice.speaker import Speaker


class SettingsDialog(QDialog):
    """Small auto-saving settings window for appearance and speech preferences."""

    settings_changed = Signal(object)

    def __init__(self, settings: AppearanceSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("JARVIS Settings")
        self.settings = settings
        layout = QFormLayout(self)

        self.background = QComboBox()
        self.background.addItems(BUILT_IN_BACKGROUNDS)
        self.background.setCurrentText(settings.background)
        self.accent_button = QPushButton(settings.accent_color)
        self.theme_button = QPushButton(settings.theme_color)
        self.user_bubble_button = QPushButton(settings.user_bubble_color)
        self.assistant_bubble_button = QPushButton(settings.assistant_bubble_color)
        self.font_size = QSpinBox()
        self.font_size.setRange(11, 24)
        self.font_size.setValue(settings.font_size)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(55, 100)
        self.opacity.setValue(settings.window_opacity)
        self.tts_voice = QLineEdit(settings.tts_voice)
        self.speech_speed = QSpinBox()
        self.speech_speed.setRange(80, 260)
        self.speech_speed.setValue(settings.speech_speed)
        self.launch_voice = QCheckBox("Start voice listener on launch")
        self.launch_voice.setChecked(settings.launch_voice_on_startup)

        layout.addRow("Background", self.background)
        layout.addRow("Accent color", self.accent_button)
        layout.addRow("Theme color", self.theme_button)
        layout.addRow("User bubble", self.user_bubble_button)
        layout.addRow("Assistant bubble", self.assistant_bubble_button)
        layout.addRow("Font size", self.font_size)
        layout.addRow("Transparency", self.opacity)
        layout.addRow("TTS voice", self.tts_voice)
        layout.addRow("Speech speed", self.speech_speed)
        layout.addRow("Startup", self.launch_voice)

        self.background.currentTextChanged.connect(self._emit)
        self.font_size.valueChanged.connect(self._emit)
        self.opacity.valueChanged.connect(self._emit)
        self.tts_voice.textChanged.connect(self._emit)
        self.speech_speed.valueChanged.connect(self._emit)
        self.launch_voice.toggled.connect(self._emit)
        self.accent_button.clicked.connect(lambda: self._pick_color(self.accent_button))
        self.theme_button.clicked.connect(lambda: self._pick_color(self.theme_button))
        self.user_bubble_button.clicked.connect(lambda: self._pick_color(self.user_bubble_button))
        self.assistant_bubble_button.clicked.connect(lambda: self._pick_color(self.assistant_bubble_button))
        self._style_color_buttons()

    def _pick_color(self, button: QPushButton) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            button.setText(color.name())
            self._style_color_buttons()
            self._emit()

    def _style_color_buttons(self) -> None:
        for button in (self.accent_button, self.theme_button, self.user_bubble_button, self.assistant_bubble_button):
            button.setStyleSheet(f"background: {button.text()}; color: white; padding: 8px;")

    def _emit(self, *args) -> None:
        del args
        self.settings = AppearanceSettings(
            accent_color=self.accent_button.text(),
            theme_color=self.theme_button.text(),
            background=self.background.currentText(),
            window_opacity=self.opacity.value(),
            user_bubble_color=self.user_bubble_button.text(),
            assistant_bubble_color=self.assistant_bubble_button.text(),
            font_size=self.font_size.value(),
            tts_voice=self.tts_voice.text() or "Default",
            speech_speed=self.speech_speed.value(),
            launch_voice_on_startup=self.launch_voice.isChecked(),
        ).sanitized()
        self.settings_changed.emit(self.settings)


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
    """Streams Groq calls away from the GUI thread."""

    chunk = Signal(str)
    finished = Signal(str)

    def __init__(self, prompt: str, client: GroqClient, memory: ConversationMemory) -> None:
        super().__init__()
        self.prompt = prompt
        self.client = client
        self.memory = memory

    @Slot()
    def run(self) -> None:
        chunks: list[str] = []
        for chunk in self.client.stream_generate(self.prompt, self.memory):
            chunks.append(chunk)
            self.chunk.emit(chunk)
        self.finished.emit("".join(chunks))


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
        self.settings_service = SettingsService()
        self.appearance = self.settings_service.load()
        self.groq = GroqClient()
        self.commands = CommandRouter()
        self.terminal = TerminalService()
        self.pending_terminal_plan: TerminalPlan | None = None
        self._last_app_stylesheet = ""
        self._last_window_opacity: float | None = None
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
        if self.appearance.launch_voice_on_startup:
            QTimer.singleShot(500, self.voice_listener.start)
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
        root = BackgroundWidget(self.appearance)
        self.background = root
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(16)

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
        self.chat = ChatView(self.appearance)
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command or question...")
        self.send_button = QPushButton("Transmit")
        self.voice_button = QPushButton("Voice")
        self.stop_button = QPushButton("Stop Speaking")
        self.settings_button = QPushButton("Settings")
        self.execute_button = QPushButton("Execute")
        self.cancel_button = QPushButton("Cancel")
        self.execute_button.hide()
        self.cancel_button.hide()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.voice_button)
        input_row.addWidget(self.stop_button)
        input_row.addWidget(self.settings_button)
        input_row.addWidget(self.execute_button)
        input_row.addWidget(self.cancel_button)
        right.addWidget(self.chat)
        right.addLayout(input_row)

        main.addLayout(left, stretch=1)
        main.addLayout(center, stretch=2)
        main.addLayout(right, stretch=2)

        self.send_button.clicked.connect(self._submit_input)
        self.input.returnPressed.connect(self._submit_input)
        self.voice_button.clicked.connect(self.voice_listener.start)
        self.stop_button.clicked.connect(self._stop_speaking)
        self.settings_button.clicked.connect(self._open_settings)
        self.execute_button.clicked.connect(self._execute_pending_terminal)
        self.cancel_button.clicked.connect(self._cancel_pending_terminal)

    def _apply_theme(self) -> None:
        """Apply appearance settings without touching unsafe Wayland window state."""
        settings = self.appearance
        self._apply_safe_window_opacity(settings)
        stylesheet = self._build_app_stylesheet(settings)
        if stylesheet != self._last_app_stylesheet:
            self.setStyleSheet(stylesheet)
            self._last_app_stylesheet = stylesheet
        self.chat.apply_settings(settings)
        self.background.apply_settings(settings)

    def _build_app_stylesheet(self, settings: AppearanceSettings) -> str:
        """Return a targeted stylesheet instead of restyling every QWidget."""
        return f"""
            QMainWindow {{ background: {settings.theme_color}; color: #f2e9df; font-family: 'DejaVu Sans'; }}
            QLabel {{ color: #f2e9df; font-family: 'DejaVu Sans'; }}
            #StatusLabel {{ color: {settings.accent_color}; font-size: {settings.font_size + 7}px; letter-spacing: 2px; padding: 12px; }}
            QLineEdit {{ background: rgba(18, 14, 10, 220); border: 1px solid {settings.accent_color}; border-radius: 10px; padding: 11px; color: #fdf3e6; font-size: {settings.font_size}px; }}
            QPushButton {{ background: rgba(36, 20, 8, 220); border: 1px solid {settings.accent_color}; border-radius: 10px; padding: 10px 14px; color: #ffd8a8; }}
            QPushButton:hover {{ background: rgba(58, 36, 16, 230); }}
            QPushButton:pressed {{ background: {settings.accent_color}; color: #08070a; }}
            #HoloPanel {{ border: 1px solid {settings.accent_color}; border-radius: 12px; background: rgba(20, 14, 8, 178); margin: 5px; }}
            #PanelTitle {{ color: {settings.accent_color}; font-size: 12px; letter-spacing: 2px; background: transparent; }}
            #PanelValue {{ color: #ffffff; font-size: 24px; font-weight: 600; background: transparent; }}
            #PanelRow {{ color: #f0d3ae; font-size: 12px; padding-top: 2px; background: transparent; }}
        """

    def _apply_safe_window_opacity(self, settings: AppearanceSettings) -> None:
        """Avoid QWindow opacity updates on Wayland/Crostini.

        Qt's Wayland platform has historically reported that window opacity is
        unsupported. On Crostini that unsupported native window update can tear
        down the Wayland connection, so the transparency slider is treated as a
        paint-only preference there. The background/chat widgets still apply the
        rest of the appearance settings instantly.
        """
        if self._is_wayland_session():
            return
        opacity = settings.window_opacity / 100
        if opacity != self._last_window_opacity:
            self.setWindowOpacity(opacity)
            self._last_window_opacity = opacity

    @staticmethod
    def _is_wayland_session() -> bool:
        platform_name = QApplication.platformName().lower()
        return "wayland" in platform_name or bool(os.getenv("WAYLAND_DISPLAY"))

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
        if self.pending_terminal_plan and prompt.lower() in {"yes", "y", "approve", "execute", "run it"}:
            self._execute_pending_terminal()
            return
        if self.pending_terminal_plan and prompt.lower() in {"no", "n", "cancel", "stop"}:
            self._cancel_pending_terminal()
            return
        if prompt.lower() in {"clear memory", "reset conversation"}:
            self.memory.clear()
            self._respond("Conversation memory cleared.")
            return
        command = self.commands.handle(prompt)
        if command.handled:
            self._respond(command.message)
            return
        terminal_plan = self.terminal.build_plan(prompt)
        if terminal_plan is not None:
            self._show_terminal_plan(terminal_plan)
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
        self.chat.begin_stream()
        worker.chunk.connect(self._append_ai_chunk)
        worker.finished.connect(self._finish_ai_stream)
        worker.finished.connect(self.ai_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        self.ai_thread.start()

    @Slot(str)
    def _append_ai_chunk(self, text: str) -> None:
        self.chat.append_stream(text)

    @Slot(str)
    def _finish_ai_stream(self, text: str) -> None:
        self.chat.end_stream()
        self.set_status("Systems online.")
        self.speaker.speak(text)

    @Slot(str)
    def _respond(self, text: str) -> None:
        self.chat.add_message("JARVIS", text, "assistant")
        self.set_status("Systems online.")
        self.speaker.speak(text)

    @Slot()
    def _stop_speaking(self) -> None:
        self.speaker.stop()
        self.set_status("Speech stopped. Groq generation continues.")

    def _show_terminal_plan(self, plan: TerminalPlan) -> None:
        self.pending_terminal_plan = plan
        risk = " Destructive/system-changing command." if plan.destructive else ""
        self.chat.add_message(
            "JARVIS",
            f"Terminal plan: {plan.summary}\nCommand: {plan.display}\n{risk} Approve before I execute.",
            "system",
        )
        self.execute_button.show()
        self.cancel_button.show()
        self.set_status("Awaiting terminal approval.")

    @Slot()
    def _execute_pending_terminal(self) -> None:
        if self.pending_terminal_plan is None:
            return
        plan = self.pending_terminal_plan
        self.pending_terminal_plan = None
        self.execute_button.hide()
        self.cancel_button.hide()
        self.set_status("Executing approved local command...")
        result = self.terminal.execute(plan)
        self._respond(f"Command exited with code {result.returncode}.\n{result.output}")

    @Slot()
    def _cancel_pending_terminal(self) -> None:
        self.pending_terminal_plan = None
        self.execute_button.hide()
        self.cancel_button.hide()
        self._respond("Terminal command cancelled.")

    @Slot()
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.appearance, self)
        dialog.settings_changed.connect(self._apply_settings_update)
        dialog.show()
        self.settings_dialog = dialog

    @Slot(object)
    def _apply_settings_update(self, settings: AppearanceSettings) -> None:
        self.appearance = settings.sanitized()
        self.settings_service.save(self.appearance)
        self._apply_theme()

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

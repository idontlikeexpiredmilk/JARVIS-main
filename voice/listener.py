"""Lightweight optional speech recognition worker."""

from __future__ import annotations

import importlib.util
import threading
from collections.abc import Callable

from config import CONFIG
from voice.audio import suppress_native_audio_stderr


class VoiceListener:
    """Wake-word listener using speech_recognition when installed.

    The GUI can run without this optional dependency; typed commands always work.
    Audio probing is stderr-suppressed by default to avoid noisy ALSA/JACK logs on
    ChromeOS/Crostini systems that lack several optional PCM devices.

    Listening durations/thresholds are configurable (see config.py) so JARVIS
    doesn't cut the user off mid-sentence:
      * wake_word_timeout: how long to wait for speech to start.
      * max_listening_time: hard ceiling on a single phrase's length.
      * silence_timeout: how much silence ends a phrase (tolerates pauses).
      * energy_threshold: microphone sensitivity (0 = auto-calibrate).
    """

    def __init__(
        self,
        on_command: Callable[[str], None],
        on_status: Callable[[str], None],
        on_state: Callable[[str], None] | None = None,
    ) -> None:
        # These callbacks should be Qt Signal.emit callables supplied by the GUI
        # layer. The listener thread only emits data; it never touches widgets or
        # calls MainWindow slots directly.
        self.on_command = on_command
        self.on_status = on_status
        # on_state(str) reports "listening" / "thinking" / "idle" so the GUI can
        # animate the AI core accordingly. Optional for backwards compatibility.
        self.on_state = on_state
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not CONFIG.enable_voice:
            self.on_status("Voice recognition is disabled. Set JARVIS_ENABLE_VOICE=1 to enable it.")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _emit_state(self, state: str) -> None:
        if self.on_state is not None:
            try:
                self.on_state(state)
            except Exception:
                pass

    def _loop(self) -> None:
        if importlib.util.find_spec("speech_recognition") is None:
            self.on_status("Voice recognition unavailable. Install SpeechRecognition and PyAudio.")
            self._running = False
            return

        import speech_recognition as sr

        recognizer = sr.Recognizer()
        # Natural-pause tolerance: how long silence must last before the
        # recognizer decides the user has stopped talking.
        recognizer.pause_threshold = CONFIG.silence_timeout
        recognizer.non_speaking_duration = min(CONFIG.silence_timeout, 0.8)
        if CONFIG.energy_threshold > 0:
            recognizer.energy_threshold = CONFIG.energy_threshold
            recognizer.dynamic_energy_threshold = False
        else:
            recognizer.dynamic_energy_threshold = True

        try:
            with suppress_native_audio_stderr(CONFIG.suppress_audio_errors):
                microphone = sr.Microphone()
        except OSError as exc:
            self.on_status(f"Microphone unavailable: {exc}")
            self._running = False
            return

        self.on_status(f"Listening for wake word: {CONFIG.wake_word.title()}")
        try:
            with suppress_native_audio_stderr(CONFIG.suppress_audio_errors):
                with microphone as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
        except OSError as exc:
            self.on_status(f"Microphone initialization failed: {exc}")
            self._running = False
            return

        while self._running:
            self._emit_state("listening")
            try:
                with suppress_native_audio_stderr(CONFIG.suppress_audio_errors):
                    with microphone as source:
                        audio = recognizer.listen(
                            source,
                            timeout=CONFIG.wake_word_timeout,
                            phrase_time_limit=CONFIG.max_listening_time,
                        )
                self._emit_state("thinking")
                self.on_status("Processing speech...")
                text = recognizer.recognize_google(audio).strip()
            except Exception:
                self._emit_state("idle")
                continue
            self._emit_state("idle")
            lowered = text.lower()
            if lowered.startswith(CONFIG.wake_word):
                command = text[len(CONFIG.wake_word) :].strip(" ,")
                if command:
                    self.on_command(command)
                else:
                    self.on_status(f"Listening for wake word: {CONFIG.wake_word.title()}")
            else:
                self.on_status(f"Listening for wake word: {CONFIG.wake_word.title()}")

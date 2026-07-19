"""Non-blocking text-to-speech wrapper with Piper as the primary engine.

Optimized for responsiveness on low-end hardware:
  * The Piper voice model is loaded once (via the ``piper`` Python package)
    and reused for every utterance instead of re-loading it per call.
  * If the ``piper`` Python package is unavailable, we fall back to invoking
    the Piper CLI per call (slower, but still works).
  * pyttsx3 is kept only as a last-resort fallback, using a single persistent
    engine instance guarded by a lock, since repeatedly creating/destroying
    pyttsx3 engines on Linux is what causes the
    ``ReferenceError: weakly-referenced object no longer exists`` crash.
"""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from config import CONFIG
from voice.audio import suppress_native_audio_stderr


class Speaker:
    """Speaks text without blocking the GUI.

    Piper is used first because it is local, offline, and lightweight enough for
    low-end Linux/ChromeOS systems when paired with a small/low quality voice
    model (e.g. ``en_US-lessac-low``). If Piper or its model is unavailable,
    the class warns once and falls back to pyttsx3 when installed. Missing
    audio dependencies never raise into the GUI thread.
    """

    def __init__(
        self,
        on_warning: Callable[[str], None] | None = None,
        on_state: Callable[[str], None] | None = None,
    ) -> None:
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._stop_requested = False
        self._warned_messages: set[str] = set()
        self._on_warning = on_warning
        self._on_state = on_state

        self._piper_voice = None
        self._piper_load_lock = threading.Lock()
        self._piper_api_unavailable = False

        self._pyttsx3_engine = None
        self._pyttsx3_lock = threading.Lock()
        self._pyttsx3_unavailable = False

    def speak(self, text: str) -> None:
        if not CONFIG.enable_tts:
            return
        self.stop()
        self._stop_requested = False
        self._thread = threading.Thread(target=self._speak_blocking, args=(text,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Immediately interrupt current playback/synthesis and clear queued TTS."""
        self._stop_requested = True
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        if self._pyttsx3_lock.acquire(blocking=False):
            try:
                engine = self._pyttsx3_engine
                if engine is not None:
                    try:
                        engine.stop()
                    except Exception:
                        pass
            finally:
                self._pyttsx3_lock.release()

    def _speak_blocking(self, text: str) -> None:
        clean_text = text.strip()
        if self._stop_requested or not clean_text:
            return
        self._emit_state("speaking")
        try:
            if self._speak_with_piper_preloaded(clean_text):
                return
            if self._stop_requested:
                return
            if self._speak_with_piper_cli(clean_text):
                return
            if self._stop_requested:
                return
            if self._speak_with_pyttsx3(clean_text):
                return
            self._warn_once("No usable TTS engine found. Install Piper or pyttsx3, or set JARVIS_ENABLE_TTS=0.")
        finally:
            self._emit_state("idle")

    def _emit_state(self, state: str) -> None:
        if self._on_state is not None:
            try:
                self._on_state(state)
            except Exception:
                pass

    def _load_piper_voice(self):
        if self._piper_voice is not None or self._piper_api_unavailable:
            return self._piper_voice
        with self._piper_load_lock:
            if self._piper_voice is not None or self._piper_api_unavailable:
                return self._piper_voice
            if importlib.util.find_spec("piper") is None:
                self._piper_api_unavailable = True
                return None
            model_path = Path(CONFIG.piper_model_path).expanduser()
            if not CONFIG.piper_model_path or not model_path.is_file():
                self._piper_api_unavailable = True
                return None
            try:
                piper_module = importlib.import_module("piper")
                voice_cls = getattr(piper_module, "PiperVoice")
                config_path = Path(CONFIG.piper_config_path).expanduser() if CONFIG.piper_config_path else None
                if config_path and config_path.is_file():
                    voice = voice_cls.load(str(model_path), config_path=str(config_path))
                else:
                    voice = voice_cls.load(str(model_path))
                self._piper_voice = voice
                return voice
            except Exception as exc:  # noqa: BLE001
                self._warn_once(f"Piper Python API unavailable ({exc}); using slower CLI fallback.")
                self._piper_api_unavailable = True
                return None

    def _speak_with_piper_preloaded(self, text: str) -> bool:
        voice = self._load_piper_voice()
        if voice is None:
            return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
            wav_path = Path(wav_file.name)
        try:
            start = time.monotonic()
            self._synthesize_with_voice(voice, text, wav_path)
            generation_time = time.monotonic() - start
            print(f"[JARVIS TTS] Generation time: {generation_time:.2f} seconds")
            if self._stop_requested:
                return False
            return self._play_wav(wav_path)
        except Exception as exc:  # noqa: BLE001
            self._warn_once(f"Piper synthesis failed ({exc}); trying CLI fallback.")
            return False
        finally:
            wav_path.unlink(missing_ok=True)

    def _synthesize_with_voice(self, voice, text: str, wav_path: Path) -> None:
        import wave

        with wave.open(str(wav_path), "wb") as wav_file:
            try:
                voice.synthesize_wav(
                    text,
                    wav_file,
                    length_scale=CONFIG.piper_length_scale,
                    noise_scale=CONFIG.piper_noise_scale,
                    noise_w=CONFIG.piper_noise_w,
                )
                return
            except TypeError:
                pass
            except AttributeError:
                pass
            try:
                voice.synthesize_wav(text, wav_file)
                return
            except AttributeError:
                pass
            voice.synthesize(text, wav_file)

    def _speak_with_piper_cli(self, text: str) -> bool:
        piper_path = shutil.which(CONFIG.piper_command)
        if piper_path is None:
            self._warn_once("Piper TTS is not installed; falling back to pyttsx3 if available.")
            return False
        model_path = Path(CONFIG.piper_model_path).expanduser()
        if not CONFIG.piper_model_path or not model_path.is_file():
            self._warn_once("Piper model not configured. Set JARVIS_PIPER_MODEL to a .onnx voice model.")
            return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
            wav_path = Path(wav_file.name)
        try:
            command = self._build_piper_command(piper_path, model_path, wav_path)
            start = time.monotonic()
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL if CONFIG.suppress_audio_errors else None,
            )
            with self._lock:
                self._process = process
            process.communicate(input=text.encode("utf-8"), timeout=120)
            generation_time = time.monotonic() - start
            print(f"[JARVIS TTS] Generation time: {generation_time:.2f} seconds")
            if self._stop_requested or process.returncode != 0:
                return False
            return self._play_wav(wav_path)
        except (OSError, subprocess.SubprocessError):
            self._warn_once("Piper failed to synthesize speech; falling back to pyttsx3 if available.")
            return False
        finally:
            with self._lock:
                self._process = None
            wav_path.unlink(missing_ok=True)

    def _build_piper_command(self, piper_path: str, model_path: Path, wav_path: Path) -> list[str]:
        command = [
            piper_path,
            "--model",
            str(model_path),
            "--output_file",
            str(wav_path),
            "--length_scale",
            str(CONFIG.piper_length_scale),
            "--noise_scale",
            str(CONFIG.piper_noise_scale),
            "--noise_w",
            str(CONFIG.piper_noise_w),
        ]
        if CONFIG.piper_config_path:
            command.extend(["--config", str(Path(CONFIG.piper_config_path).expanduser())])
        if CONFIG.piper_speaker:
            command.extend(["--speaker", CONFIG.piper_speaker])
        return command

    def _play_wav(self, wav_path: Path) -> bool:
        player = self._select_audio_player()
        if player is None:
            self._warn_once("No WAV audio player found. Install aplay or PulseAudio/PipeWire paplay.")
            return False
        with suppress_native_audio_stderr(CONFIG.suppress_audio_errors):
            process = subprocess.Popen(
                [player, str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL if CONFIG.suppress_audio_errors else None,
            )
            with self._lock:
                self._process = process
            process.wait(timeout=120)
        return not self._stop_requested and process.returncode == 0

    def _select_audio_player(self) -> str | None:
        if CONFIG.audio_player:
            configured = shutil.which(CONFIG.audio_player)
            if configured is not None:
                return configured
            self._warn_once(f"Configured audio player '{CONFIG.audio_player}' was not found.")
        for candidate in ("paplay", "aplay", "pw-play"):
            player = shutil.which(candidate)
            if player is not None:
                return player
        return None

    def _get_pyttsx3_engine(self):
        if self._pyttsx3_engine is not None:
            return self._pyttsx3_engine
        try:
            pyttsx3 = importlib.import_module("pyttsx3")
            with suppress_native_audio_stderr(CONFIG.suppress_audio_errors):
                engine = pyttsx3.init()
            self._pyttsx3_engine = engine
            return engine
        except Exception as exc:  # noqa: BLE001
            self._warn_once(f"pyttsx3 could not initialize ({exc}); disabling this fallback.")
            self._pyttsx3_unavailable = True
            return None

    def _speak_with_pyttsx3(self, text: str) -> bool:
        if self._pyttsx3_unavailable:
            return False
        if importlib.util.find_spec("pyttsx3") is None:
            self._pyttsx3_unavailable = True
            return False

        with self._pyttsx3_lock:
            engine = self._get_pyttsx3_engine()
            if engine is None:
                return False
            try:
                start = time.monotonic()
                with suppress_native_audio_stderr(CONFIG.suppress_audio_errors):
                    engine.setProperty("rate", CONFIG.tts_rate)
                    engine.say(text)
                    engine.runAndWait()
                generation_time = time.monotonic() - start
                print(f"[JARVIS TTS] Generation time: {generation_time:.2f} seconds")
                return True
            except (ReferenceError, RuntimeError) as exc:
                self._warn_once(
                    f"pyttsx3 fallback is unreliable on this system ({exc}); "
                    "disabling it for the rest of this session. Piper remains available."
                )
                self._pyttsx3_engine = None
                self._pyttsx3_unavailable = True
                return False
            except Exception as exc:  # noqa: BLE001
                self._warn_once(f"pyttsx3 fallback failed ({exc}); disabling it for this session.")
                self._pyttsx3_engine = None
                self._pyttsx3_unavailable = True
                return False

    def _warn_once(self, message: str) -> None:
        if message in self._warned_messages:
            return
        self._warned_messages.add(message)
        print(f"[JARVIS TTS] {message}")
        if self._on_warning is not None:
            self._on_warning(message)

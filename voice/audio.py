"""Audio backend helpers for noisy Linux/ChromeOS environments."""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator


@contextlib.contextmanager
def suppress_native_audio_stderr(enabled: bool = True) -> Iterator[None]:
    """Temporarily silence C-level ALSA/JACK diagnostics written to stderr.

    PyAudio, PortAudio, pyttsx3, and espeak can emit repeated ALSA/JACK warnings
    directly to file descriptor 2 on ChromeOS/Crostini when optional PCM devices
    are not present. Those warnings are noisy but usually not fatal, so audio
    setup/playback should keep the GUI clean while still failing gracefully.
    """
    if not enabled:
        yield
        return

    stderr_fd = sys.stderr.fileno()
    saved_fd = os.dup(stderr_fd)
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
            yield
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(saved_fd)

"""Persistent local UI settings for JARVIS."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


BUILT_IN_BACKGROUNDS = (
    "Earth",
    "Moon",
    "Mars",
    "Jupiter",
    "Saturn",
    "Neptune",
    "Galaxy",
    "Nebula",
    "Black Hole",
    "Stars",
    "Aurora",
    "Matrix",
    "Circuit Board",
    "Abstract Waves",
)


@dataclass(frozen=True)
class AppearanceSettings:
    """User-customizable settings that are cheap to apply at runtime."""

    accent_color: str = "#ff8c1a"
    theme_color: str = "#08070a"
    background: str = "Saturn"
    window_opacity: int = 100
    user_bubble_color: str = "#2e1c0c"
    assistant_bubble_color: str = "#15100c"
    system_bubble_color: str = "#281e0f"
    font_size: int = 15
    tts_voice: str = "Default"
    speech_speed: int = 165
    launch_voice_on_startup: bool = False

    def sanitized(self) -> "AppearanceSettings":
        background = self.background if self.background in BUILT_IN_BACKGROUNDS else "Saturn"
        return replace(
            self,
            background=background,
            window_opacity=max(55, min(100, int(self.window_opacity))),
            font_size=max(11, min(24, int(self.font_size))),
            speech_speed=max(80, min(260, int(self.speech_speed))),
        )


class SettingsService:
    """Load and save local settings as small JSON.

    The path defaults to the user's config directory and can be overridden in
    tests with ``JARVIS_SETTINGS_PATH``.
    """

    def __init__(self, path: Path | None = None) -> None:
        env_path = os.getenv("JARVIS_SETTINGS_PATH")
        self.path = path or (Path(env_path).expanduser() if env_path else Path.home() / ".config" / "jarvis" / "settings.json")

    def load(self) -> AppearanceSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppearanceSettings()
        if not isinstance(data, dict):
            return AppearanceSettings()
        allowed: dict[str, Any] = {key: data[key] for key in AppearanceSettings.__dataclass_fields__ if key in data}
        try:
            return AppearanceSettings(**allowed).sanitized()
        except (TypeError, ValueError):
            return AppearanceSettings()

    def save(self, settings: AppearanceSettings) -> None:
        clean = settings.sanitized()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(clean), indent=2, sort_keys=True), encoding="utf-8")

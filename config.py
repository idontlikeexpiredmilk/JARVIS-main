"""Application configuration for the JARVIS desktop assistant.

Never hard-code API keys in this file. Set GROQ_API_KEY in your shell
or use a local .env loader before launching the app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class JarvisConfig:
    """Runtime settings used across the application."""

    app_name: str = "JARVIS"
    groq_api_key: str = os.getenv("GROQ_API_KEY", os.getenv("JARVIS_GROQ_API_KEY", ""))
    groq_model: str = os.getenv("JARVIS_GROQ_MODEL", "llama-3.1-8b-instant")
    debug_ai: bool = os.getenv("JARVIS_DEBUG_AI", "1") not in {"0", "false", "False"}
    max_memory_turns: int = int(os.getenv("JARVIS_MAX_MEMORY_TURNS", "12"))
    wake_word: str = os.getenv("JARVIS_WAKE_WORD", "jarvis").lower()
    tts_rate: int = int(os.getenv("JARVIS_TTS_RATE", "165"))
    piper_command: str = os.getenv("JARVIS_PIPER_COMMAND", "piper")
    piper_model_path: str = os.getenv("JARVIS_PIPER_MODEL", "")
    piper_config_path: str = os.getenv("JARVIS_PIPER_CONFIG", "")
    piper_speaker: str = os.getenv("JARVIS_PIPER_SPEAKER", "")
    piper_length_scale: float = float(os.getenv("JARVIS_PIPER_LENGTH_SCALE", "1.0"))
    piper_noise_scale: float = float(os.getenv("JARVIS_PIPER_NOISE_SCALE", "0.667"))
    piper_noise_w: float = float(os.getenv("JARVIS_PIPER_NOISE_W", "0.8"))
    audio_player: str = os.getenv("JARVIS_AUDIO_PLAYER", "")
    enable_tts: bool = os.getenv("JARVIS_ENABLE_TTS", "1") not in {"0", "false", "False"}
    enable_voice: bool = os.getenv("JARVIS_ENABLE_VOICE", "1") not in {"0", "false", "False"}
    suppress_audio_errors: bool = os.getenv("JARVIS_SUPPRESS_AUDIO_ERRORS", "1") not in {"0", "false", "False"}
    animation_fps: int = int(os.getenv("JARVIS_ANIMATION_FPS", "30"))
    command_timeout_seconds: int = int(os.getenv("JARVIS_COMMAND_TIMEOUT", "8"))

    # --- Microphone / listening behavior -----------------------------------
    # wake_word_timeout: how long (seconds) to wait for speech to *start*
    # before giving up on that listen attempt.
    wake_word_timeout: float = float(os.getenv("JARVIS_WAKE_WORD_TIMEOUT", "6"))
    # max_listening_time: hard ceiling (seconds) on a single phrase, so JARVIS
    # can capture full sentences instead of being cut off after ~1 second.
    max_listening_time: float = float(os.getenv("JARVIS_MAX_LISTENING_TIME", "15"))
    # silence_timeout: how long (seconds) of silence ends a phrase. Higher
    # values tolerate natural pauses/breaths without cutting the user off.
    silence_timeout: float = float(os.getenv("JARVIS_SILENCE_TIMEOUT", "1.2"))
    # energy_threshold: microphone sensitivity. 0 = let SpeechRecognition
    # auto-calibrate (dynamic_energy_threshold). Any positive value disables
    # auto-calibration and uses that fixed threshold instead.
    energy_threshold: int = int(os.getenv("JARVIS_ENERGY_THRESHOLD", "0"))

    # --- Weather (optional) --------------------------------------------------
    enable_weather: bool = os.getenv("JARVIS_ENABLE_WEATHER", "1") not in {"0", "false", "False"}
    weather_api_key: str = os.getenv("JARVIS_WEATHER_API_KEY", os.getenv("OPENWEATHER_API_KEY", ""))
    weather_location: str = os.getenv("JARVIS_WEATHER_LOCATION", "")
    weather_units: str = os.getenv("JARVIS_WEATHER_UNITS", "metric")
    weather_refresh_minutes: int = int(os.getenv("JARVIS_WEATHER_REFRESH_MINUTES", "15"))


CONFIG = JarvisConfig()

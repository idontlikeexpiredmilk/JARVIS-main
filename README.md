# JARVIS Desktop Assistant

A lightweight Python desktop assistant with a futuristic JARVIS-style interface, Groq API integration, optional voice I/O, safe local commands, and a live system dashboard.

## Implementation plan

1. **GUI shell and animations**: PySide6 renders a modern desktop assistant with wrapped chat bubbles, lightweight themed backgrounds, an animated 2D AI core, waveform visualization, system panels, and non-blocking startup messages.
2. **AI brain**: `ai/groq.py` calls Groq as the only AI provider, streams tokens as they arrive, and uses bounded conversation memory from `ai/memory.py`.
3. **Voice**: `voice/listener.py` optionally listens for the configured wake word, and `voice/speaker.py` speaks responses without blocking the GUI.
4. **System controls**: `system/commands.py` handles explicit local commands with intent matching so incidental words like "battery" or "system" do not accidentally execute actions.
5. **Terminal assistant**: `services/terminal.py` creates confirm-first plans for common local terminal tasks and executes only after approval.
6. **Settings**: `services/settings.py` persists local appearance, background, font, transparency, TTS, speech speed, and startup preferences.
7. **Polish/performance**: Animations are timer-based 2D painting, avoiding heavy 3D rendering for Celeron-class Chromebooks.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your-groq-api-key"
python main.py
```

Do not commit API keys. The assistant reads the Groq key from `GROQ_API_KEY` (or `JARVIS_GROQ_API_KEY`).

## Groq API verification

This project uses Groq's OpenAI-compatible Chat Completions API:

- Endpoint: `POST https://api.groq.com/openai/v1/chat/completions`
- Required request fields used by JARVIS: `model` and `messages`
- Message format: OpenAI-compatible chat objects with `role` and `content`
- Default model: `llama-3.1-8b-instant`, currently listed by Groq as a production model suitable for low-latency conversational use

You can override the model with `JARVIS_GROQ_MODEL` if Groq changes model availability or if you want a larger model such as `llama-3.3-70b-versatile`.

## Groq troubleshooting

JARVIS prefers Groq's official Python SDK and falls back to a standard-library HTTP request only if the SDK is unavailable. The fallback includes an explicit `User-Agent` because Cloudflare `error code: 1010` means the request was blocked based on the client signature before normal API validation.

Set `JARVIS_DEBUG_AI=1` to print the Groq endpoint, selected model, HTTP status, and failure body. Debug output never prints the API key. Set `JARVIS_DEBUG_AI=0` to silence these diagnostics.

## Piper TTS setup

JARVIS uses Piper as the primary local/offline text-to-speech engine and falls back to pyttsx3 only when Piper or its voice model is unavailable. For a low-end Chromebook, start with a small English model such as `en_US-lessac-low` or another `*-low.onnx` voice.

Example setup:

```bash
# Install Piper; use the packaged binary if your distro provides it, or install the Python package.
python -m pip install piper-tts

# Create a local voices folder, then download a lightweight English .onnx model
# and its matching .onnx.json config from the Piper voices repository.
mkdir -p ~/.local/share/piper/voices
export JARVIS_PIPER_MODEL="$HOME/.local/share/piper/voices/en_US-lessac-low.onnx"
export JARVIS_PIPER_CONFIG="$HOME/.local/share/piper/voices/en_US-lessac-low.onnx.json"
```

Useful TTS options:

- `JARVIS_ENABLE_TTS=0` disables spoken responses.
- `JARVIS_PIPER_COMMAND` overrides the Piper executable name/path.
- `JARVIS_PIPER_MODEL` points to the `.onnx` voice model.
- `JARVIS_PIPER_CONFIG` points to the matching `.onnx.json` config when needed.
- `JARVIS_PIPER_LENGTH_SCALE`, `JARVIS_PIPER_NOISE_SCALE`, and `JARVIS_PIPER_NOISE_W` tune voice speed/style.
- `JARVIS_AUDIO_PLAYER` can force `paplay`, `aplay`, or `pw-play` on Linux/Crostini.

## Audio on ChromeOS/Linux

ChromeOS/Crostini can print noisy ALSA/JACK messages while Python audio libraries probe unavailable sound devices. JARVIS suppresses those native audio diagnostics by default. If audio is not configured yet, typed commands still work. You can disable voice or TTS explicitly:

```bash
export JARVIS_ENABLE_VOICE=0
export JARVIS_ENABLE_TTS=0
```

Set `JARVIS_SUPPRESS_AUDIO_ERRORS=0` only when you need low-level audio debugging output.

## Useful commands

Commands are intentionally short and explicit. Full sentences that merely mention these words are treated as conversation and go to Groq instead.

- `time` or `what time is it`
- `date`
- `battery` or `battery status`
- `system`, `cpu`, `ram`, or `disk`
- `wifi`, `network`, or `ip`
- `open website example.com`
- `open app xterm`
- `clear memory`

## Appearance settings

Open **Settings** in the main window to adjust the accent color, theme color, built-in background, window transparency, chat bubble colors, font size, TTS voice label, speech speed, and startup voice-listener behavior. Settings are saved automatically to `~/.config/jarvis/settings.json` unless `JARVIS_SETTINGS_PATH` is set. On Wayland/Crostini, window opacity is not applied to the native top-level window because Qt only documents `windowOpacity` support for Embedded Linux, macOS, Windows, and X11 with compositing; theme and background colors still update immediately inside the app.

Built-in low-cost backgrounds include Earth, Moon, Mars, Jupiter, Saturn, Neptune, Galaxy, Nebula, Black Hole, Stars, Aurora, Matrix, Circuit Board, and Abstract Waves. They are painted locally with simple Qt drawing primitives so switching is instant and Celeron-class systems stay responsive.

## Terminal assistant

Terminal requests are generated as a visible command plan first. JARVIS waits for the **Execute** button or a typed approval such as `yes` before running anything, and destructive/system-changing plans are labelled. Current local-first plans include:

- `Install ffmpeg`
- `Update packages`
- `Find every Python file`
- `Search this folder for config`
- `Kill Python`

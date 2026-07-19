"""Gemini Developer API client used as the assistant brain."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from ai.memory import ConversationMemory
from config import CONFIG


JARVIS_SYSTEM_PROMPT = """
You are JARVIS, a concise, capable, futuristic desktop AI assistant inspired by
cinematic science-fiction interfaces. You are polite, technically strong, calm,
and practical. Help with coding, system questions, planning, and general tasks.
If a request could affect the local computer, ask for confirmation unless it is
read-only or explicitly safe.
""".strip()


@dataclass
class GeminiClient:
    """Small dependency-light Gemini REST client using the Python standard library."""

    api_key: str = CONFIG.gemini_api_key
    model: str = CONFIG.gemini_model
    timeout: int = 30

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, memory: ConversationMemory) -> str:
        """Send a prompt to Gemini and return the first text response."""
        if not self.configured:
            return (
                "Gemini is not configured. Set JARVIS_GEMINI_API_KEY in your "
                "environment, then restart the assistant."
            )

        memory.add_user(prompt)
        payload = {
            "systemInstruction": {"parts": [{"text": JARVIS_SYSTEM_PROMPT}]},
            "contents": memory.as_gemini_contents(),
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "maxOutputTokens": 1024,
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return f"Gemini HTTP error {exc.code}: {detail[:400]}"
        except urllib.error.URLError as exc:
            return f"Network error while contacting Gemini: {exc.reason}"
        except TimeoutError:
            return "Gemini request timed out."

        text = self._extract_text(data)
        memory.add_assistant(text)
        return text

    @staticmethod
    def _extract_text(data: dict[str, object]) -> str:
        candidates = data.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            return "I received no usable response from Gemini."
        content = candidates[0].get("content", {}) if isinstance(candidates[0], dict) else {}
        parts = content.get("parts", []) if isinstance(content, dict) else []
        texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        return "\n".join(text for text in texts if text).strip() or "Gemini returned an empty response."

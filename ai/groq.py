"""Groq API client used as the assistant brain."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ai.memory import ConversationMemory
from config import CONFIG


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_USER_AGENT = "JARVIS-Desktop-Assistant/0.1 (+https://api.groq.com)"


JARVIS_SYSTEM_PROMPT = """
You are JARVIS, a concise, capable, futuristic desktop AI assistant inspired by
cinematic science-fiction interfaces. You are polite, technically strong, calm,
and practical. Help with coding, system questions, planning, and general tasks.
If a request could affect the local computer, ask for confirmation unless it is
read-only or explicitly safe. If you cannot actually do something for example make
 audio say Im sorry I cannot do that would you like to try something else? The owners name is kyle
 do not call them mrstark or master.
""".strip()


@dataclass
class GroqClient:
    """Groq chat client using the official SDK with a standard-library fallback."""

    api_key: str = CONFIG.groq_api_key
    model: str = CONFIG.groq_model
    timeout: int = 30
    debug: bool = CONFIG.debug_ai

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, memory: ConversationMemory) -> str:
        """Send a prompt to Groq and return the first assistant message."""
        if not self.configured:
            return (
                "Groq is not configured. Set GROQ_API_KEY in your environment, "
                "then restart the assistant."
            )

        memory.add_user(prompt)
        payload = self._build_payload(memory)
        self._debug(f"Groq endpoint: {GROQ_CHAT_COMPLETIONS_URL}")
        self._debug(f"Groq model: {self.model}")

        start = time.monotonic()
        if importlib.util.find_spec("groq") is not None:
            text = self._generate_with_official_client(payload)
        else:
            self._debug("Groq SDK not installed; using urllib fallback with explicit User-Agent.")
            text = self._generate_with_urllib(payload)
        response_time = time.monotonic() - start
        print(f"[JARVIS AI] Response time: {response_time:.2f} seconds")

        if not text.startswith("Groq HTTP error") and not text.startswith("Network error"):
            memory.add_assistant(text)
        return text

    def _generate_with_official_client(self, payload: dict[str, object]) -> str:
        """Send the request with Groq's official Python client when installed."""
        groq_module = importlib.import_module("groq")
        client = groq_module.Groq(api_key=self.api_key, timeout=self.timeout)
        try:
            raw_response = client.chat.completions.with_raw_response.create(**payload)
            status_code = getattr(raw_response, "status_code", None)
            if status_code is None and hasattr(raw_response, "http_response"):
                status_code = getattr(raw_response.http_response, "status_code", None)
            self._debug(f"Groq HTTP status: {status_code or 200}")
            completion = raw_response.parse()
            return self._extract_text_from_sdk_completion(completion)
        except Exception as exc:
            status_code = getattr(exc, "status_code", "unknown")
            body = self._exception_body(exc)
            self._debug(f"Groq HTTP status: {status_code}")
            self._debug(f"Groq failure body: {body}")
            return f"Groq HTTP error {status_code}: {body}"

    def _generate_with_urllib(self, payload: dict[str, object]) -> str:
        """Fallback HTTP implementation with explicit headers and User-Agent."""
        request = urllib.request.Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status_code = response.status
                body = response.read().decode("utf-8")
                self._debug(f"Groq HTTP status: {status_code}")
                data = json.loads(body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self._debug(f"Groq HTTP status: {exc.code}")
            self._debug(f"Groq failure body: {detail}")
            return f"Groq HTTP error {exc.code}: {detail[:800]}"
        except urllib.error.URLError as exc:
            self._debug("Groq HTTP status: unavailable")
            self._debug(f"Groq failure body: {exc.reason}")
            return f"Network error while contacting Groq: {exc.reason}"
        except TimeoutError:
            self._debug("Groq HTTP status: timeout")
            return "Groq request timed out."

        return self._extract_text(data)

    def _build_payload(self, memory: ConversationMemory) -> dict[str, object]:
        """Build the Groq OpenAI-compatible chat completions payload.

        Groq's Chat Completions API requires `model` and `messages`; the message
        format follows OpenAI-compatible `role`/`content` chat messages.
        """
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                *memory.as_chat_messages(),
            ],
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 1024,
        }

    def _build_headers(self) -> dict[str, str]:
        """Build redaction-safe HTTP headers for the urllib fallback."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": GROQ_USER_AGENT,
        }

    @staticmethod
    def _extract_text(data: dict[str, object]) -> str:
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return "I received no usable response from Groq."
        choice = choices[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        return str(content).strip() or "Groq returned an empty response."

    @staticmethod
    def _extract_text_from_sdk_completion(completion: Any) -> str:
        choices = getattr(completion, "choices", [])
        if not choices:
            return "I received no usable response from Groq."
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "") if message is not None else ""
        return str(content).strip() or "Groq returned an empty response."

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[JARVIS AI] {message}", file=sys.stderr)

    @staticmethod
    def _exception_body(exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            text = getattr(response, "text", None)
            if text:
                return str(text)[:800]
        body = getattr(exc, "body", None)
        if body:
            return str(body)[:800]
        return str(exc)[:800]

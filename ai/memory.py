"""Conversation memory management for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ConversationMemory:
    """Stores a bounded conversation history in OpenAI/Groq-compatible chat format."""

    max_turns: int = 12
    _messages: list[dict[str, object]] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self._add("user", text)

    def add_assistant(self, text: str) -> None:
        self._add("model", text)

    def clear(self) -> None:
        self._messages.clear()

    def as_chat_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for role, text in self.transcript():
            messages.append({"role": "assistant" if role == "model" else role, "content": text})
        return messages

    def transcript(self) -> Iterable[tuple[str, str]]:
        for message in self._messages:
            role = str(message["role"])
            parts = message.get("parts", [])
            text = " ".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
            yield role, text

    def _add(self, role: str, text: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return
        self._messages.append({"role": role, "parts": [{"text": clean_text}]})
        max_messages = self.max_turns * 2
        if len(self._messages) > max_messages:
            self._messages = self._messages[-max_messages:]

"""Provider interfaces for swappable AI backends."""

from __future__ import annotations

from typing import Protocol

from ai.memory import ConversationMemory


class AIProvider(Protocol):
    """Minimal interface the UI needs from an AI provider."""

    def generate(self, prompt: str, memory: ConversationMemory) -> str:
        """Return an assistant response for the prompt and conversation memory."""

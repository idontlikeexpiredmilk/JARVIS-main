"""Tests for the Groq OpenAI-compatible chat completions client."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace

from ai.groq import GROQ_CHAT_COMPLETIONS_URL, GROQ_USER_AGENT, GroqClient, JARVIS_SYSTEM_PROMPT
from ai.memory import ConversationMemory


class GroqClientTests(unittest.TestCase):
    def test_payload_matches_openai_compatible_chat_completions_shape(self) -> None:
        memory = ConversationMemory(max_turns=2)
        memory.add_user("Status report")
        memory.add_assistant("Systems online.")

        payload = GroqClient(api_key="test-key", model="llama-3.1-8b-instant")._build_payload(memory)

        self.assertEqual(payload["model"], "llama-3.1-8b-instant")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                {"role": "user", "content": "Status report"},
                {"role": "assistant", "content": "Systems online."},
            ],
        )
        self.assertEqual(payload["temperature"], 0.7)
        self.assertEqual(payload["top_p"], 0.9)
        self.assertEqual(payload["max_tokens"], 1024)

    def test_endpoint_matches_groq_openai_compatible_chat_completions_url(self) -> None:
        self.assertEqual(GROQ_CHAT_COMPLETIONS_URL, "https://api.groq.com/openai/v1/chat/completions")

    def test_headers_include_required_values_without_debug_exposure(self) -> None:
        headers = GroqClient(api_key="secret-key", model="llama-3.1-8b-instant")._build_headers()

        self.assertEqual(headers["Authorization"], "Bearer secret-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["User-Agent"], GROQ_USER_AGENT)

        stream = io.StringIO()
        with redirect_stderr(stream):
            GroqClient(api_key="secret-key", model="llama-3.1-8b-instant", debug=True)._debug(
                "Groq model: llama-3.1-8b-instant"
            )
        self.assertNotIn("secret-key", stream.getvalue())

    def test_extract_text_reads_first_choice_message_content(self) -> None:
        response = {"choices": [{"message": {"content": "At your service."}}]}

        self.assertEqual(GroqClient._extract_text(response), "At your service.")

    def test_extract_text_from_sdk_completion(self) -> None:
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Systems online."))]
        )

        self.assertEqual(GroqClient._extract_text_from_sdk_completion(completion), "Systems online.")


if __name__ == "__main__":
    unittest.main()

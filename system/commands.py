"""Safe local command helpers for JARVIS."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import webbrowser
from dataclasses import dataclass
from shlex import split

from system.monitor import SystemMonitor


@dataclass
class CommandResult:
    handled: bool
    message: str


class CommandRouter:
    """Routes explicit safe commands without exposing a general shell.

    Matching is intent based: compact commands and direct requests execute,
    while incidental mentions such as "my battery died yesterday" fall through
    to Groq as normal conversation.
    """

    _TIME_PATTERNS = (r"time", r"what'?s the time", r"what time is it", r"current time")
    _DATE_PATTERNS = (r"date", r"today'?s date", r"what'?s the date", r"what day is it")
    _BATTERY_PATTERNS = (r"battery", r"battery status", r"check battery", r"what'?s my battery")
    _SYSTEM_PATTERNS = (r"system", r"system info", r"system status", r"cpu", r"ram", r"memory", r"disk")
    _WIFI_PATTERNS = (r"wifi", r"network", r"ip", r"ip address")

    def __init__(self) -> None:
        self.monitor = SystemMonitor()

    def handle(self, text: str) -> CommandResult:
        raw = text.strip()
        command = self._normalize(raw)
        if not command:
            return CommandResult(False, "")
        if self._matches(command, self._TIME_PATTERNS):
            return CommandResult(True, f"The current time is {dt.datetime.now():%I:%M %p}.")
        if self._matches(command, self._DATE_PATTERNS):
            return CommandResult(True, f"Today is {dt.datetime.now():%A, %B %d, %Y}.")
        if self._matches(command, self._BATTERY_PATTERNS):
            return CommandResult(True, f"Battery: {self.monitor.snapshot().battery_label}.")
        if self._matches(command, self._SYSTEM_PATTERNS):
            snap = self.monitor.snapshot()
            if command == "cpu":
                return CommandResult(True, f"CPU usage is {snap.cpu_percent:.0f}%.")
            if command in {"ram", "memory"}:
                return CommandResult(True, f"RAM usage is {snap.ram_percent:.0f}%.")
            if command == "disk":
                return CommandResult(True, f"Disk usage is {snap.disk_percent:.0f}%.")
            return CommandResult(True, f"CPU {snap.cpu_percent:.0f}%, RAM {snap.ram_percent:.0f}%, disk {snap.disk_percent:.0f}%.")
        if self._matches(command, self._WIFI_PATTERNS):
            snap = self.monitor.snapshot()
            return CommandResult(True, f"Network: {snap.network_label}.")
        if command in {"volume", "clipboard", "notes", "weather", "terminal"}:
            return CommandResult(True, f"{command.title()} is available as a local module, but this shortcut is not configured yet.")
        if command.startswith("open website "):
            url = raw.partition("open website ")[2].strip()
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            webbrowser.open(url)
            return CommandResult(True, f"Opening {url}.")
        if command.startswith("open app "):
            app = raw.partition("open app ")[2].strip()
            if not app:
                return CommandResult(True, "Tell me which application to open.")
            try:
                subprocess.Popen(split(app), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as exc:
                return CommandResult(True, f"I could not open {app}: {exc}")
            return CommandResult(True, f"Opening {app}.")
        if command in {"clear memory", "reset conversation"}:
            return CommandResult(False, "")
        return CommandResult(False, "")

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[?!.,]+$", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    @classmethod
    def _matches(cls, command: str, patterns: tuple[str, ...]) -> bool:
        return any(re.fullmatch(pattern, command) for pattern in patterns)

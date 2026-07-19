"""Safe local command helpers for JARVIS."""

from __future__ import annotations

import datetime as dt
import subprocess
import webbrowser
from dataclasses import dataclass
from shlex import split

from config import CONFIG
from system.monitor import SystemMonitor


@dataclass
class CommandResult:
    handled: bool
    message: str


class CommandRouter:
    """Routes explicit safe commands without exposing a general shell."""

    def __init__(self) -> None:
        self.monitor = SystemMonitor()

    def handle(self, text: str) -> CommandResult:
        command = text.strip().lower()
        if not command:
            return CommandResult(False, "")
        if "time" in command:
            return CommandResult(True, f"The current time is {dt.datetime.now():%I:%M %p}.")
        if "date" in command:
            return CommandResult(True, f"Today is {dt.datetime.now():%A, %B %d, %Y}.")
        if "cpu" in command or "ram" in command or "system" in command:
            snap = self.monitor.snapshot()
            return CommandResult(
                True,
                f"CPU {snap.cpu_percent:.0f}%, RAM {snap.ram_percent:.0f}%, disk {snap.disk_percent:.0f}%.",
            )
        if command.startswith("open website "):
            url = text.partition("open website ")[2].strip()
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            webbrowser.open(url)
            return CommandResult(True, f"Opening {url}.")
        if command.startswith("open app "):
            app = text.partition("open app ")[2].strip()
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

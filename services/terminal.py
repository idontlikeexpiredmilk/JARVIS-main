"""Confirm-first terminal assistant service."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import CONFIG


@dataclass
class TerminalPlan:
    """A shell command that must be shown to the user before execution."""

    summary: str
    command: list[str]
    destructive: bool = False

    @property
    def display(self) -> str:
        return " ".join(shlex.quote(part) for part in self.command)


@dataclass
class TerminalResult:
    output: str
    returncode: int


class TerminalService:
    """Maps common local maintenance requests to safe commands.

    This intentionally avoids free-form shell generation. Unknown terminal
    requests are sent to Groq for reasoning instead of being executed locally.
    """

    def build_plan(self, text: str) -> TerminalPlan | None:
        command = text.strip().lower()
        if not command:
            return None
        if re.fullmatch(r"(find|list|show) (all |every )?python files?", command):
            return TerminalPlan("Find Python files in this folder", ["find", ".", "-name", "*.py", "-type", "f"])
        if re.fullmatch(r"search (this folder|folder|files)( for)? .+", command):
            query = re.sub(r"^search (this folder|folder|files)( for)?\s+", "", text, flags=re.I).strip()
            rg = shutil.which("rg") or "grep"
            if Path(rg).name == "rg":
                return TerminalPlan(f"Search this folder for {query!r}", [rg, "--hidden", "--glob", "!.git", query, "."])
            return TerminalPlan(f"Search this folder for {query!r}", [rg, "-R", query, "."])
        if re.fullmatch(r"install [\w.+-]+", command):
            package = text.split(maxsplit=1)[1]
            manager = self._package_manager()
            return TerminalPlan(f"Install {package}", [*manager, "install", "-y", package], destructive=True)
        if command in {"update packages", "update system", "upgrade packages"}:
            manager = self._package_manager()
            update = "upgrade" if command.startswith("upgrade") else "update"
            extra = ["-y"] if update == "upgrade" else []
            return TerminalPlan(f"Run package {update}", [*manager, update, *extra], destructive=True)
        if command in {"kill python", "stop python", "kill python processes"}:
            return TerminalPlan("Terminate Python processes owned by this user", ["pkill", "-u", "$USER", "-f", "python"], destructive=True)
        return None

    def execute(self, plan: TerminalPlan) -> TerminalResult:
        command = [part if part != "$USER" else self._current_user() for part in plan.command]
        try:
            completed = subprocess.run(
                command,
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                timeout=CONFIG.command_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return TerminalResult("Command timed out before completion.", 124)
        except OSError as exc:
            return TerminalResult(f"Could not execute command: {exc}", 127)
        output = (completed.stdout + completed.stderr).strip() or "Command completed with no output."
        return TerminalResult(output[:4000], completed.returncode)

    def _package_manager(self) -> list[str]:
        for candidate in ("apt", "dnf", "pacman", "brew"):
            path = shutil.which(candidate)
            if path and candidate == "apt":
                return [path]
            if path and candidate == "dnf":
                return [path]
            if path and candidate == "pacman":
                return [path, "-S"]
            if path and candidate == "brew":
                return [path]
        return ["apt"]

    @staticmethod
    def _current_user() -> str:
        import getpass

        return getpass.getuser()

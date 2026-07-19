"""Command intent tests for local-first routing."""

from __future__ import annotations

import sys
from types import SimpleNamespace

if "psutil" not in sys.modules:
    sys.modules["psutil"] = SimpleNamespace(
        cpu_percent=lambda interval=None: 12.0,
        virtual_memory=lambda: SimpleNamespace(percent=34.0),
        disk_usage=lambda path: SimpleNamespace(percent=56.0),
        net_if_stats=lambda: {"wlan0": SimpleNamespace(isup=True)},
        sensors_battery=lambda: SimpleNamespace(percent=78.0, power_plugged=False),
    )

from services.terminal import TerminalService
from system.commands import CommandRouter


def test_battery_sentence_does_not_trigger_command() -> None:
    result = CommandRouter().handle("My battery died yesterday.")

    assert not result.handled


def test_system_recommendation_does_not_trigger_command() -> None:
    result = CommandRouter().handle("What system do you recommend?")

    assert not result.handled


def test_direct_battery_command_triggers() -> None:
    result = CommandRouter().handle("battery status")

    assert result.handled
    assert "Battery:" in result.message


def test_one_word_cpu_command_triggers() -> None:
    result = CommandRouter().handle("cpu")

    assert result.handled
    assert "CPU" in result.message


def test_terminal_plan_requires_confirmation() -> None:
    plan = TerminalService().build_plan("Find every Python file")

    assert plan is not None
    assert plan.command[:2] == ["find", "."]

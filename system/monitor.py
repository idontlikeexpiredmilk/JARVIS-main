"""Lightweight system telemetry collection."""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class SystemSnapshot:
    cpu_percent: float
    ram_percent: float
    disk_percent: float
    network_label: str
    battery_label: str


class SystemMonitor:
    """Collects simple system stats for dashboard widgets."""

    def snapshot(self) -> SystemSnapshot:
        battery = psutil.sensors_battery()
        battery_label = "Unavailable"
        if battery is not None:
            plugged = "AC" if battery.power_plugged else "Battery"
            battery_label = f"{battery.percent:.0f}% ({plugged})"

        net = psutil.net_if_stats()
        online = any(stats.isup for stats in net.values())
        return SystemSnapshot(
            cpu_percent=psutil.cpu_percent(interval=None),
            ram_percent=psutil.virtual_memory().percent,
            disk_percent=psutil.disk_usage("/").percent,
            network_label="Online" if online else "Offline",
            battery_label=battery_label,
        )

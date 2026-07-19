"""Settings persistence tests for local UI customization."""

from services.settings import AppearanceSettings, BUILT_IN_BACKGROUNDS, SettingsService


def test_settings_persist_after_restart(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    expected = AppearanceSettings(background="Mars", accent_color="#44aaff", font_size=18, window_opacity=88)

    service.save(expected)
    reloaded = SettingsService(path).load()

    assert reloaded.background == "Mars"
    assert reloaded.accent_color == "#44aaff"
    assert reloaded.font_size == 18
    assert reloaded.window_opacity == 88


def test_all_requested_backgrounds_are_available() -> None:
    requested = {
        "Earth",
        "Moon",
        "Mars",
        "Jupiter",
        "Saturn",
        "Neptune",
        "Galaxy",
        "Nebula",
        "Black Hole",
        "Stars",
        "Aurora",
        "Matrix",
        "Circuit Board",
        "Abstract Waves",
    }

    assert requested.issubset(set(BUILT_IN_BACKGROUNDS))

from __future__ import annotations

import json

import pytest

from fm27_analyst import plugin_install, updater


@pytest.fixture
def steam(tmp_path):
    root = tmp_path / "Steam"
    lib2 = tmp_path / "games"
    (root / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0" { "path" "%s" }\n "1" { "path" "%s" }\n}\n'
        % (str(root).replace("\\", "\\\\"), str(lib2).replace("\\", "\\\\")), encoding="utf-8")
    demo = lib2 / "steamapps" / "common" / "Football Manager 27 Demo"
    (demo / "BepInEx" / "plugins").mkdir(parents=True)
    (lib2 / "steamapps" / "common" / "Football Manager 26 Demo").mkdir()
    (lib2 / "steamapps" / "common" / "dota 2 beta").mkdir()
    return root, demo


def test_finds_fm27_in_second_library(steam):
    root, demo = steam
    games = plugin_install.find_games(plugin_install.steam_libraries(str(root)))
    assert games == [demo]


def test_installs_then_reports_current_then_updates(steam, tmp_path):
    root, demo = steam
    dll = tmp_path / "FM27AnalystBridge.dll"
    dll.write_bytes(b"v1")
    st = plugin_install.ensure_plugin([demo], dll)
    assert st.games[0].plugin == "installed"
    target = demo / "BepInEx" / "plugins" / "FM27AnalystBridge" / "FM27AnalystBridge.dll"
    assert target.read_bytes() == b"v1"
    assert plugin_install.ensure_plugin([demo], dll).games[0].plugin == "current"
    dll.write_bytes(b"v2")
    assert plugin_install.ensure_plugin([demo], dll).games[0].plugin == "updated"
    assert target.read_bytes() == b"v2"


def test_no_bepinex_is_reported_not_created(tmp_path):
    game = tmp_path / "Football Manager 27"
    game.mkdir()
    dll = tmp_path / "p.dll"
    dll.write_bytes(b"x")
    st = plugin_install.ensure_plugin([game], dll)
    assert st.games[0].plugin == "no_bepinex" and not (game / "BepInEx").exists()


def test_locked_plugin_reported(steam, tmp_path, monkeypatch):
    _, demo = steam
    dll = tmp_path / "p.dll"
    dll.write_bytes(b"new")

    def locked(*a, **k):
        raise PermissionError("in use")

    monkeypatch.setattr(plugin_install.Path, "replace", locked)
    st = plugin_install.ensure_plugin([demo], dll)
    assert st.games[0].plugin == "outdated_locked" and "Закройте FM27" in st.games[0].message


def test_bundled_plugin_present():
    p = plugin_install.bundled_plugin()
    assert p is not None and p.stat().st_size > 10_000


def release(tag, assets):
    return lambda url, timeout=10: json.dumps({"tag_name": tag, "assets": assets, "body": "Что нового",
                                               "html_url": "https://github.com/x"}).encode()


SETUP = {"name": "FM27.Analyst_0.3.0_x64-setup.exe",
         "browser_download_url": "https://github.com/Label777/FM27Analyst/releases/download/v0.3.0/FM27.Analyst_0.3.0_x64-setup.exe"}


def test_update_check():
    assert updater.parse_version("v0.10.1") > updater.parse_version("0.9.9")
    info = updater.check(release("v0.3.0", [{"name": "x.msi"}, SETUP]), current="0.2.0")
    assert info.available and info.latest == "0.3.0" and info.url.endswith("-setup.exe")
    assert not updater.check(release("v0.2.0", [SETUP]), current="0.2.0").available
    assert not updater.check(release("v0.3.0", []), current="0.2.0").available  # нет установщика — нечего ставить

    def offline(url, timeout=10):
        raise OSError("нет сети")

    off = updater.check(offline, current="0.2.0")
    assert not off.available and "нет сети" in off.error


def test_installer_only_from_own_releases():
    with pytest.raises(ValueError):
        updater.download_and_run("https://evil.example/setup.exe", fetch=lambda u, timeout=0: b"")

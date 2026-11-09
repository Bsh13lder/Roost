"""``scripts/publish_mobile.sh`` with a fake ``flutter``: it builds debug unless a release signing setup exists,
copies the APK under its versioned name and writes a ``latest.json`` the gateway accepts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from roost.mobile_update.release import read_latest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_mobile.sh"
FAKE_FLUTTER = """#!/usr/bin/env bash
set -e
kind="${3#--}"
mkdir -p build/app/outputs/flutter-apk
printf 'apk-%s' "$kind" > "build/app/outputs/flutter-apk/app-$kind.apk"
"""


def _project(tmp_path: Path, version: str = "1.0.1+2", app_version: str | None = None) -> tuple[Path, Path]:
    src = tmp_path / "mobile-src"
    (src / "android").mkdir(parents=True)
    (src / "lib").mkdir()
    (src / "pubspec.yaml").write_text(f"name: roost_mobile\nversion: {version}\n")
    (src / "lib" / "app_version.dart").write_text(f"const appVersion = '{app_version or version}';\n")
    flutter = tmp_path / "flutter"
    flutter.write_text(FAKE_FLUTTER)
    flutter.chmod(0o755)
    return src, flutter


def _run(tmp_path: Path, src: Path, flutter: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "ROOST_MOBILE_SRC": str(src), "ROOST_MOBILE_DIR": str(tmp_path / "out"),
           "FLUTTER": str(flutter)}
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30)


def test_publishes_a_slim_release_build_with_a_valid_latest_json(tmp_path):
    src, flutter = _project(tmp_path)
    done = _run(tmp_path, src, flutter, "Update check inside the app")
    assert done.returncode == 0, done.stderr
    assert "release" in done.stdout and "debug key" in done.stdout   # no key.properties: the debug signing key
    assert "--target-platform android-arm64" in done.stdout
    out = tmp_path / "out"
    apk = out / "roost-1.0.1+2.apk"
    assert apk.read_bytes() == b"apk-release"
    latest = json.loads((out / "latest.json").read_text())
    assert latest == {"version": "1.0.1", "build": 2, "file": apk.name,
                      "sha256": hashlib.sha256(b"apk-release").hexdigest(), "notes": "Update check inside the app"}
    assert read_latest(out) is not None
    assert sorted(p.name for p in out.iterdir()) == ["latest.json", apk.name]   # no temp files left


def test_says_when_its_own_signing_setup_is_used(tmp_path):
    src, flutter = _project(tmp_path)
    (src / "android" / "key.properties").write_text("storeFile=x\n")
    done = _run(tmp_path, src, flutter)
    assert done.returncode == 0, done.stderr
    assert "key.properties" in done.stdout
    assert (tmp_path / "out" / "roost-1.0.1+2.apk").read_bytes() == b"apk-release"


@pytest.mark.parametrize("version", ["1.0.1", "1.0+2", "abc", "1.0.1+0"])
def test_refuses_a_bad_version(tmp_path, version):
    src, flutter = _project(tmp_path, version)
    done = _run(tmp_path, src, flutter)
    assert done.returncode != 0
    assert not (tmp_path / "out" / "latest.json").exists()


def test_refuses_when_the_app_version_constant_differs_from_pubspec(tmp_path):
    src, flutter = _project(tmp_path, version="1.0.2+3", app_version="1.0.1+2")
    done = _run(tmp_path, src, flutter)
    assert done.returncode != 0
    assert "app_version.dart" in done.stderr
    assert not (tmp_path / "out" / "latest.json").exists()

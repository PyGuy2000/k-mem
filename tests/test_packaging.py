"""The library installs as a package.

The plugin's launchers put ``plugins/k-mem/lib`` on ``sys.path`` themselves, so
nothing in the plugin path exercises ``pyproject.toml``. A repo that imports
``kmem`` from its own CI does, and a broken package config would fail only
there, on a machine nobody is watching. Building the wheel here keeps that
failure in this suite.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Build from a copy. setuptools writes build/ and *.egg-info into the
    # source tree it is given, and a test must not leave those in the repo.
    src = tmp_path_factory.mktemp("src")
    for rel in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy(ROOT / rel, src / rel)
    shutil.copytree(ROOT / "plugins" / "k-mem" / "lib", src / "plugins" / "k-mem" / "lib",
                    ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    out = tmp_path_factory.mktemp("wheel")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-q", "-w", str(out), str(src)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    # A build failure is the finding, never a skip: skipping here is how a
    # broken package config would stay green in this suite.
    assert proc.returncode == 0, proc.stderr.strip()[-600:]
    wheels = list(out.glob("k_mem-*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def test_wheel_carries_the_package(wheel: Path) -> None:
    names = zipfile.ZipFile(wheel).namelist()
    assert "kmem/__init__.py" in names
    assert "kmem/context/compiler.py" in names, "the resolver is what a consumer imports"
    assert "kmem/hooks/read_gate.py" in names
    assert not any(n.startswith("plugins/") or n.startswith("lib/") for n in names), (
        "package-dir must strip the plugin path, or `import kmem` fails"
    )


def test_wheel_declares_the_console_script(wheel: Path) -> None:
    zf = zipfile.ZipFile(wheel)
    entry = next(n for n in zf.namelist() if n.endswith("entry_points.txt"))
    assert "kmem = kmem.cli:main" in zf.read(entry).decode()


def test_wheel_version_matches_the_package(wheel: Path) -> None:
    sys.path.insert(0, str(ROOT / "plugins" / "k-mem" / "lib"))
    from kmem import __version__

    assert f"k_mem-{__version__}-" in wheel.name, (wheel.name, __version__)

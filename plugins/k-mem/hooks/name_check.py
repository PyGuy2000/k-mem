#!/usr/bin/env python3
"""Launcher: puts the plugin's lib on sys.path and runs kmem.hooks.name_check."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from kmem.hooks.name_check import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

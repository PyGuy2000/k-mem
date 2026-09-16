"""Hook entry points. Each module exposes ``main(argv) -> int`` and reads the
Claude Code hook payload from stdin.

Exit codes follow the hook contract: 0 allows, 2 blocks with stderr fed back
to the model. A hook that cannot decide fails OPEN and logs why; a harness
fault must never block all editing or break a session.

Wired by ``hooks/hooks.json`` in the plugin through thin launchers under
``hooks/``; also reachable as ``kmem hook <name>`` for manual runs.
"""

from __future__ import annotations

from . import docs_check, name_check, outbox_guard, read_gate, session_start, sweep, write_guard

HOOKS = {
    "read-gate": read_gate.main,
    "write-guard": write_guard.main,
    "sweep": sweep.main,
    "name-check": name_check.main,
    "session-start": session_start.main,
    "outbox-guard": outbox_guard.main,
    "docs-check": docs_check.main,
}

__all__ = ["HOOKS"]

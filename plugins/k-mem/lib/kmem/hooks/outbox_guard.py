"""Stop: the guard for the write-side memory leak.

WHY. Session-START delivery of memory works (handoff inbox, inventory). The
leak is session END: decisions made in a long session die with it unless a
handoff note or memory file gets written, and by then nobody is reminded to
write one. This fires once per session, only when the session is
demonstrably long AND leaves modified tracked files or project notes behind
with no handoff queued during the session. It blocks the stop exactly once
(exit 2, stderr fed to the model) so the reminder lands in model context at
the one moment it is actionable.

Not a nag: three conditions must all hold, and the marker guarantees one
firing per session ever.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from ..gate import Gate, read_payload
from ..handoffs import pending_dir

#: A session smaller than this has not earned the reminder.
TRANSCRIPT_BYTES_MIN = 800_000
#: A pending handoff younger than this counts as "this session already wrote one".
HANDOFF_FRESH_SECONDS = 8 * 3600

MESSAGE = """SESSION-END GUARD (fires once per session): this is a long session that leaves
modified tracked files or project notes behind, and no handoff note has been queued.
Decisions and reasoning not written down die with this session.

Do this now, briefly:
1. Tell the user what unwritten state exists (uncommitted changes, decisions made in
   discussion, in-flight work).
2. Offer to queue a handoff note to the next session (`kmem handoff send`) and/or
   write a memory file.
3. If the user already declined a handoff this session, say so and finish normally.

Then finish your reply. Do not start new work.
"""


def tracked_changes(cwd: str) -> bool:
    try:
        out = subprocess.run(["git", "-C", cwd, "status", "--porcelain"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in out.splitlines():
        status, path = line[:2], line[3:]
        if status.strip() and status != "??":
            return True
        if status == "??" and "project_notes" in path:
            return True
    return False


def handoff_written_recently(pending: Path, now: float | None = None) -> bool:
    if not pending.is_dir():
        return False
    now = now or time.time()
    try:
        return any(now - p.stat().st_mtime < HANDOFF_FRESH_SECONDS for p in pending.glob("*.md"))
    except OSError:
        return False


def decide(payload: dict, gate: Gate | None = None) -> tuple[int, str]:
    if payload.get("stop_hook_active"):
        return 0, ""
    gate = gate or Gate()
    session = str(payload.get("session_id", "no-session"))
    if gate.marker(f"outbox-{session}").exists():
        return 0, ""
    transcript = Path(str(payload.get("transcript_path", "")))
    try:
        if not transcript.is_file() or transcript.stat().st_size < TRANSCRIPT_BYTES_MIN:
            return 0, ""
    except OSError:
        return 0, ""
    cwd = str(payload.get("cwd", "")) or "."
    if not tracked_changes(cwd):
        return 0, ""
    if handoff_written_recently(pending_dir(gate.config)):
        return 0, ""
    if not gate.mark_once(f"outbox-{session}"):
        return 0, ""
    return 2, MESSAGE


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    if not payload:
        return 0
    code, msg = decide(payload)
    if msg:
        print(msg, file=sys.stderr)
    return code

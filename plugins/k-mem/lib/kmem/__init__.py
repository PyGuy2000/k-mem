"""K-mem: a memory and governance library for Claude Code sessions.

Standard library only, so any ``python3`` on PATH can import it from a hook.

Modules:

- ``config``    the per-user config file (repos, aliases, state dirs, flags)
- ``layout``    where a governed repo keeps its records
- ``govmap``    ``.claude/adr_map.json``: path patterns and the ADRs they need
- ``context``   the deterministic context resolver and its disposable index
- ``notes``     the decisions index generator and the notes archiver
- ``audit``     the docs checks that fail when the record and the tree disagree
- ``inventory`` what exists and where, across every configured repo
- ``report``    the gate evidence report
- ``cli``       the ``kmem`` command
"""

__version__ = "0.1.1"

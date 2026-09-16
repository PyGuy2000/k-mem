# Changelog

## 0.1.1 (2026-09-16)

Fixes from the first installs on a clean machine.

- The plugin manifest no longer declares `hooks/hooks.json`. Claude Code loads that file on its own, and declaring it again refused the whole plugin.
- DevFlow is listed as an https url source. A github source clones over SSH, which fails on any machine with no GitHub SSH key.
- The name check reads the whole final reply. A long reply lands as several transcript entries and only the last was checked, so a reply that had named the decisions was blocked.
- The CLI finds the data directory a session created, `~/.claude/plugins/data/k-mem-k-mem/`. It defaulted to `.../data/k-mem/`, so `kmem report` read an empty directory while the hooks wrote to the real one.
- The fresh-machine script reads plugin status per plugin and byte-safely, and the Docker image no longer rewrites git URLs, so it fails the way a stranger's machine fails.

## 0.1.0 (2026-09-16)

First release.

- Library (`kmem`): the context resolver with a disposable SQLite index, the decisions index generator, the notes archiver, four docs checks with self-expiring tolerances, the knowledge inventory, the gate evidence report. One config file under the plugin's data directory.
- Hooks: read-before-write gate (direct tools, MCP filesystem tools, Bash), decisions write guard, unevidenced-change sweep, decision name check, session-end guard, docs check, session start (first-run config, stale-checkout warning, handoff inbox, context packet, inventory).
- `kmem` command: init, doctor, resolve, index, status, edges, audit, report, inventory, notes, docs, handoff, intent-guard, install-git-hooks, hook.
- Skills: project-memory, handoff, update-project-docs, adr, quick. Commands: idea, park, portfolio, on-track.
- Templates for `kmem init`: the seven notes files, the map, the `CLAUDE.md` block, the decision template.
- `example/`: a governed repo to try on the first session.
- Marketplace with two plugins: `k-mem` and `devflow`.

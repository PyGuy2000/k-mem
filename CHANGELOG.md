# Changelog

## 0.1.0 (2026-09-16)

First release.

- Library (`kmem`): the context resolver with a disposable SQLite index, the decisions index generator, the notes archiver, four docs checks with self-expiring tolerances, the knowledge inventory, the gate evidence report. One config file under the plugin's data directory.
- Hooks: read-before-write gate (direct tools, MCP filesystem tools, Bash), decisions write guard, unevidenced-change sweep, decision name check, session-end guard, docs check, session start (first-run config, stale-checkout warning, handoff inbox, context packet, inventory).
- `kmem` command: init, doctor, resolve, index, status, edges, audit, report, inventory, notes, docs, handoff, intent-guard, install-git-hooks, hook.
- Skills: project-memory, handoff, update-project-docs, adr, quick. Commands: idea, park, portfolio, on-track.
- Templates for `kmem init`: the seven notes files, the map, the `CLAUDE.md` block, the decision template.
- `example/`: a governed repo to try on the first session.
- Marketplace with two plugins: `k-mem` and `devflow`.

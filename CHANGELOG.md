# Changelog

## 0.1.4 (2026-09-17)

Two defects a first consumer found, both of which made k-mem wrong about someone else's repo.

**`kmem notes index` no longer overwrites an index another generator owns.** A repo that already generated `decisions.md` with its own script keeps a start marker with its own attribution; k-mem looked for its exact marker, missed, and rewrote both the format and the preamble above it. Each tool's freshness check then called the other's correct output stale, which reads as a staleness bug rather than a collision, and the ADR write guard's checklist sent authors straight into it. `kmem notes index` now refuses and names the generator it found, `--force` takes the file over deliberately, `kmem audit` skips its freshness check instead of failing, and the write guard says "whichever generator owns it" rather than naming one.

**The skills name DevFlow's tools, not a server address.** `mcp__devflow__X` is the name a settings.json-wired server gets; a plugin-installed DevFlow is namespaced `plugin:devflow:devflow`, so 22 hard-coded mentions across 7 skills and commands were wrong for half of all installs. They now name the tool and let the model bind it. A test fails on any reintroduced prefix.

## 0.1.3 (2026-09-17)

DevFlow is no longer a declared plugin dependency. The install is three commands instead of two, and the README says so. The reason is a machine that already runs DevFlow from its own checkout: a declared dependency cannot be disabled or uninstalled while k-mem is enabled, so that machine ended up with two DevFlow servers on one state file, one of them missing the private overlay the other carries. The fresh-machine test installs DevFlow explicitly and still checks it loaded.

## 0.1.2 (2026-09-17)

The library is now pip-installable. `pip install "k-mem @ git+https://github.com/PyGuy2000/k-mem.git@v0.1.2"` installs the `kmem` package and the `kmem` console script from the same tree the plugin runs. Nothing about the plugin changes; the launchers under `plugins/k-mem/hooks/` still put `lib/` on the path themselves. This exists for a repo whose own tests or CI import the resolver, where a Claude Code plugin install is not available on the runner.

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

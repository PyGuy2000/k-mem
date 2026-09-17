# Design

This records what K-mem does and why each piece is shaped the way it is. The README says how to use it.

## The three limits

The design started from a failure review. Three limits were recorded, in the assistant's own words, and treated as the spec.

1. No memory across sessions. Every session starts empty.
2. Rules that depend on the model's attention degrade. A decision injected at session start was missed 400 turns later in the same session.
3. The absence of a never-learned fact is undetectable. A decision record asserted that no store for a kind of rule existed, while a config file had held exactly that kind of rule for months and an archived note had already decided the question.

Each fails at a different point: session start, mid-session, and search time. So each gets a different mechanism, and no single mechanism is expected to cover another's failure.

A fourth finding came later and changed how limit 2 is handled. A rule or a known gap that lives only in prose is a note to self. A decision was cited across a repo with no body for 4 months. A test tier was reported as built and never ran for 6 weeks. Both passed a green build, because nothing outside the model checked the prose against the tree. The rule: the record is not the check.

## Limit 1: files, delivered at the two moments that matter

Durable state lives in files. Hooks deliver them at session start and ask for them at session end.

At session start the plugin prints, in this order: a stale-checkout warning when the default branch carries the notes contract and this checkout does not; every pending handoff note addressed to the project; the context packet for governed files already changed on the branch; and the knowledge inventory. The project's `CLAUDE.md` block asks for `STATE.md` and `plans.md` to be read before the first substantive answer.

At session end a Stop hook fires once when three conditions hold: the transcript is over 800 KB, tracked files or project notes are modified, and no handoff was queued in the last 8 hours. It blocks the stop one time and asks the model to offer a handoff or a memory write. All three conditions must hold, so it fires only when a reminder is actionable.

The notes are tiered because one long file is read once and never again. `STATE.md` has a token budget and the audit fails when it is exceeded. Superseded facts are deleted from it, not annotated; git holds the history.

## Limit 2: rules move into hooks that fire at the violation

Four firing points, ordered by how late they catch the error.

**Write time.** Two hooks. The decisions write guard denies the first write into a decisions path once with a checklist (number unique, absence claims cite the inventory, prior decision checked including the handoff archive, names defined before use, tickets for outstanding work, index refreshed) and passes the identical retry. The checklist is guaranteed to be the most recent thing in context while the decision is written.

The read gate goes further. `.claude/adr_map.json` maps path patterns to decision numbers. A write under a governed path is refused until the transcript shows those decision files were read. Evidence of a read is any tool use whose input names the decision file, or, for the single-file layout, one tool use that names both `decisions.md` and the decision number. Reading `decisions.md` without the number is not evidence for the number. Only completed earlier turns are visible to a PreToolUse hook, so the read must happen in a turn before the edit. There is no once-per-session bypass.

The gate sees Bash. A command is parsed for write-shaped operations: `sed -i`, `perl -i`, `awk -i inplace`, redirects including heredocs, `tee`, the copy family, the remove family, `git restore|checkout|mv|rm|apply`, and `open(path, "w")` inside inline Python. Targets resolve against the hook's cwd and any `cd` in the command; only a path under a repo that carries a map is considered. A command the parser cannot see through is the known residual. The PostToolUse sweep lists governed files dirty in the repo after every Bash command and logs any that changed in this session with no read line as `unevidenced`. The residual shows up as a number on the report.

**Read time.** The gate family covers writes. The mistakes that cost the most are not writes at all: a session concludes something from an instrument that could not have shown otherwise, says it, and the claim reaches a human before anything checks it. Most of that is unreachable from a hook, because a claim makes no tool call. Two cases are reachable. Running the ambient `python` when the repo pins its own, and piping a 13-line listing through `tail -12` and reporting the missing line as absent, are both Bash commands, visible to a PreToolUse hook, and decidable from the command text.

The command guard takes exactly those two. `.claude/commands.json` declares the pinned commands and the commands whose whole output is the evidence; a bare pinned command and a truncated evidence command are refused with the required form named. Declaring the file is the opt-in, which is why the guard costs nothing in a repo that has not thought about it.

Rule 2 is declaration-driven on purpose. `| head` is correct most of the time. It is wrong when the output is being read as a complete list, and the command text does not say which of those is happening. A heuristic would refuse good commands all day and teach the session to work around the hook. The repo names the commands whose output is evidence, and the rule fires on those.

**Beside the gate: the resolver.** The gate answers one question from one hand-kept map: which decisions govern this path. The resolver answers the wider one: given an intended edit, what authoritative project knowledge applies. It compiles a disposable SQLite index from files the repo already keeps (the map, the decision header blocks, the contract register, the plan index, the fact-document frontmatter, and the DevFlow state when present) and returns a packet: mandatory records, advisory records one labelled relation away, collisions, provenance per record, and a receipt hash over the request and both revisions.

Two rules hold it honest. Mandatory comes only from explicit relationships, never from a score or an embedding or the model's judgement; a test feeds it a search backend that returns a perfect score and asserts nothing enters the mandatory set. And the mandatory set is exactly the map's set, so a second map never appears. In shadow mode the gate logs its own set beside the resolver's with a classification (`MATCH`, `RESOLVER_EXTRA`, `EXISTING_EXTRA`, `CONFLICT`) and nothing the resolver does changes the yes or no. In enforce mode the resolver's set is added to the map's, the refusal carries the packet, and a resolver failure logs `fallback` while the map decides.

**Commit time.** The intent guard is a pre-commit hook. An added line under `docs/project_notes/` that names future work (next step, deferred, todo, pending) and carries no ticket id fails the commit. A status tag on a decision heading, a `**Status**` line, and words quoted in inline code are exempt, since they only explain the vocabulary. The hook is self-contained so it keeps working when the plugin moves.

**Reply time.** A Stop hook maps every write since the last human message through the map and blocks the reply once if it does not name the governing decisions. The protocol half (did the reply apply what it named) is visibility only.

**Build time.** Four docs checks: every bare decision citation resolves to a file, the decisions index equals what the generator renders, `STATE.md` is under budget, every edge the resolver compiles points at a record it also compiled. Tolerances are self-expiring: an allowlist entry names a ticket and a date, and past the date the check goes red.

Every check ships with a proof of red. A check that cannot fail is not a check.

**The wiring lesson.** A hook is fenced only through the command that wires it. In an earlier setup the read gate never blocked anything for two days: its settings entry ended in `|| true`, which turned the deny exit code into an allow, while the evidence log kept recording "denied". The script's own tests had run the script directly and never the wired string. So the plugin's tests run every hook as a subprocess through its launcher, with the payload shape Claude Code sends, and assert the exit code.

## Limit 3: enumeration

Search confirms suspicion. A generated list in context can contradict a confident "there is no such thing."

The inventory enumerates three classes across every configured repo: knowledge files with each file's own first-line description, every decision id and title, and every handoff subject including the archive. The archive matters: the missed decision that started this work was an archived note, and a recent-25 cut reproduced the exact gap.

Two properties hold. Every description is extracted from the file, never authored in the script, so the list cannot drift from the tree. And the output is bounded, because it competes with the work for context.

Not covered: decision bodies and ticket work logs. The inventory says a decision exists; reading it is a separate step. The resolver narrows the gap for one path at a time.

## Two decision layouts

One file per decision under `docs/project_notes/decisions/` (`ADR-NNN-slug.md`), or every decision as a `## ADR-NNN` heading inside one `decisions.md`. The gate, the resolver, the audit and the inventory read both. The per-file layout wins when it has files.

Header fields are parsed for edges: `Depends on`, `Supersedes`, `Superseded by`, and any decision or ticket reference in a field. Body prose is never parsed for edges, because it mentions every decision in the neighbourhood and would make the graph useless.

## Identity

Every repo restarts numbering at 001, so a bare `ADR-013` names several decisions. Record ids are repo-qualified: `my_app:ADR-013`. A prose alias from the config (`other ADR-013`, `other-013`) resolves to that repo. The repo id comes from, in order: the `repo` key in the map, the configured checkout path, the parent of the git common dir (a worktree's folder is named after its branch), the origin URL, the folder name.

## What is deliberately not here

A search backend. Indexes and code graphs already exist as MCP tools; the resolver has a typed seam for one and ships a null implementation.

A second map. A hand-written relationship config was rejected because the map already is one.

A hook that redirects raw search to the resolver. The gate's evidence of a read is that raw search.

Automatic memory capture. Plugins that record observations per session exist and can run beside this one.

## Why DevFlow is a url source, not a github source

The marketplace entry for DevFlow points at an https url:

```json
{"source": "url", "url": "https://github.com/PyGuy2000/devflow-mcp.git"}
```

A `{"source": "github", "repo": "..."}` entry clones over SSH. On a machine
with no GitHub SSH key, which is every fresh install, that fails with a host
key error or a publickey refusal, and the plugin never installs. `claude
plugin marketplace add` does fall back to https and prints "SSH not
configured, cloning via https", but the plugin-source clone inside `claude
plugin install` does not. An https url takes the same path in both.

Found on the test VM after the Docker run passed, because the image had a
url rewrite that hid it.

## Configuration, not code

Every path and every repo name lives in `config.json` under the plugin's data directory. The package carries no repo, host, client or ticket of its author's. A release check greps the tree for any and fails.

## What the tests cover

The resolver suite: governed paths resolve, ungoverned paths have no mandatory set, body prose does not become an edge, provenance points at real lines, delete-and-rebuild gives the same packet, a stale index is detected, the receipt is deterministic, two repos with the same number get distinct ids, a perfect search score never becomes mandatory, collisions are reported, both layouts work, a worktree resolves to its canonical id.

The gate suite: deny without a read, allow after any kind of read, the decision files themselves are not gated, fail open and log on a missing transcript, the single-file layout denies until the section is read, enforce mode carries the packet and the receipt, a broken resolver in enforce mode still denies from the map, 16 Bash write shapes are denied, 8 read-only or ungoverned commands are never gated, MCP and notebook writes are gated, the sweep logs a bypass once.

The audit suite: each of the four checks has a red fixture and a green one, and allowlist entries stop protecting after their date.

The acceptance: in the example repo, through the real launchers, an unread governed edit is refused, allowed after the read, `sed -i` refused with `via: bash`, and the sweep logs the bypass.

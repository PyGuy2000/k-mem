---
name: handoff
description: Pass work between Claude Code sessions without the user copy-pasting prompts across terminals. Writes a structured note to the shared mailbox; the SessionStart hook delivers it when a session opens in the target project. Use when the user says "hand this off to X", "tell the X session", "write a note for X", "write me a prompt for the next session", or when closing a session with in-flight work.
---

# Handoff: mail between sessions instead of copy-paste relay

The user runs one session per repo. Notes between sessions go through the K-mem mailbox (`kmem handoff list` prints where it is) and are delivered automatically at session start in the target project. Never ask the user to paste a prompt into another terminal, and never write NEXT_SESSION.md files into repos.

## Sending: "hand this off to <project>"

1. Target = the project's name. A checkout answers to its directory name, its git repository name and its configured name; `kmem handoff inbox` prints the primary one for the current repo. If unsure, ask.
2. Write the body to a scratch file, then queue it:

```bash
kmem handoff send --to <target> --subject "one line" --body-file /path/to/body.md
```

The body follows this shape (the command fills it in when the body is empty):

```markdown
## State
What is done, what is in flight (PR numbers, branch names, ticket ids).

## Ask
The specific action requested from the receiving session, or "FYI only".

## References
File paths, tickets, PR URLs. Link, do not paste code.

## Warnings
Anything the receiving session must not do (for example "do not git reset; uncommitted work present").
```

3. Keep it under ~60 lines. State facts, not narration. Convert relative dates to absolute.
4. For every ticket referenced in the note, leave a breadcrumb on the ticket itself (`mcp__devflow__log_work` when DevFlow is installed). The receiving session then gets the full history from the ticket and the note can shrink to the Ask and the Warnings.
5. Confirm to the user: "Handoff queued for <target>; it loads automatically when you open a session there."

## Session-close notes ("write me a prompt for the next session")

Same mechanism, addressed to the CURRENT project (`--to` = this repo's name). The next session here receives it at startup. Before writing it, check `git status`. If there is uncommitted work, say so under Warnings and offer to commit first; uncommitted work left across a session boundary has been lost before.

## Receiving

The SessionStart hook injects pending notes automatically. When that happens:

1. Fold the notes into your working context and tell the user what arrived and from where.
2. After acting on a note (or confirming it is stale), move it out of the inbox: `kmem handoff archive <file>`.
3. If a note's Ask conflicts with what the user asks for directly, the user wins; say so.

If the user asks "any handoffs?" mid-session, run `kmem handoff inbox`.

## Replying

A reply is a new handoff addressed back to the `from:` project. Reference the original subject so the thread is followable in the archive.

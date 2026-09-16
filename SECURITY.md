# Security

## Reporting a vulnerability

Report privately through GitHub's [security advisory form](https://github.com/PyGuy2000/k-mem/security/advisories/new). Please do not open a public issue for something exploitable.

Expect an acknowledgement within a week. This is a one-person project, so a fix may take longer than that; the advisory thread will say where things stand.

## What this software does on your machine

Worth knowing before you install it, because plugins run with your permissions.

**It reads.** The resolver and the inventory read the repos listed in your config file, and only those. The gate reads the session transcript to check whether a decision file was opened.

**It writes** to the plugin's own data directory, to the project notes when you run `kmem init` or `kmem notes`, and to `.git/hooks/pre-commit` when you run `kmem install-git-hooks`.

**It runs `git`** to find repo names, list changed files and read revisions. It runs no other external program.

**It sends nothing anywhere.** No network calls, no telemetry, no analytics. The only network traffic near this project is `claude plugin install` fetching the repo.

**It does not read your secrets on purpose,** and it has no special handling to avoid them either. The knowledge inventory lists file names and each file's first line. If a file in a configured repo opens with a credential, that line can appear in the inventory and therefore in your session context. Keep secrets out of the first line of tracked files, which is good practice regardless.

## The gate is not a security boundary

The read-before-write gate refuses an edit until the governing decision has been read in the session. It is a workflow check, and it is honest about its limits:

- It proves a read happened, not that it was understood.
- It **fails open**. An unreadable transcript or a broken map allows the write and logs why. A fault in this plugin must never block all editing, so a determined bypass is always available.
- A file named `DISABLED` in the evidence directory turns it off.
- The Bash parser sees common write shapes. A command it cannot parse gets caught by the sweep and logged as `unevidenced`. That counts the residual; it does not prevent it.

Do not use it to stop a hostile actor. Use it to stop a forgetful one.

## Supported versions

The latest release gets fixes. Older tags do not.

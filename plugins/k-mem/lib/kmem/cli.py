"""The ``kmem`` command.

    kmem init [--repo NAME=PATH]... [--alias ALIAS=NAME]... [--name NAME] [--no-scaffold] [--force]
    kmem doctor [--json]
    kmem resolve --target PATH [--operation edit] [--json]
    kmem index | status | edges
    kmem audit [--root DIR] [--json]
    kmem report [--since YYYY-MM-DD] [--json]
    kmem inventory [--out FILE] [--stats]
    kmem notes index | archive [--cutoff YYYY-MM-DD] | adr "Title"
    kmem docs check [--force] | stamp FILE | stamp-all | init FILE
    kmem handoff inbox | list | send --to NAME --subject S [--from NAME] [--body-file F] | archive NAME
    kmem intent-guard [--self-test] [--diff-from-stdin]
    kmem install-git-hooks [--force]
    kmem hook <name>            run one hook with the payload on stdin

Exit codes: 0 ok; 1 a check failed; 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, docsync, handoffs, inventory, report
from .audit import run_audit
from .config import Config, config_path, data_dir, load_config
from .govmap import find_repo_root, load_map
from .layout import MAP_REL, NOTES_DIR
from .notes import ForeignIndex, archive_old_notes, write_index
from .notes.new_adr import create as create_adr
from .scaffold import TEMPLATES_DIR, install_git_hooks, scaffold

USAGE_ERROR = 2


def _root_or_die(arg: str | None) -> Path:
    root = Path(arg).resolve() if arg else find_repo_root()
    if root is None:
        raise SystemExit(f"no {MAP_REL.as_posix()} above the working directory; pass --root or run kmem init here")
    return root


def _git_toplevel(start: Path) -> Path | None:
    try:
        r = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _service(args: argparse.Namespace):
    from .context import ContextResolutionService

    root = _root_or_die(getattr(args, "root", None))
    return ContextResolutionService(
        root=root,
        repo=getattr(args, "repo", None),
        db_path=Path(args.db) if getattr(args, "db", None) else None,
    )


def _add_repo_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", help=f"repo root (default: walk up from cwd to {MAP_REL.as_posix()})")
    p.add_argument("--repo", help="repo name for qualified ids (default: detected)")
    p.add_argument("--db", help="index path (default: <index_dir>/<repo>.sqlite)")


# --- init / doctor ---------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    target = config_path()
    if target.is_file() and args.force:
        cfg = Config.defaults(data_dir())
    else:
        cfg = load_config()
    created = not target.is_file()
    for item in args.repo:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            raise SystemExit(f"--repo expects NAME=PATH, got {item!r}")
        cfg.repos[name] = Path(path).expanduser().resolve()
    for item in args.alias:
        alias, sep, name = item.partition("=")
        if not sep or not alias or not name:
            raise SystemExit(f"--alias expects ALIAS=NAME, got {item!r}")
        cfg.aliases[alias] = name

    root = Path(args.root).resolve() if args.root else (find_repo_root() or _git_toplevel(Path.cwd()))
    lines: list[str] = []
    if root is not None:
        from .context.compiler import detect_repo_name

        if not args.no_scaffold:
            name = args.name or detect_repo_name(root, cfg)
            lines += scaffold(root, name)
        name = args.name or cfg.repo_for_root(root) or detect_repo_name(root, cfg)
        if name not in cfg.repos:
            cfg.repos[name] = root
    for d in (cfg.evidence_dir, cfg.index_dir, cfg.handoffs_dir):
        d.mkdir(parents=True, exist_ok=True)
    cfg.save(target)
    print(f"{'wrote' if created or args.force else 'updated'} {target}")
    print(f"repos: {', '.join(cfg.repos) or '(none)'}")
    for line in lines:
        print(line)
    if root is None:
        print("not in a git repo: nothing scaffolded (run kmem init inside a repo, or pass --root)")
    return 0


def _doctor_rows(root: Path | None) -> list[tuple[str, str, bool]]:
    rows: list[tuple[str, str, bool]] = []
    base = data_dir()
    rows.append(("data dir", f"{base} ({'exists' if base.is_dir() else 'missing; kmem init creates it'})", True))
    cp = config_path()
    if cp.is_file():
        try:
            cfg = load_config()
            rows.append(("config", f"{cp} (ok)", True))
        except ValueError as exc:
            cfg = Config.defaults(base)
            rows.append(("config", f"{cp} (INVALID: {exc})", False))
    else:
        cfg = load_config()
        rows.append(("config", f"{cp} (missing; defaults in use; run kmem init)", True))
    py = f"{platform.python_version()} ({sys.executable})"
    rows.append(("python", py, sys.version_info >= (3, 9)))
    rows.append(("python3 on PATH", shutil.which("python3") or "NOT FOUND (the hooks run `python3`)", bool(shutil.which("python3"))))
    git = shutil.which("git")
    if git:
        try:
            v = subprocess.run([git, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            v = "present"
        rows.append(("git", v, True))
    else:
        rows.append(("git", "not on PATH (repo ids and staleness need it)", False))
    missing = [f"{n} -> {p}" for n, p in cfg.repos.items() if not p.is_dir()]
    rows.append(("repos", f"{len(cfg.repos)} configured, {len(missing)} missing" + (": " + "; ".join(missing) if missing else ""), not missing))
    for label, d in (("index dir", cfg.index_dir), ("evidence dir", cfg.evidence_dir), ("handoffs dir", cfg.handoffs_dir)):
        try:
            d.mkdir(parents=True, exist_ok=True)
            writable = os.access(d, os.W_OK)
        except OSError:
            writable = False
        rows.append((label, f"{d} ({'writable' if writable else 'NOT writable'})", writable))
    rows.append(("devflow state", f"{cfg.devflow_state} ({'present' if cfg.devflow_state.is_file() else 'absent; tickets skipped'})", True))
    rows.append(("gate", ("enforce" if cfg.enforce else "shadow") + ("; DISABLED marker present" if (cfg.evidence_dir / "DISABLED").exists() else ""), True))
    rows.append(("templates", f"{TEMPLATES_DIR} ({'ok' if (TEMPLATES_DIR / 'CLAUDE.md.block').is_file() else 'MISSING'})", (TEMPLATES_DIR / "CLAUDE.md.block").is_file()))
    if root is None:
        rows.append(("this repo", f"not governed (no {MAP_REL.as_posix()} above cwd)", True))
    else:
        try:
            n = len(load_map(root))
            rows.append(("this repo", f"{root} governed ({n} rules)", True))
        except (OSError, ValueError) as exc:
            rows.append(("this repo", f"{root}: map unreadable ({exc})", False))
    return rows


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else find_repo_root()
    rows = _doctor_rows(root)
    if args.json:
        print(json.dumps([{"item": k, "value": v, "ok": ok} for k, v, ok in rows], indent=2))
    else:
        for k, v, ok in rows:
            print(f"{'ok  ' if ok else 'FAIL'} {k:<15} {v}")
    return 0 if all(ok for _, _, ok in rows) else 1


# --- resolver ------------------------------------------------------------------------


def _print_packet(packet, as_json: bool) -> None:
    if as_json:
        print(json.dumps(packet.to_dict(), indent=2))
        return
    print(f"{packet.request.operation} {packet.request.target}  [{packet.receipt_id}]")
    print(f"  source {packet.source_revision}  index {packet.index_revision}")
    print("  mandatory:")
    for r in packet.mandatory:
        print(f"    {r.record_id:<34} {r.status or '':<10} {r.path}")
    if packet.collisions:
        print("  collisions:")
        for c in packet.collisions:
            print(f"    {c.relation:<22} {c.record.record_id:<34} {c.record.title[:60]}")
    print("  advisory:")
    for a in packet.advisory:
        print(f"    {a.relation:<22} {a.record.record_id:<34} {a.record.title[:60]}")


def cmd_resolve(args: argparse.Namespace) -> int:
    svc = _service(args)
    try:
        _print_packet(svc.resolve_context(args.operation, args.target), args.json)
    finally:
        svc.close()
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    svc = _service(args)
    try:
        rev = svc.build_index()
        print(json.dumps({"ok": True, **svc.status(), "index_revision": rev}, indent=2))
    finally:
        svc.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    svc = _service(args)
    try:
        print(json.dumps(svc.status(), indent=2))
    finally:
        svc.close()
    return 0


def cmd_edges(args: argparse.Namespace) -> int:
    svc = _service(args)
    try:
        svc.ensure_index()
        edges = svc.store.unresolved_edges()
        if args.json:
            print(json.dumps([e.__dict__ for e in edges], indent=2))
        else:
            for e in edges:
                print(f"{e.source_id} -{e.relationship}-> {e.target_id}   ({e.provenance.get('source')}:{e.provenance.get('line')})")
            print(f"{len(edges)} unresolved", file=sys.stderr)
    finally:
        svc.close()
    return 0


# --- audit / report / inventory ------------------------------------------------------


def cmd_audit(args: argparse.Namespace) -> int:
    root = _root_or_die(args.root)
    results = run_audit(root)
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        for r in results:
            print(f"{r.status.upper():<5} {r.key:<32} {r.detail}")
        counts = {s: sum(1 for r in results if r.status == s) for s in ("pass", "fail", "skip")}
        print(f"{len(results)} checks: {counts['pass']} pass, {counts['fail']} fail, {counts['skip']} skip")
    return 1 if any(r.status == "fail" for r in results) else 0


def cmd_report(args: argparse.Namespace) -> int:
    cfg = load_config()
    rep = report.build(cfg.evidence_dir, args.since)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        sys.stdout.write(report.render(rep, cfg.evidence_dir))
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    cfg = load_config()
    text = inventory.render(cfg)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.stats:
        print(inventory.stats_line(text, cfg.inventory_line_budget), file=sys.stderr)
    return 0


# --- notes / docs / handoff ----------------------------------------------------------


def cmd_notes(args: argparse.Namespace) -> int:
    root = _root_or_die(args.root)
    notes_dir = root / NOTES_DIR
    if args.notes_cmd == "index":
        try:
            n_rows, n_files, size = write_index(notes_dir, force=getattr(args, "force", False))
        except (FileNotFoundError, ForeignIndex) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"decisions.md: index of {n_rows} headings across {n_files} files ({size:,} bytes)")
        return 0
    if args.notes_cmd == "adr":
        path = create_adr(root, args.title, (TEMPLATES_DIR / "ADR.md").read_text(encoding="utf-8"))
        n_rows, n_files, _ = write_index(notes_dir)
        print(f"created {path.relative_to(root).as_posix()}; index now {n_rows} headings across {n_files} files")
        return 0
    cutoff = dt.date.fromisoformat(args.cutoff) if args.cutoff else None
    for line in archive_old_notes(notes_dir, cutoff):
        print(line)
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    try:
        if args.docs_cmd == "check":
            start = Path(args.root).resolve() if args.root else Path.cwd()
            lines = docsync.check(start, load_config(), force=args.force)
            if lines:
                print("\n".join(lines))
            else:
                print("docs check: nothing stale, nothing over budget")
            return 0
        if args.docs_cmd == "stamp":
            print(docsync.stamp(Path(args.file)))
            return 0
        if args.docs_cmd == "stamp-all":
            print(docsync.stamp_all(Path(args.root).resolve() if args.root else Path.cwd()))
            return 0
        print(docsync.init(Path(args.file)))
        return 0
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def cmd_handoff(args: argparse.Namespace) -> int:
    cfg = load_config()
    cwd = Path.cwd()
    if args.handoff_cmd == "inbox":
        text = handoffs.inbox(cwd, cfg)
        sys.stdout.write(text if text else f"no pending handoff for {handoffs.project_names(cwd, cfg)[-1]} in {handoffs.pending_dir(cfg)}\n")
        return 0
    if args.handoff_cmd == "list":
        notes = handoffs.list_pending(cfg)
        for p in notes:
            meta = handoffs.parse_note(p)
            print(f"{p.name}  to={meta.get('to', '?')}  from={meta.get('from', '?')}  {meta.get('subject', '')}")
        print(f"{len(notes)} pending in {handoffs.pending_dir(cfg)}", file=sys.stderr)
        return 0
    if args.handoff_cmd == "archive":
        print(f"archived -> {handoffs.archive(cfg, args.name)}")
        return 0
    body = ""
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        body = sys.stdin.read()
    sender = args.from_ or handoffs.project_names(cwd, cfg)[-1]
    path = handoffs.send(cfg, sender, args.to, args.subject, body)
    print(f"queued {path}")
    print(f"It loads automatically when a session opens in {args.to}.")
    return 0


# --- guards / hooks --------------------------------------------------------------------


def cmd_intent_guard(args: argparse.Namespace) -> int:
    from . import intent_guard

    argv: list[str] = []
    if args.self_test:
        argv.append("--self-test")
    if args.diff_from_stdin:
        argv.append("--diff-from-stdin")
    if args.root:
        argv += ["--root", args.root]
    return intent_guard.main(argv)


def cmd_install_git_hooks(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else (_git_toplevel(Path.cwd()) or Path.cwd())
    try:
        print(install_git_hooks(root, force=args.force))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    from .hooks import HOOKS

    fn = HOOKS.get(args.name)
    if fn is None:
        raise SystemExit(f"unknown hook {args.name!r}; one of: {', '.join(sorted(HOOKS))}")
    return int(fn())


# --- parser ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kmem", description="K-mem: memory and governance for Claude Code sessions.")
    p.add_argument("--version", action="version", version=f"kmem {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="write the config file; scaffold the notes, map and CLAUDE.md block in this repo")
    s.add_argument("--repo", action="append", default=[], metavar="NAME=PATH", help="register a checkout (repeatable)")
    s.add_argument("--alias", action="append", default=[], metavar="ALIAS=NAME", help="prose qualifier for a repo (repeatable)")
    s.add_argument("--root", help="the repo to scaffold and register (default: the one above cwd)")
    s.add_argument("--name", help="the repo's name for qualified ids (default: detected)")
    s.add_argument("--no-scaffold", action="store_true", help="config only; write no files into the repo")
    s.add_argument("--force", action="store_true", help="start the config from defaults even if a file exists")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", help="check the install: data dir, config, python, git, repos, state dirs")
    s.add_argument("--root")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("resolve", help="the context packet for an operation on a path")
    _add_repo_opts(s)
    s.add_argument("--operation", default="edit")
    s.add_argument("--target", required=True, help="repo-relative path")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_resolve)

    s = sub.add_parser("index", help="rebuild the disposable index from the authored sources")
    _add_repo_opts(s)
    s.set_defaults(fn=cmd_index)

    s = sub.add_parser("status", help="index revision, source revision, staleness")
    _add_repo_opts(s)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("edges", help="relationship targets that resolve to no record")
    _add_repo_opts(s)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_edges)

    s = sub.add_parser("audit", help="the docs checks; exit 1 when any fails")
    s.add_argument("--root")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("report", help="the gate evidence report")
    s.add_argument("--since", help="YYYY-MM-DD; keep lines on or after this date")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("inventory", help="what exists and where, across every configured repo")
    s.add_argument("--out", type=Path, help="write here instead of stdout")
    s.add_argument("--stats", action="store_true", help="report size against the line budget on stderr")
    s.set_defaults(fn=cmd_inventory)

    s = sub.add_parser("notes", help="project-notes tooling")
    ns = s.add_subparsers(dest="notes_cmd", required=True)
    n = ns.add_parser("index", help="regenerate docs/project_notes/decisions.md from decisions/")
    n.add_argument("--force", action="store_true",
                   help="overwrite decisions.md even when another generator's marker owns it")
    n.add_argument("--root")
    n = ns.add_parser("archive", help="move closed bugs/issues sections older than the cutoff into archive/")
    n.add_argument("--root")
    n.add_argument("--cutoff", help="YYYY-MM-DD (default: 90 days ago)")
    n = ns.add_parser("adr", help="create the next ADR file from the template and refresh the index")
    n.add_argument("title")
    n.add_argument("--root")
    s.set_defaults(fn=cmd_notes)

    s = sub.add_parser("docs", help="fact-doc staleness and the notes budget")
    ds = s.add_subparsers(dest="docs_cmd", required=True)
    d = ds.add_parser("check", help="stale fact docs and over-budget notes (advisory)")
    d.add_argument("--root")
    d.add_argument("--force", action="store_true", help="ignore the per-HEAD cache")
    d = ds.add_parser("stamp", help="set a doc's last_synced_sha to HEAD")
    d.add_argument("file")
    d = ds.add_parser("stamp-all", help="stamp every enrolled doc")
    d.add_argument("--root")
    d = ds.add_parser("init", help="add the frontmatter skeleton to a doc")
    d.add_argument("file")
    s.set_defaults(fn=cmd_docs)

    s = sub.add_parser("handoff", help="notes between sessions")
    hs = s.add_subparsers(dest="handoff_cmd", required=True)
    hs.add_parser("inbox", help="pending notes addressed to this project")
    hs.add_parser("list", help="every pending note")
    h = hs.add_parser("send", help="queue a note for another project (body from --body-file or stdin)")
    h.add_argument("--to", required=True, help="target project name")
    h.add_argument("--subject", required=True)
    h.add_argument("--from", dest="from_", help="sender (default: this project)")
    h.add_argument("--body-file")
    h = hs.add_parser("archive", help="move a pending note to archive/ after acting on it")
    h.add_argument("name")
    s.set_defaults(fn=cmd_handoff)

    s = sub.add_parser("intent-guard", help="refuse unfinished intent in the notes with no ticket id (pre-commit)")
    s.add_argument("--self-test", action="store_true")
    s.add_argument("--diff-from-stdin", action="store_true")
    s.add_argument("--root")
    s.set_defaults(fn=cmd_intent_guard)

    s = sub.add_parser("install-git-hooks", help="install the pre-commit intent guard into this repo")
    s.add_argument("--root")
    s.add_argument("--force", action="store_true", help="replace an existing pre-commit hook")
    s.set_defaults(fn=cmd_install_git_hooks)

    s = sub.add_parser("hook", help="run one hook with the Claude Code payload on stdin")
    s.add_argument("name", help="read-gate | write-guard | sweep | name-check | session-start | outbox-guard | docs-check")
    s.set_defaults(fn=cmd_hook)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(f"kmem: {exc.code}", file=sys.stderr)
            return USAGE_ERROR
        raise
    except FileNotFoundError as exc:
        print(f"kmem: {exc}", file=sys.stderr)
        return USAGE_ERROR
    except ValueError as exc:
        print(f"kmem: {exc}", file=sys.stderr)
        return USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())

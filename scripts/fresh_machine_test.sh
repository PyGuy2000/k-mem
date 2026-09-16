#!/usr/bin/env bash
# The fresh-machine test. Runs inside docker/Dockerfile, or on any machine
# with python3, git and the claude CLI.
#
#   fresh_machine_test.sh            install k-mem@k-mem from GitHub
#   fresh_machine_test.sh /src       install from a local checkout (mounted)
#
# Steps: add the marketplace, install the plugin (which pulls devflow), find
# the installed plugin root, then run the gate acceptance through the real
# launchers, the resolver and the audit on example/, and the test suite.
set -u
SRC="${1:-}"
pass=0; fail=0
ok()   { echo "PASS $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

if [ -n "$SRC" ]; then
  claude plugin marketplace add "$SRC" && ok "marketplace add (local)" || bad "marketplace add (local)"
else
  claude plugin marketplace add PyGuy2000/k-mem && ok "marketplace add (github)" || bad "marketplace add (github)"
fi
claude plugin install k-mem@k-mem && ok "plugin install k-mem@k-mem" || bad "plugin install k-mem@k-mem"
claude plugin list 2>/dev/null | tee /tmp/plugins.txt

# Each plugin's own status line. Two traps this has already fallen into:
#   - grepping the whole listing for a name matches that name inside an error
#     message saying it is MISSING, so a failed install reads as a pass;
#   - matching the list glyph with "." fails under mawk, which counts bytes,
#     while gawk on a workstation matches it fine.
# So: a header line names a plugin and carries no colon, while Version, Scope,
# Status and Error all do. No glyph is ever matched.
status_of() {
  awk -v want="$1" '
    !/:/ && /@/ { line = $0; sub(/^[^A-Za-z0-9]*/, "", line); inblock = (index(line, want "@") == 1) }
    inblock && /Status:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }
  ' /tmp/plugins.txt
}
case "$(status_of k-mem)" in
  *enabled*) ok "k-mem loaded (status enabled)" ;;
  *) bad "k-mem loaded: $(status_of k-mem)"; grep -A2 "Error:" /tmp/plugins.txt | head -6 ;;
esac
case "$(status_of devflow)" in
  *enabled*) ok "devflow installed as a dependency and loaded" ;;
  "") bad "devflow installed as a dependency (not listed at all)" ;;
  *) bad "devflow loaded: $(status_of devflow)" ;;
esac

ROOT="$(find "$HOME/.claude/plugins" -type f -path '*k-mem*' -name 'kmem' 2>/dev/null | head -1 | xargs -r dirname | xargs -r dirname)"
if [ -z "$ROOT" ] && [ -n "$SRC" ]; then ROOT="$SRC/plugins/k-mem"; echo "(using the checkout's plugin dir)"; fi
if [ -z "$ROOT" ]; then bad "plugin root found"; echo "$pass passed, $fail failed"; exit 1; fi
ok "plugin root found: $ROOT"
KMEM="$ROOT/bin/kmem"
EX="${SRC:-$(dirname "$(dirname "$ROOT")")}/example"

"$KMEM" doctor && ok "kmem doctor" || bad "kmem doctor"
rm -rf /tmp/example && cp -r "$EX" /tmp/example && cd /tmp/example || exit 1
git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -q -m init
"$KMEM" resolve --target src/billing/invoice.py | grep -q "example:ADR-001" && ok "kmem resolve" || bad "kmem resolve"
"$KMEM" audit && ok "kmem audit" || bad "kmem audit"

# The gate through the wired launcher, with the payload shape Claude Code sends.
T=/tmp/session.jsonl
echo '{"type":"user","message":{"role":"user","content":"go"}}' > "$T"
payload() { printf '{"session_id":"fresh","transcript_path":"%s","tool_name":"Edit","tool_input":{"file_path":"/tmp/example/src/billing/invoice.py"}}' "$T"; }
payload | python3 "$ROOT/hooks/read_gate.py" 2>/tmp/deny.txt; rc=$?
if [ "$rc" -eq 2 ] && grep -q "ADR-001-invoice-rounding.md" /tmp/deny.txt; then ok "unread governed edit refused (exit 2)"; else bad "unread governed edit refused (exit $rc)"; fi
echo '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Read","input":{"file_path":"/tmp/example/docs/project_notes/decisions/ADR-001-invoice-rounding.md"}}]}}' >> "$T"
echo '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Read","input":{"file_path":"/tmp/example/docs/project_notes/decisions/ADR-002-tax-table-source.md"}}]}}' >> "$T"
payload | python3 "$ROOT/hooks/read_gate.py" 2>/dev/null; rc=$?
if [ "$rc" -eq 0 ]; then ok "edit allowed after the read (exit 0)"; else bad "edit allowed after the read (exit $rc)"; fi
echo '{"type":"user","message":{"role":"user","content":"go"}}' > "$T"
printf '{"session_id":"fresh2","transcript_path":"%s","tool_name":"Bash","cwd":"/tmp/example","tool_input":{"command":"sed -i s/CENT/PENNY/ src/billing/invoice.py"}}' "$T" | python3 "$ROOT/hooks/read_gate.py" 2>/dev/null; rc=$?
if [ "$rc" -eq 2 ]; then ok "sed -i on a governed file refused via bash"; else bad "sed -i on a governed file refused (exit $rc)"; fi
"$KMEM" report | grep -q "shadow lines" && ok "kmem report" || bad "kmem report"

if [ -n "$SRC" ] && [ -d "$SRC/tests" ]; then
  (cd "$SRC" && python3 -m pytest -q -p no:cacheprovider) && ok "test suite" || bad "test suite"
fi
echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]

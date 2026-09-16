"""Docs checks that fail when the record and the tree disagree.

Each check takes ``root`` so a test can point it at a fixture tree, and each
has a proof-of-red test: a fixture where the violation is present and the
check must FAIL. A check that cannot go red is not a check.
"""

from .checks import (
    DOCS_CHECKS,
    check_adr_index_fresh,
    check_adr_refs_resolve,
    check_context_index_edges_resolve,
    check_state_budget,
    run_audit,
)
from .result import FAIL, PASS, SKIP, CheckResult

__all__ = [
    "DOCS_CHECKS",
    "CheckResult",
    "FAIL",
    "PASS",
    "SKIP",
    "check_adr_index_fresh",
    "check_adr_refs_resolve",
    "check_context_index_edges_resolve",
    "check_state_budget",
    "run_audit",
]

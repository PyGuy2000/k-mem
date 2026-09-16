"""One checked invariant. Stdlib only."""

from __future__ import annotations

from dataclasses import asdict, dataclass

PASS = "pass"
FAIL = "fail"
SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    key: str
    title: str
    status: str  # pass | fail | skip
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def ok(key: str, title: str, detail: str = "") -> CheckResult:
    return CheckResult(key, title, PASS, detail)


def bad(key: str, title: str, detail: str) -> CheckResult:
    return CheckResult(key, title, FAIL, detail)


def skip(key: str, title: str, detail: str) -> CheckResult:
    return CheckResult(key, title, SKIP, detail)

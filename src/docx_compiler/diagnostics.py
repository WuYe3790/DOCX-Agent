from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DiagnosticLevel = Literal["info", "warning", "error"]
SupportStatus = Literal["native", "degraded", "rejected"]


@dataclass
class Diagnostic:
    level: DiagnosticLevel
    code: str
    message: str
    block_id: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    support: SupportStatus | None = None

    def to_dict(self) -> dict:
        data = {
            "level": self.level,
            "code": self.code,
            "message": self.message,
        }
        if self.block_id:
            data["block_id"] = self.block_id
        if self.line_start is not None:
            data["line_start"] = self.line_start
        if self.line_end is not None:
            data["line_end"] = self.line_end
        if self.support:
            data["support"] = self.support
        return data


def diagnostics_to_dicts(diagnostics: list[Diagnostic]) -> list[dict]:
    return [diagnostic.to_dict() for diagnostic in diagnostics]


def has_errors(diagnostics: list[Diagnostic]) -> bool:
    return any(diagnostic.level == "error" for diagnostic in diagnostics)


def support_summary(blocks: list[dict]) -> dict:
    summary = {"native": 0, "degraded": 0, "rejected": 0}
    for block in blocks:
        support = block.get("support") or ("native" if block.get("supported", True) else "rejected")
        if support not in summary:
            support = "rejected"
        summary[support] += 1
    return summary

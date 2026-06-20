"""Generic design-rule model for Visio Bridge automation.

The design layer is intentionally read/plan oriented: it audits a Visio file
and returns structured suggestions that lower-level SKILL executors can apply.
It does not write XML directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable


class RuleSeverity(str, Enum):
    """Severity levels used by design-rule reports."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    UNSUPPORTED = "unsupported"


@dataclass
class FixSuggestion:
    """A suggested fix that can be translated to a SKILL command group."""

    executor: str
    commands: list[dict[str, Any]]
    description: str = ""
    target: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "executor": self.executor,
            "commands": self.commands,
        }
        if self.description:
            data["description"] = self.description
        if self.target:
            data["target"] = self.target
        return data


@dataclass
class DesignViolation:
    """One rule result for one target."""

    rule_id: str
    target: str
    message: str
    severity: RuleSeverity = RuleSeverity.WARNING
    category: str = ""
    fixes: list[FixSuggestion] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "target": self.target,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.category:
            data["category"] = self.category
        if self.details:
            data["details"] = self.details
        if self.fixes:
            data["fixes"] = [fix.to_dict() for fix in self.fixes]
        return data


RuleCheck = Callable[[Any], Iterable[DesignViolation]]


@dataclass
class DesignRule:
    """A reusable rule bound to a profile."""

    rule_id: str
    title: str
    category: str
    check: RuleCheck
    severity: RuleSeverity = RuleSeverity.WARNING
    description: str = ""
    requirement: str = "recommended"
    required_capabilities: set[str] = field(default_factory=set)

    def run(self, context: Any) -> list[DesignViolation]:
        missing = self.required_capabilities - context.available_capabilities
        if missing:
            return [
                DesignViolation(
                    rule_id=self.rule_id,
                    target="document",
                    severity=RuleSeverity.UNSUPPORTED,
                    category=self.category,
                    message=(
                        f"Rule requires unavailable capabilities: "
                        f"{', '.join(sorted(missing))}"
                    ),
                    details={"missing_capabilities": sorted(missing)},
                )
            ]

        results: list[DesignViolation] = []
        for violation in self.check(context):
            if not violation.category:
                violation.category = self.category
            results.append(violation)
        return results


@dataclass
class DesignProfile:
    """A complete design profile such as circuit diagrams or chart templates."""

    profile_id: str
    name: str
    rules: list[DesignRule]
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignReport:
    """The structured output of a design audit."""

    profile_id: str
    profile_name: str
    file_path: str
    violations: list[DesignViolation] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, violation: DesignViolation) -> None:
        self.violations.append(violation)
        if violation.severity == RuleSeverity.UNSUPPORTED:
            self.unsupported.append(violation.rule_id)

    def extend(self, violations: Iterable[DesignViolation]) -> None:
        for violation in violations:
            self.add(violation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "file_path": self.file_path,
            "summary": self.summary(),
            "metadata": self.metadata,
            "violations": [v.to_dict() for v in self.violations],
        }

    def summary(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in RuleSeverity}
        for violation in self.violations:
            counts[violation.severity.value] += 1
        counts["total"] = len(self.violations)
        return counts

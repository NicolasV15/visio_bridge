"""Design audit engine and command planning helpers."""

from __future__ import annotations

from typing import Any, Iterable

from ..core.bridge import VisioBridge
from .context import DesignCapabilityRegistry, DesignContext
from .model import DesignProfile, DesignReport, DesignViolation, RuleSeverity


def audit_design(
    bridge: VisioBridge,
    profile: DesignProfile,
    targets: Iterable[str] | None = None,
    registry: DesignCapabilityRegistry | None = None,
) -> DesignReport:
    """Audit *bridge* with *profile* and return a structured report.

    The audit is read-only. Any suggested fixes are returned as lower-level
    command payloads and are not applied here.
    """

    context = DesignContext.from_bridge(bridge, registry=registry)
    target_filter = set(targets or [])
    report = DesignReport(
        profile_id=profile.profile_id,
        profile_name=profile.name,
        file_path=bridge.file_path,
        metadata={
            "available_capabilities": sorted(context.available_capabilities),
            "reader_errors": context.reader_errors,
            "profile": profile.metadata,
        },
    )

    for rule in profile.rules:
        try:
            violations = rule.run(context)
        except Exception as exc:
            violations = [
                DesignViolation(
                    rule_id=rule.rule_id,
                    target="document",
                    severity=RuleSeverity.ERROR,
                    category=rule.category,
                    message=f"Rule failed during audit: {exc}",
                )
            ]

        if target_filter:
            violations = [
                violation
                for violation in violations
                if any(violation.target == target or violation.target.startswith(target + "/") for target in target_filter)
            ]
        report.extend(violations)

    return report


def plan_design_commands(
    report: DesignReport | dict[str, Any],
    include_severity: set[str] | list[str] | tuple[str, ...] | None = None,
    registry: DesignCapabilityRegistry | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Group report fix suggestions by executor.

    Returns:
      {
        "doc_page_settings": [{"source": {...}, "commands": [...]}],
        "symbol_editor": [...]
      }
    """

    allowed = set(include_severity or [RuleSeverity.ERROR.value, RuleSeverity.WARNING.value])
    report_data = report.to_dict() if isinstance(report, DesignReport) else report
    grouped: dict[str, list[dict[str, Any]]] = {}

    for violation in report_data.get("violations", []):
        if violation.get("severity") not in allowed:
            continue
        source = {
            "rule_id": violation.get("rule_id"),
            "target": violation.get("target"),
            "severity": violation.get("severity"),
            "message": violation.get("message"),
        }
        for fix in violation.get("fixes", []):
            executor = fix.get("executor")
            commands = fix.get("commands", [])
            if not executor or not commands:
                continue
            if registry is not None:
                commands = registry.adapt_commands(executor, commands)
            grouped.setdefault(executor, []).append(
                {
                    "source": source,
                    "description": fix.get("description", ""),
                    "target": fix.get("target", violation.get("target", "")),
                    "commands": commands,
                }
            )

    return grouped

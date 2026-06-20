"""Profile description and Markdown rendering utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .model import DesignProfile


DEFAULT_TEMPLATE = """# {{ profile_name }}

<!-- AUTO-GENERATED FROM PROFILE; DO NOT EDIT BY HAND -->

Profile ID: `{{ profile_id }}`

{{ description }}

## Metadata
{{ metadata }}

## Capability Dependencies
{{ capabilities }}

## Rule Overview
{{ rules }}

## Document Settings
{{ document_settings }}

## Power Symbols
{{ power_symbols }}

## Generic Symbol Canvas Rules
{{ symbol_canvas_rules }}

## Wire Style
{{ wire_style }}

## Dynamic Connector
{{ dynamic_connector }}

## Generic Rule Notes
{{ generic_rules }}

## Fixable Rules
{{ fixable_rules }}
"""


def describe_design_profile(profile: DesignProfile) -> dict[str, Any]:
    """Return a structured description of every rule and declared setting."""

    rules = []
    for rule in profile.rules:
        rules.append(
            {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "category": rule.category,
                "requirement": rule.requirement,
                "severity": rule.severity.value,
                "description": rule.description,
                "required_capabilities": sorted(rule.required_capabilities),
            }
        )

    capabilities = sorted(
        {
            capability
            for rule in profile.rules
            for capability in rule.required_capabilities
        }
    )

    return {
        "profile_id": profile.profile_id,
        "profile_name": profile.name,
        "description": profile.description,
        "metadata": profile.metadata,
        "capabilities": capabilities,
        "rules": rules,
        "spec": profile.metadata.get("spec", {}),
    }


def render_design_profile_markdown(
    profile: DesignProfile,
    template: str | None = None,
) -> str:
    """Render a profile description as Markdown using a small placeholder template."""

    description = describe_design_profile(profile)
    spec = description["spec"]
    rendered = template or DEFAULT_TEMPLATE
    replacements = {
        "profile_id": description["profile_id"],
        "profile_name": description["profile_name"],
        "description": description["description"],
        "metadata": _render_key_values(_metadata_without_spec(description["metadata"])),
        "capabilities": _render_list(description["capabilities"]),
        "rules": _render_rules(description["rules"]),
        "document_settings": _render_named_settings(spec.get("document_settings", [])),
        "power_symbols": _render_power_symbols(spec.get("power_symbols", [])),
        "symbol_canvas_rules": _render_named_settings(spec.get("symbol_canvas_rules", [])),
        "wire_style": _render_wire_style(spec.get("wire_style", {})),
        "dynamic_connector": _render_dynamic_connector(spec.get("dynamic_connector", {})),
        "generic_rules": _render_named_settings(spec.get("generic_rules", [])),
        "fixable_rules": _render_named_settings(spec.get("fixable_rules", [])),
    }
    for key, value in replacements.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered.rstrip() + "\n"


def write_design_profile_markdown(
    profile: DesignProfile,
    output_path: str | Path,
    template: str | None = None,
) -> None:
    """Write the rendered Markdown for *profile* to *output_path*."""

    Path(output_path).write_text(
        render_design_profile_markdown(profile, template=template),
        encoding="utf-8",
    )


def load_profile_markdown_template(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _metadata_without_spec(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "spec"}


def _render_key_values(data: dict[str, Any]) -> str:
    if not data:
        return "- None"
    return "\n".join(f"- `{key}`: {value}" for key, value in data.items())


def _render_list(values: list[str]) -> str:
    if not values:
        return "- None"
    return "\n".join(f"- `{value}`" for value in values)


def _render_rules(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return "No rules."
    lines = [
        "| Rule ID | Title | Category | Requirement | Severity | Capabilities |",
        "|---|---|---|---|---|---|",
    ]
    for rule in rules:
        capabilities = ", ".join(f"`{item}`" for item in rule["required_capabilities"]) or "None"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{rule['rule_id']}`",
                    str(rule["title"]),
                    f"`{rule['category']}`",
                    f"`{rule['requirement']}`",
                    f"`{rule['severity']}`",
                    capabilities,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _render_named_settings(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- None"
    blocks = []
    for item in items:
        name = item.get("name") or item.get("rule_id") or "Unnamed"
        blocks.append(f"### {name}")
        for key, value in item.items():
            if key == "name":
                continue
            blocks.append(f"- `{key}`: {_format_value(value)}")
    return "\n".join(blocks)


def _render_power_symbols(symbols: list[dict[str, Any]]) -> str:
    if not symbols:
        return "- None"
    blocks = []
    for symbol in symbols:
        blocks.append(f"### {symbol.get('name', 'Unnamed')}")
        for key, value in symbol.items():
            if key == "name":
                continue
            blocks.append(f"- `{key}`: {_format_value(value)}")
    return "\n".join(blocks)


def _render_wire_style(style: dict[str, Any]) -> str:
    if not style:
        return "- None"
    lines = []
    for key, value in style.items():
        lines.append(f"- `{key}`: {_format_value(value)}")
    return "\n".join(lines)


def _render_dynamic_connector(connector: dict[str, Any]) -> str:
    if not connector:
        return "- None"
    lines = []
    for key, value in connector.items():
        lines.append(f"- `{key}`: {_format_value(value)}")
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        inner = ", ".join(f"{key}={_format_value(val)}" for key, val in value.items())
        return "{" + inner + "}"
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value)
    return f"`{value}`"

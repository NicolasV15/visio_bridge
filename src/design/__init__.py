"""Generic design-rule framework for Visio Bridge."""

from .context import DesignCapabilityRegistry, DesignContext, DesignTarget, default_design_registry
from .engine import audit_design, plan_design_commands
from .model import (
    DesignProfile,
    DesignReport,
    DesignRule,
    DesignViolation,
    FixSuggestion,
    RuleSeverity,
)
from .profile_docs import (
    describe_design_profile,
    load_profile_markdown_template,
    render_design_profile_markdown,
    write_design_profile_markdown,
)
from .profiles.circuit_diagram import CIRCUIT_SCHEMATIC_PROFILE

__all__ = [
    "DesignCapabilityRegistry",
    "DesignContext",
    "DesignProfile",
    "DesignReport",
    "DesignRule",
    "DesignTarget",
    "DesignViolation",
    "FixSuggestion",
    "RuleSeverity",
    "audit_design",
    "default_design_registry",
    "describe_design_profile",
    "load_profile_markdown_template",
    "plan_design_commands",
    "render_design_profile_markdown",
    "write_design_profile_markdown",
    "CIRCUIT_SCHEMATIC_PROFILE",
]

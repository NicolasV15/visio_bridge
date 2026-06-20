from .src.core.bridge import VisioBridge
from .src.core.locator import ElementLocator
from .src.core.formula_cache import FormulaCacheResult, recalculate_formula_cache
from .src.skill import (
    to_skill,
    apply_skill_commands,
    to_settings_skill,
    apply_settings_commands,
    apply_instance_commands,
)
from .src.desktop import (
    DesktopCommandResult,
    LocalWindowsTransport,
    ParallelsTransport,
    VisioDesktopSession,
    apply_desktop_command_groups,
    apply_instance_commands_desktop,
    apply_settings_commands_desktop,
    apply_skill_commands_desktop,
    create_default_transport,
    mac_path_to_parallels_unc,
)
from .src.design import (
    CIRCUIT_SCHEMATIC_PROFILE,
    DesignCapabilityRegistry,
    DesignContext,
    DesignProfile,
    DesignReport,
    DesignRule,
    DesignViolation,
    FixSuggestion,
    RuleSeverity,
    audit_design,
    default_design_registry,
    describe_design_profile,
    plan_design_commands,
    render_design_profile_markdown,
)

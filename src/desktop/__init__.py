"""Optional Visio desktop automation backend."""

from .session import (
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

__all__ = [
    "DesktopCommandResult",
    "LocalWindowsTransport",
    "ParallelsTransport",
    "VisioDesktopSession",
    "apply_desktop_command_groups",
    "apply_instance_commands_desktop",
    "apply_settings_commands_desktop",
    "apply_skill_commands_desktop",
    "create_default_transport",
    "mac_path_to_parallels_unc",
]

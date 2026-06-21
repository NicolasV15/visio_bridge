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
from .session_control import (
    VisioDocumentSessionInfo,
    VisioSessionActionResult,
    VisioSessionManager,
    close_visio_file,
    find_visio_document,
    list_visio_documents,
    open_visio_file,
    refresh_visio_file,
)

__all__ = [
    "DesktopCommandResult",
    "LocalWindowsTransport",
    "ParallelsTransport",
    "VisioDocumentSessionInfo",
    "VisioDesktopSession",
    "VisioSessionActionResult",
    "VisioSessionManager",
    "apply_desktop_command_groups",
    "apply_instance_commands_desktop",
    "apply_settings_commands_desktop",
    "apply_skill_commands_desktop",
    "close_visio_file",
    "create_default_transport",
    "find_visio_document",
    "list_visio_documents",
    "mac_path_to_parallels_unc",
    "open_visio_file",
    "refresh_visio_file",
]

"""Optional Visio desktop automation backend."""

from .pdf_export import (
    VisioPdfExportOptions,
    VisioPdfExportResult,
    export_visio_pdf,
)
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
    export_pdf_desktop,
    mac_path_to_parallels_unc,
)
from .session_control import (
    VisioDocumentSessionInfo,
    VisioSessionActionResult,
    VisioSessionManager,
    close_visio_file,
    export_open_document_pdf,
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
    "VisioPdfExportOptions",
    "VisioPdfExportResult",
    "VisioDesktopSession",
    "VisioSessionActionResult",
    "VisioSessionManager",
    "apply_desktop_command_groups",
    "apply_instance_commands_desktop",
    "apply_settings_commands_desktop",
    "apply_skill_commands_desktop",
    "close_visio_file",
    "create_default_transport",
    "export_open_document_pdf",
    "export_pdf_desktop",
    "export_visio_pdf",
    "find_visio_document",
    "list_visio_documents",
    "mac_path_to_parallels_unc",
    "open_visio_file",
    "refresh_visio_file",
]

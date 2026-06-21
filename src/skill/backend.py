from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable


from ..core.config import load_config

XML_BACKENDS = {"xml", "zip", "legacy", "original"}
DESKTOP_BACKENDS = {"desktop", "visio", "visio-api", "com"}


def _normalize_backend_value(backend: str | None, *, source: str) -> str:
    if backend is None:
        raise ValueError(
            f"{source} backend is required. Choose backend='desktop' or backend='xml'."
        )
    normalized = str(backend).strip().lower()
    if normalized in XML_BACKENDS:
        return "xml"
    if normalized in DESKTOP_BACKENDS:
        return "desktop"
    raise ValueError(f"Unsupported {source} backend: {backend}")


def normalize_backend(backend: str | None) -> str:
    return _normalize_backend_value(backend, source="phase-two")


def require_configured_backend(selected_backend: str) -> str:
    cfg = load_config()
    configured = _normalize_backend_value(
        cfg.get("backend"),
        source="configured",
    )
    if configured != selected_backend:
        raise RuntimeError(
            "Configured backend does not match requested backend. "
            f"configured={configured!r}, requested={selected_backend!r}. "
            "Update .visio_bridge.json or call the entry point with the configured mode."
        )
    return configured


def _same_path(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except FileNotFoundError:
        return Path(left).expanduser().absolute() == Path(right).expanduser().absolute()


def _reload_bridge_if_target_matches_source(
    bridge: Any,
    output_path: str | os.PathLike[str] | None,
) -> None:
    if output_path is not None and not _same_path(output_path, bridge.file_path):
        return
    bridge.__init__(str(output_path or bridge.file_path))


def _record_backend(bridge: Any, backend: str, error: Exception | None = None) -> None:
    bridge.last_phase2_backend = backend
    bridge.last_phase2_desktop_error = str(error) if error is not None else None


def try_desktop_backend(
    bridge: Any,
    *,
    backend: str | None,
    output_path: str | os.PathLike[str] | None,
    desktop_apply: Callable[..., Any],
) -> tuple[bool, Any]:
    """Run the explicitly selected backend after config consistency checks.

    Returns ``(True, result)`` when the desktop backend handled the command.
    Returns ``(False, None)`` when explicit XML mode was selected and allowed.
    """

    selected = normalize_backend(backend)
    require_configured_backend(selected)
    if selected == "xml":
        _record_backend(bridge, "xml")
        return False, None

    try:
        result = desktop_apply(output_path=output_path)
    except Exception as exc:
        _record_backend(bridge, "desktop", exc)
        raise

    _reload_bridge_if_target_matches_source(bridge, output_path)
    _record_backend(bridge, "desktop")
    return True, result


def save_xml_if_requested(
    bridge: Any,
    output_path: str | os.PathLike[str] | None,
) -> None:
    if output_path is not None:
        bridge.save(str(output_path))

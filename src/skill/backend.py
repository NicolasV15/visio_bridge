from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable


from ..core.config import load_config

XML_BACKENDS = {"xml", "zip", "legacy", "original"}
DESKTOP_BACKENDS = {"desktop", "visio", "visio-api", "com"}
AUTO_BACKENDS = {"auto", None}


def normalize_backend(backend: str | None) -> str:
    if backend in AUTO_BACKENDS:
        cfg = load_config()
        backend = cfg.get("backend", "auto")
        if backend in AUTO_BACKENDS:
            return "auto"
    normalized = str(backend).strip().lower()
    if normalized in XML_BACKENDS:
        return "xml"
    if normalized in DESKTOP_BACKENDS:
        return "desktop"
    if normalized == "auto":
        return "auto"
    raise ValueError(f"Unsupported phase-two backend: {backend}")


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
    """Run desktop backend when requested/available.

    Returns ``(True, result)`` when the desktop backend handled the command.
    Returns ``(False, None)`` when ``backend='auto'`` cannot use desktop and
    the caller should fall back to the XML implementation.
    """

    selected = normalize_backend(backend)
    if selected == "xml":
        _record_backend(bridge, "xml")
        return False, None

    try:
        result = desktop_apply(output_path=output_path)
    except Exception as exc:
        if selected == "desktop":
            _record_backend(bridge, "desktop", exc)
            raise
        _record_backend(bridge, "xml", exc)
        return False, None

    _reload_bridge_if_target_matches_source(bridge, output_path)
    _record_backend(bridge, "desktop")
    return True, result


def save_xml_fallback_if_requested(
    bridge: Any,
    output_path: str | os.PathLike[str] | None,
) -> None:
    if output_path is not None:
        bridge.save(str(output_path))

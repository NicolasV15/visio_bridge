"""Visio desktop session management helpers.

These helpers connect to the user's existing Visio desktop instance when
possible. They are intentionally separate from ``VisioDesktopSession`` because
the phase-two command runner creates an isolated Visio process, while this
module manages documents the user already has open.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .session import (
    DesktopCommandResult,
    DesktopTransport,
    create_default_transport,
    _parse_runner_json,
)


@dataclass
class VisioDocumentSessionInfo:
    """Information about a document currently open in Visio desktop."""

    name: str
    full_name: str
    saved: bool
    active: bool
    read_only: bool
    window_count: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisioDocumentSessionInfo":
        return cls(
            name=str(data.get("name", "")),
            full_name=str(data.get("full_name", "")),
            saved=bool(data.get("saved", False)),
            active=bool(data.get("active", False)),
            read_only=bool(data.get("read_only", False)),
            window_count=int(data.get("window_count", 0) or 0),
        )


@dataclass
class VisioSessionActionResult:
    """Result from a Visio session management action."""

    action: str
    status: str
    message: str = ""
    document: VisioDocumentSessionInfo | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisioSessionActionResult":
        document = data.get("document")
        return cls(
            action=str(data.get("action", "")),
            status=str(data.get("status", "")),
            message=str(data.get("message", "")),
            document=(
                VisioDocumentSessionInfo.from_dict(document)
                if isinstance(document, dict)
                else None
            ),
        )


class VisioSessionManager:
    """Run Visio desktop session actions through the configured transport."""

    def __init__(
        self,
        transport: DesktopTransport | None = None,
        *,
        mode: str | None = None,
        vm_name: str | None = None,
        timeout: int | None = None,
        keep_artifacts: bool = False,
    ):
        from ..core.config import load_config

        cfg = load_config()
        if mode is None:
            mode = cfg.get("desktop_transport_mode")
        if vm_name is None:
            vm_name = cfg.get("vm_name")

        self.transport = transport or create_default_transport(mode, vm_name=vm_name)
        self.timeout = timeout if timeout is not None else cfg.get("timeout", 180)
        self.keep_artifacts = keep_artifacts

    def run(
        self,
        action: str,
        *,
        file_path: str | os.PathLike[str] | None = None,
        visible: bool = True,
        activate: bool = True,
        save: bool = False,
        discard_unsaved: bool = False,
    ) -> DesktopCommandResult:
        host_file = (
            Path(file_path).expanduser()
            if file_path is not None
            else Path.cwd() / "visio_bridge_session"
        )
        mapped_file_path = self.transport.map_path(host_file) if file_path is not None else None
        payload = {
            "action": action,
            "file_path": mapped_file_path,
            "visible": visible,
            "activate": activate,
            "save": save,
            "discard_unsaved": discard_unsaved,
        }

        try:
            completed = self.transport.run_python_source(
                PYTHON_SESSION_RUNNER,
                payload,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Visio session command timed out after {self.timeout} seconds."
            ) from exc

        data = _parse_runner_json(completed.stdout)
        if completed.returncode != 0:
            raise RuntimeError(
                "Visio session command failed "
                f"(exit {completed.returncode}).\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        if data and data.get("status") == "error":
            raise RuntimeError(data.get("message") or "Visio session command failed.")
        return DesktopCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            data=data,
        )


def _manager_from_kwargs(
    *,
    session: VisioSessionManager | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    keep_artifacts: bool = False,
) -> VisioSessionManager:
    return session or VisioSessionManager(
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )


def list_visio_documents(
    *,
    session: VisioSessionManager | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    keep_artifacts: bool = False,
) -> list[VisioDocumentSessionInfo]:
    """Return documents currently open in the user's Visio instance."""

    runner = _manager_from_kwargs(
        session=session,
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )
    result = runner.run("list")
    data = result.data or {}
    documents = data.get("documents", [])
    return [
        VisioDocumentSessionInfo.from_dict(item)
        for item in documents
        if isinstance(item, dict)
    ]


def find_visio_document(
    file_path: str | os.PathLike[str],
    *,
    session: VisioSessionManager | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    keep_artifacts: bool = False,
) -> VisioDocumentSessionInfo | None:
    """Find an already-open Visio document by path."""

    runner = _manager_from_kwargs(
        session=session,
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )
    result = runner.run("find", file_path=file_path)
    data = result.data or {}
    document = data.get("document")
    return VisioDocumentSessionInfo.from_dict(document) if isinstance(document, dict) else None


def open_visio_file(
    file_path: str | os.PathLike[str],
    *,
    visible: bool = True,
    activate: bool = True,
    session: VisioSessionManager | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    keep_artifacts: bool = False,
) -> VisioSessionActionResult:
    """Open a file in Visio, or activate it when it is already open."""

    runner = _manager_from_kwargs(
        session=session,
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )
    result = runner.run(
        "open",
        file_path=file_path,
        visible=visible,
        activate=activate,
    )
    return VisioSessionActionResult.from_dict(result.data or {})


def close_visio_file(
    file_path: str | os.PathLike[str],
    *,
    save: bool = False,
    discard_unsaved: bool = False,
    session: VisioSessionManager | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    keep_artifacts: bool = False,
) -> VisioSessionActionResult:
    """Close a Visio document.

    By default this refuses to close documents with unsaved UI changes. Pass
    ``save=True`` to save first, or ``discard_unsaved=True`` to close without
    prompting and discard those UI changes.
    """

    runner = _manager_from_kwargs(
        session=session,
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )
    result = runner.run(
        "close",
        file_path=file_path,
        save=save,
        discard_unsaved=discard_unsaved,
    )
    return VisioSessionActionResult.from_dict(result.data or {})


def refresh_visio_file(
    file_path: str | os.PathLike[str],
    *,
    discard_unsaved: bool = True,
    activate: bool = True,
    visible: bool = True,
    session: VisioSessionManager | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    keep_artifacts: bool = False,
) -> VisioSessionActionResult:
    """Reload a file in Visio by closing and reopening the matching document.

    The default ``discard_unsaved=True`` intentionally discards unsaved changes
    made in the Visio UI so the reopened document reflects the current file on
    disk.
    """

    runner = _manager_from_kwargs(
        session=session,
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )
    result = runner.run(
        "refresh",
        file_path=file_path,
        discard_unsaved=discard_unsaved,
        activate=activate,
        visible=visible,
    )
    return VisioSessionActionResult.from_dict(result.data or {})


PYTHON_SESSION_RUNNER = r'''
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime

import pythoncom
import win32com.client


VIS_OPEN_RW = 32


def log_step(payload: dict, message: str) -> None:
    print(f"{datetime.now().isoformat()} {message}", file=sys.stderr, flush=True)


def write_result(result_status: str, message: str = "", **fields) -> None:
    data = {"status": result_status, "message": message}
    data.update(fields)
    print(json.dumps(data, ensure_ascii=False), flush=True)


def normalize_path(path) -> str:
    if not path:
        return ""
    text = str(path).replace("/", "\\").strip()
    try:
        return os.path.normcase(os.path.abspath(text))
    except Exception:
        return text.lower()


def document_info(app, doc):
    full_name = ""
    name = ""
    saved = False
    read_only = False
    window_count = 0
    active = False
    try:
        full_name = str(doc.FullName)
    except Exception:
        pass
    try:
        name = str(doc.Name)
    except Exception:
        name = os.path.basename(full_name)
    try:
        saved = bool(doc.Saved)
    except Exception:
        pass
    try:
        read_only = bool(doc.ReadOnly)
    except Exception:
        pass
    try:
        window_count = int(doc.Windows.Count)
    except Exception:
        pass
    try:
        active = app.ActiveDocument is not None and app.ActiveDocument.FullName == doc.FullName
    except Exception:
        active = False
    return {
        "name": name,
        "full_name": full_name,
        "saved": saved,
        "active": active,
        "read_only": read_only,
        "window_count": window_count,
    }


def active_application(create=False, visible=True):
    try:
        app = win32com.client.GetActiveObject("Visio.Application")
        if visible is not None:
            app.Visible = bool(visible)
        return app, False
    except Exception:
        if not create:
            return None, False
    app = win32com.client.DispatchEx("Visio.Application")
    app.Visible = bool(visible)
    return app, True


def iter_documents(app):
    if app is None:
        return []
    return [doc for doc in app.Documents]


def find_document(app, file_path):
    target = normalize_path(file_path)
    for doc in iter_documents(app):
        try:
            full_name = str(doc.FullName)
        except Exception:
            full_name = ""
        if full_name and normalize_path(full_name) == target:
            return doc
        if full_name and full_name.lower() == str(file_path).lower():
            return doc
    return None


def activate_document(doc):
    try:
        if doc.Windows.Count > 0:
            doc.Windows.Item(1).Activate()
            return
    except Exception:
        pass
    try:
        doc.Application.ActiveWindow.Activate()
    except Exception:
        pass


def open_document(app, file_path, activate=True):
    doc = app.Documents.OpenEx(file_path, VIS_OPEN_RW)
    if activate:
        activate_document(doc)
    return doc


def close_document(doc, save=False, discard_unsaved=False):
    try:
        is_saved = bool(doc.Saved)
    except Exception:
        is_saved = True
    if save:
        doc.Save()
    elif not is_saved:
        if not discard_unsaved:
            raise RuntimeError(
                "Document has unsaved changes. Pass save=True or discard_unsaved=True."
            )
        doc.Saved = True
    doc.Close()


def main() -> int:
    payload = json.load(sys.stdin)

    pythoncom.CoInitialize()
    try:
        action = payload.get("action")
        file_path = payload.get("file_path")
        visible = bool(payload.get("visible", True))
        activate = bool(payload.get("activate", True))
        save = bool(payload.get("save", False))
        discard_unsaved = bool(payload.get("discard_unsaved", False))

        log_step(payload, f"action_start {action}")
        create = action in {"open", "refresh"}
        app, created = active_application(create=create, visible=visible if create else None)

        if action == "list":
            documents = [document_info(app, doc) for doc in iter_documents(app)]
            write_result("ok", documents=documents)
            return 0

        if app is None:
            if action == "find":
                write_result("ok", document=None)
                return 0
            write_result("ok", action=action, status="not_found", message="Visio is not running.")
            return 0

        if action == "find":
            doc = find_document(app, file_path)
            write_result("ok", document=document_info(app, doc) if doc is not None else None)
            return 0

        if action == "open":
            doc = find_document(app, file_path)
            if doc is not None:
                if activate:
                    activate_document(doc)
                write_result(
                    "ok",
                    action="open",
                    status="already_open",
                    document=document_info(app, doc),
                )
                return 0
            doc = open_document(app, file_path, activate=activate)
            write_result("ok", action="open", status="opened", document=document_info(app, doc))
            return 0

        if action == "close":
            doc = find_document(app, file_path)
            if doc is None:
                write_result("ok", action="close", status="not_found", message="Document is not open.")
                return 0
            info = document_info(app, doc)
            close_document(doc, save=save, discard_unsaved=discard_unsaved)
            write_result("ok", action="close", status="closed", document=info)
            return 0

        if action == "refresh":
            doc = find_document(app, file_path)
            if doc is not None:
                close_document(doc, save=False, discard_unsaved=discard_unsaved)
                status = "refreshed"
            else:
                status = "opened"
            doc = open_document(app, file_path, activate=activate)
            write_result("ok", action="refresh", status=status, document=document_info(app, doc))
            return 0

        raise ValueError(f"Unsupported Visio session action: {action}")
    except Exception as exc:
        log_step(payload, f"error {exc}")
        write_result("error", f"{exc}\n{traceback.format_exc()}")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
'''

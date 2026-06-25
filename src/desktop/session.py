"""Visio desktop automation backend.

This module keeps the existing phase-two JSON command shape intact and sends
commands to a Windows Python runner that automates Visio desktop through
``pywin32`` / ``win32com.client``.  It supports two transports:

* macOS + Parallels Desktop: ``prlctl exec <vm> --current-user cmd /c python ...``
* native Windows: local ``python`` execution
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence

from .pdf_export import VisioPdfExportOptions, VisioPdfExportResult


@dataclass
class DesktopCommandResult:
    """Result returned by a desktop command run."""

    returncode: int
    stdout: str
    stderr: str
    data: dict[str, Any] | None = None


class DesktopTransport:
    """Small transport protocol implemented by concrete desktop runners."""

    mode = "base"

    def map_path(self, path: str | os.PathLike[str]) -> str:
        raise NotImplementedError

    def run_python_source(
        self,
        source: str,
        payload: Mapping[str, Any],
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        raise NotImplementedError

    def run_python_file(
        self,
        script_path: str,
        payload_path: str,
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        source = Path(script_path).read_text(encoding="utf-8")
        payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
        return self.run_python_source(source, payload, timeout=timeout)


PYTHON_STDIN_BOOTSTRAP = (
    "import base64,io,json,sys;"
    "bundle=json.load(sys.stdin);"
    "source=base64.b64decode(bundle['source_b64']).decode('utf-8');"
    "payload=base64.b64decode(bundle['payload_b64']).decode('utf-8');"
    "sys.stdin=io.StringIO(payload);"
    "exec(source, {'__name__':'__main__'})"
)


def _runner_input(source: str, payload: Mapping[str, Any]) -> str:
    payload_text = json.dumps(payload, ensure_ascii=False)
    return json.dumps(
        {
            "source_b64": base64.b64encode(source.encode("utf-8")).decode("ascii"),
            "payload_b64": base64.b64encode(payload_text.encode("utf-8")).decode("ascii"),
        }
    )


def _windows_join(*parts: str) -> str:
    return str(PureWindowsPath(*parts))


def mac_path_to_parallels_unc(
    path: str | os.PathLike[str],
    *,
    home: str | os.PathLike[str] | None = None,
) -> str:
    """Map a host macOS path to the Parallels ``\\Mac\\Home`` UNC path.

    The current project lives below the user's home directory, which Parallels
    exposes as ``\\Mac\\Home`` when home sharing is enabled.
    """

    source = Path(path).expanduser()
    home_path = Path(home).expanduser() if home is not None else Path.home()
    try:
        rel = source.resolve().relative_to(home_path.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Path is not under the Parallels shared home directory: {source}"
        ) from exc
    return _windows_join(r"\\Mac\Home", *rel.parts)


@dataclass
class ParallelsTransport(DesktopTransport):
    """Run Python inside a Parallels Windows VM."""

    vm_name: str = ""
    home: str | os.PathLike[str] | None = None
    prlctl: str = "prlctl"
    current_user: bool = True

    mode: str = "parallels"

    def map_path(self, path: str | os.PathLike[str]) -> str:
        return mac_path_to_parallels_unc(path, home=self.home)

    def run_python_source(
        self,
        source: str,
        payload: Mapping[str, Any],
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        vm = self.vm_name
        if not vm:
            raise RuntimeError(
                "Parallels VM name must be configured explicitly for desktop transport."
            )
        cmd = [
            self.prlctl,
            "exec",
            vm,
        ]
        if self.current_user:
            cmd.append("--current-user")
        cmd.extend(
            [
                "cmd",
                "/c",
                f'python -c "{PYTHON_STDIN_BOOTSTRAP}"',
            ]
        )
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            input=_runner_input(source, payload),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )


@dataclass
class LocalWindowsTransport(DesktopTransport):
    """Run Python directly on Windows."""

    python: str = "python"
    mode: str = "windows-local"

    def map_path(self, path: str | os.PathLike[str]) -> str:
        return str(path)

    def run_python_source(
        self,
        source: str,
        payload: Mapping[str, Any],
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            self.python,
            "-c",
            PYTHON_STDIN_BOOTSTRAP,
        ]
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            input=_runner_input(source, payload),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )


def create_default_transport(
    mode: str | None = None,
    *,
    vm_name: str | None = None,
) -> DesktopTransport:
    """Create a desktop transport for the current host."""
    from ..core.config import load_config
    cfg = load_config()
    
    if mode is None:
        mode = cfg.get("desktop_transport_mode")
    
    if not vm_name:
        vm_name = cfg.get("vm_name")

    if mode is None:
        raise ValueError(
            "desktop_transport_mode must be configured explicitly as "
            "'windows-local' or 'parallels'."
        )
    normalized = str(mode).strip().lower()
    if normalized in {"windows", "windows-local", "local"}:
        return LocalWindowsTransport()
    if normalized in {"parallels", "parallels-desktop"}:
        if not vm_name:
            raise ValueError(
                "vm_name must be configured explicitly when desktop_transport_mode='parallels'."
            )
        return ParallelsTransport(vm_name=vm_name)
    raise ValueError(f"Unsupported desktop transport mode: {mode}")


def _normalize_command_groups(
    command_groups: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize executor groups into the wire shape consumed by the runner."""

    normalized: list[dict[str, Any]] = []
    if isinstance(command_groups, Mapping):
        for executor, groups in command_groups.items():
            if isinstance(groups, Mapping):
                groups = [groups]
            for group in groups:
                normalized.append(
                    {
                        "executor": executor,
                        "target": group.get("target"),
                        "commands": list(group.get("commands", [])),
                    }
                )
        return normalized

    for group in command_groups:
        executor = group.get("executor")
        if not executor:
            raise ValueError(f"Desktop command group is missing executor: {group}")
        normalized.append(
            {
                "executor": executor,
                "target": group.get("target"),
                "commands": list(group.get("commands", [])),
            }
        )
    return normalized


class VisioDesktopSession:
    """Execute phase-two commands through Visio desktop COM automation."""

    def __init__(
        self,
        transport: DesktopTransport | None = None,
        *,
        mode: str | None = None,
        vm_name: str | None = None,
        timeout: int | None = None,
        visible: bool | None = None,
        keep_artifacts: bool = False,
        stage_local: bool | None = None,
    ):
        from ..core.config import load_config
        cfg = load_config()

        if mode is None:
            mode = cfg.get("desktop_transport_mode")
        
        if not vm_name:
            vm_name = cfg.get("vm_name")

        self.transport = transport or create_default_transport(mode, vm_name=vm_name)
        self.timeout = timeout if timeout is not None else cfg.get("timeout", 180)
        self.visible = visible if visible is not None else cfg.get("visible", False)
        self.keep_artifacts = keep_artifacts
        _ = stage_local  # Compatibility no-op; desktop runs no longer stage files.

    def run(
        self,
        file_path: str | os.PathLike[str],
        command_groups: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        output_path: str | os.PathLike[str] | None = None,
        pdf_output_path: str | os.PathLike[str] | None = None,
        pdf_options: VisioPdfExportOptions | Mapping[str, Any] | None = None,
    ) -> DesktopCommandResult:
        host_file = Path(file_path).expanduser()
        host_output = Path(output_path).expanduser() if output_path else None
        host_pdf_output = Path(pdf_output_path).expanduser() if pdf_output_path else None
        if pdf_options is not None and host_pdf_output is None:
            raise ValueError("pdf_output_path is required when pdf_options is provided.")
        pdf_payload = None
        if host_pdf_output is not None:
            pdf_payload = VisioPdfExportOptions.from_value(pdf_options).to_payload(
                source="saved_file"
            )

        payload = {
            "file_path": self.transport.map_path(host_file),
            "output_path": (
                self.transport.map_path(host_output) if host_output is not None else None
            ),
            "pdf_output_path": (
                self.transport.map_path(host_pdf_output)
                if host_pdf_output is not None
                else None
            ),
            "pdf_options": pdf_payload,
            "visible": self.visible,
            "command_groups": _normalize_command_groups(command_groups),
        }

        try:
            completed = self.transport.run_python_source(
                PYTHON_RUNNER,
                payload,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Visio desktop command timed out after {self.timeout} seconds."
            ) from exc
        data = _parse_runner_json(completed.stdout)
        if completed.returncode != 0:
            raise RuntimeError(
                "Visio desktop command failed "
                f"(exit {completed.returncode}).\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        if data and data.get("status") == "error":
            raise RuntimeError(data.get("message") or "Visio desktop command failed.")
        return DesktopCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            data=data,
        )

    def export_pdf(
        self,
        file_path: str | os.PathLike[str],
        output_pdf_path: str | os.PathLike[str],
        *,
        options: VisioPdfExportOptions | Mapping[str, Any] | None = None,
    ) -> VisioPdfExportResult:
        result = self.run(
            file_path,
            [],
            pdf_output_path=output_pdf_path,
            pdf_options=options,
        )
        return VisioPdfExportResult.from_dict(result.data or {})


def _parse_runner_json(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


def apply_desktop_command_groups(
    file_path: str | os.PathLike[str],
    command_groups: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    output_path: str | os.PathLike[str] | None = None,
    pdf_output_path: str | os.PathLike[str] | None = None,
    pdf_options: VisioPdfExportOptions | Mapping[str, Any] | None = None,
    session: VisioDesktopSession | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    visible: bool | None = None,
    stage_local: bool | None = None,
) -> DesktopCommandResult:
    runner = session or VisioDesktopSession(
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        visible=visible,
        stage_local=stage_local,
    )
    return runner.run(
        file_path,
        command_groups,
        output_path=output_path,
        pdf_output_path=pdf_output_path,
        pdf_options=pdf_options,
    )


def export_pdf_desktop(
    file_path: str | os.PathLike[str],
    output_pdf_path: str | os.PathLike[str],
    *,
    options: VisioPdfExportOptions | Mapping[str, Any] | None = None,
    session: VisioDesktopSession | None = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    visible: bool | None = None,
    stage_local: bool | None = None,
) -> VisioPdfExportResult:
    runner = session or VisioDesktopSession(
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        visible=visible,
        stage_local=stage_local,
    )
    return runner.export_pdf(file_path, output_pdf_path, options=options)


def apply_skill_commands_desktop(
    file_path: str | os.PathLike[str],
    shape_path: str,
    commands: list[dict[str, Any]],
    *,
    output_path: str | os.PathLike[str] | None = None,
    session: VisioDesktopSession | None = None,
    **kwargs: Any,
) -> DesktopCommandResult:
    return apply_desktop_command_groups(
        file_path,
        [{"executor": "symbol_editor", "target": shape_path, "commands": commands}],
        output_path=output_path,
        session=session,
        **kwargs,
    )


def apply_settings_commands_desktop(
    file_path: str | os.PathLike[str],
    commands: list[dict[str, Any]],
    *,
    output_path: str | os.PathLike[str] | None = None,
    session: VisioDesktopSession | None = None,
    **kwargs: Any,
) -> DesktopCommandResult:
    return apply_desktop_command_groups(
        file_path,
        [{"executor": "doc_page_settings", "commands": commands}],
        output_path=output_path,
        session=session,
        **kwargs,
    )


def apply_instance_commands_desktop(
    file_path: str | os.PathLike[str],
    commands: list[dict[str, Any]],
    *,
    output_path: str | os.PathLike[str] | None = None,
    session: VisioDesktopSession | None = None,
    **kwargs: Any,
) -> DesktopCommandResult:
    return apply_desktop_command_groups(
        file_path,
        [{"executor": "instance_manager", "commands": commands}],
        output_path=output_path,
        session=session,
        **kwargs,
    )


PYTHON_RUNNER = r'''
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import traceback
from datetime import datetime

import pythoncom
import win32com.client
import win32process


VIS_SECTION_CONNECTION = 7
VIS_SECTION_FIRST_GEOMETRY = 10
VIS_SECTION_USER = 242
VIS_TAG_DEFAULT = 0
VIS_TAG_MOVE_TO = 138
VIS_TAG_LINE_TO = 139
VIS_TAG_ELLIPTICAL_ARC_TO = 144
VIS_TAG_CONNECTION_POINT = 153
VIS_ROW_LAST = -2
VIS_OPEN_RW = 32
VIS_FIXED_FORMAT_PDF = 1
VIS_DOC_EX_INTENT_SCREEN = 0
VIS_DOC_EX_INTENT_PRINT = 1
VIS_PRINT_ALL = 0
VIS_PRINT_FROM_TO = 1
VIS_PRINT_CURRENT_PAGE = 2
VIS_PRINT_SELECTION = 3
VIS_PRINT_CURRENT_VIEW = 4
VIS_SELECT = 2


def log_step(payload: dict, message: str) -> None:
    print(f"{datetime.now().isoformat()} {message}", file=sys.stderr, flush=True)


def write_result(status: str, message: str = "", results: list | None = None, **fields) -> None:
    data = {"status": status, "message": message, "results": results or []}
    data.update(fields)
    print(json.dumps(data, ensure_ascii=False), flush=True)


def terminate_process(pid) -> None:
    if not pid:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


def application_process_id(app):
    try:
        hwnd = int(app.WindowHandle32)
        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
        return int(process_id)
    except Exception:
        return None


def cmd_value(cmd, name, default=None):
    return cmd[name] if name in cmd else default


def looks_like_formula(value) -> bool:
    if value is None:
        return False
    text = str(value)
    if any(token in text for token in ("Width", "Height", "Geometry", "TheDoc!", "User.", "Sheet.")):
        return True
    return any(ch in text for ch in ("*", "+", "/")) or text.strip().startswith("-")


def set_cell_formula_value(owner, cell_name, value=None, formula=None, unit=None, preserve_formula=False):
    if not cell_name:
        raise ValueError("Cell name is required.")
    cell = owner.CellsU(str(cell_name))
    set_cell_object_formula_value(cell, value, formula, unit, preserve_formula)


def set_cell_object_formula_value(cell, value=None, formula=None, unit=None, preserve_formula=False):
    effective_formula = None if formula is None else str(formula)
    effective_value = None if value is None else str(value)
    if effective_formula is None and looks_like_formula(effective_value):
        effective_formula = effective_value
        effective_value = "0"
    if effective_formula is not None:
        if effective_formula:
            cell.FormulaU = effective_formula
        elif effective_value is not None:
            cell.FormulaU = effective_value
    elif effective_value is not None:
        cell.FormulaU = effective_value


def connection_cell_column(name):
    mapping = {"X": 0, "Y": 1, "DirX": 2, "DirY": 3}
    if name not in mapping:
        raise ValueError(f"Unsupported connection cell: {name}")
    return mapping[name]


def geometry_cell_column(name):
    mapping = {"X": 0, "Y": 1, "A": 2, "B": 3, "C": 4, "D": 5}
    if name not in mapping:
        raise ValueError(f"Unsupported geometry cell: {name}")
    return mapping[name]


def connection_command_values(cmd, cell_name):
    if cell_name == "DirX":
        return cmd_value(cmd, "dir_x", cmd_value(cmd, "dirx")), cmd_value(cmd, "dir_x_formula", cmd_value(cmd, "dirx_formula"))
    if cell_name == "DirY":
        return cmd_value(cmd, "dir_y", cmd_value(cmd, "diry")), cmd_value(cmd, "dir_y_formula", cmd_value(cmd, "diry_formula"))
    prop = cell_name.lower()
    return cmd.get(prop), cmd.get(f"{prop}_formula")


def find_page(doc, ref):
    ref = str(ref)
    try:
        return doc.Pages.ItemU(ref)
    except Exception:
        pass
    for page in doc.Pages:
        if str(page.ID) == ref or page.Name == ref or page.NameU == ref:
            return page
    raise ValueError(f"Could not find page: {ref}")


def find_master(doc, ref):
    ref = str(ref)
    try:
        return doc.Masters.ItemU(ref)
    except Exception:
        pass
    for master in doc.Masters:
        if str(master.ID) == ref or master.Name == ref or master.NameU == ref:
            return master
    raise ValueError(f"Could not find master: {ref}")


def find_shape_by_id(shapes, shape_id):
    target = int(shape_id)
    for shape in shapes:
        if int(shape.ID) == target:
            return shape
        try:
            if shape.Shapes.Count > 0:
                found = find_shape_by_id(shape.Shapes, target)
                if found is not None:
                    return found
        except Exception:
            pass
    return None


def first_shape(container):
    if container.Shapes.Count < 1:
        raise ValueError("Target container contains no shapes.")
    return container.Shapes.Item(1)


def resolve_shape_path(doc, path):
    parts = [part for part in str(path).strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"Invalid shape path: {path}")
    if parts[0] == "pages":
        current = find_page(doc, parts[1])
    elif parts[0] == "masters":
        current = find_master(doc, parts[1])
    else:
        raise ValueError(f"Unsupported shape path category: {parts[0]}")
    idx = 2
    saw_shape = False
    while idx < len(parts):
        if parts[idx] != "shape":
            raise ValueError(f"Unsupported path token {parts[idx]!r} in {path}")
        shape = find_shape_by_id(current.Shapes, parts[idx + 1])
        if shape is None:
            raise ValueError(f"Could not find shape ID {parts[idx + 1]} in {path}")
        current = shape
        saw_shape = True
        idx += 2
    return current if saw_shape else first_shape(current)


def resolve_container_path(doc, path):
    parts = [part for part in str(path).strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"Invalid container path: {path}")
    if parts[0] == "pages":
        current = find_page(doc, parts[1])
    elif parts[0] == "masters":
        current = find_master(doc, parts[1])
    else:
        raise ValueError(f"Unsupported container path category: {parts[0]}")
    idx = 2
    while idx < len(parts):
        if parts[idx] != "shape":
            raise ValueError(f"Unsupported container path: {path}")
        shape = find_shape_by_id(current.Shapes, parts[idx + 1])
        if shape is None:
            raise ValueError(f"Could not find shape ID {parts[idx + 1]} in {path}")
        current = shape
        idx += 2
    return current


def parent_shape_path(path):
    parts = [part for part in str(path).strip("/").split("/") if part]
    if len(parts) >= 2 and parts[-2] == "shape":
        return "/".join(parts[:-2])
    raise ValueError(f"Invalid shape path: {path}")


def ensure_user_row(owner, name):
    try:
        owner.CellsU(f"User.{name}.Value")
    except Exception:
        owner.AddNamedRow(VIS_SECTION_USER, str(name), VIS_TAG_DEFAULT)


def set_user_row(owner, name, value=None, formula=None, unit=None):
    ensure_user_row(owner, name)
    set_cell_formula_value(owner, f"User.{name}.Value", value, formula, unit)
    try:
        set_cell_formula_value(owner, f"User.{name}.Prompt", "")
    except Exception:
        pass


def delete_user_row(owner, name):
    try:
        row = owner.CellsU(f"User.{name}.Value").Row
        owner.DeleteRow(VIS_SECTION_USER, row)
    except Exception:
        pass


def section_index(name, ix=0):
    if name == "Geometry":
        return VIS_SECTION_FIRST_GEOMETRY + int(ix)
    if name == "Connection":
        return VIS_SECTION_CONNECTION
    if name == "User":
        return VIS_SECTION_USER
    raise ValueError(f"Unsupported section for desktop backend: {name}")


def row_tag(row_type):
    if row_type == "MoveTo":
        return VIS_TAG_MOVE_TO
    if row_type == "LineTo":
        return VIS_TAG_LINE_TO
    if row_type == "EllipticalArcTo":
        return VIS_TAG_ELLIPTICAL_ARC_TO
    return VIS_TAG_DEFAULT


def ensure_section(shape, name, ix=0):
    section = section_index(name, ix)
    if not shape.SectionExists(section, 0):
        shape.AddSection(section)
    return section


def ensure_section_row(shape, section_name, section_ix=0, row_ix=0, row_name=None, row_type=None):
    if section_name == "User" and row_name:
        ensure_user_row(shape, row_name)
        return shape.CellsU(f"User.{row_name}.Value").Row
    section = ensure_section(shape, section_name, section_ix)
    if row_name:
        try:
            return shape.CellsU(f"{section_name}.{row_name}.Value").Row
        except Exception:
            pass
    row = int(row_ix or 0)
    try:
        shape.CellsSRC(section, row, 0)
        return row
    except Exception:
        if section_name == "Connection":
            return shape.AddRow(section, VIS_ROW_LAST, VIS_TAG_CONNECTION_POINT)
        shape.AddRow(section, row, row_tag(row_type))
        return row


def section_cell_name(section_name, section_ix, row_ix, row_name, cell_name):
    if section_name == "Geometry":
        return f"Geometry{int(section_ix) + 1}.{cell_name}{row_ix}"
    if section_name == "Connection":
        return f"Connections.{cell_name}{row_ix}"
    if section_name == "User" and row_name:
        return f"User.{row_name}.{cell_name}"
    raise ValueError(f"Unsupported section cell name: {section_name}")


def next_geometry_ix(shape):
    ix = 0
    while True:
        if not shape.SectionExists(VIS_SECTION_FIRST_GEOMETRY + ix, 0):
            return ix
        ix += 1


def add_geom_row(shape, geom_ix, row_ix, row_type, cells):
    section = ensure_section(shape, "Geometry", geom_ix)
    try:
        actual_row = shape.AddRow(section, VIS_ROW_LAST, row_tag(row_type))
    except Exception:
        actual_row = int(row_ix)
    for key, value in cells.items():
        cell = shape.CellsSRC(section, actual_row, geometry_cell_column(key))
        set_cell_object_formula_value(cell, value)


def add_rectangle_geometry(shape, cmd):
    geom_ix = next_geometry_ix(shape)
    ensure_section(shape, "Geometry", geom_ix)
    set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.NoFill", "0")
    set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.NoLine", "0")
    add_geom_row(shape, geom_ix, 1, "MoveTo", {"X": cmd_value(cmd, "x_min", "0"), "Y": cmd_value(cmd, "y_min", "0")})
    add_geom_row(shape, geom_ix, 2, "LineTo", {"X": cmd_value(cmd, "x_max", "Width"), "Y": cmd_value(cmd, "y_min", "0")})
    add_geom_row(shape, geom_ix, 3, "LineTo", {"X": cmd_value(cmd, "x_max", "Width"), "Y": cmd_value(cmd, "y_max", "Height")})
    add_geom_row(shape, geom_ix, 4, "LineTo", {"X": cmd_value(cmd, "x_min", "0"), "Y": cmd_value(cmd, "y_max", "Height")})
    add_geom_row(shape, geom_ix, 5, "LineTo", {"X": cmd_value(cmd, "x_min", "0"), "Y": cmd_value(cmd, "y_min", "0")})


def add_line_geometry(shape, cmd):
    geom_ix = next_geometry_ix(shape)
    ensure_section(shape, "Geometry", geom_ix)
    set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.NoFill", "1")
    set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.NoLine", "0")
    add_geom_row(shape, geom_ix, 1, "MoveTo", {"X": cmd_value(cmd, "x1", "0"), "Y": cmd_value(cmd, "y1", "0")})
    add_geom_row(shape, geom_ix, 2, "LineTo", {"X": cmd_value(cmd, "x2", "Width"), "Y": cmd_value(cmd, "y2", "Height")})


def mid_expr(a, b):
    return f"(({a})+({b}))*0.5"


def add_ellipse_geometry(shape, cmd, start_angle=0.0, sweep_angle=360.0):
    x_min = cmd_value(cmd, "x_min", "0")
    y_min = cmd_value(cmd, "y_min", "0")
    x_max = cmd_value(cmd, "x_max", "Width")
    y_max = cmd_value(cmd, "y_max", "Height")
    geom_ix = next_geometry_ix(shape)
    ensure_section(shape, "Geometry", geom_ix)
    closed = float(sweep_angle) >= 360.0
    set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.NoFill", "0" if closed else "1")
    set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.NoLine", "0")
    cx = mid_expr(x_min, x_max)
    cy = mid_expr(y_min, y_max)
    aspect = f"(({x_max})-({x_min}))/(({y_max})-({y_min}))"
    if closed:
        add_geom_row(shape, geom_ix, 1, "MoveTo", {"X": x_min, "Y": cy})
        add_geom_row(shape, geom_ix, 2, "EllipticalArcTo", {"X": x_max, "Y": cy, "A": cx, "B": y_max, "C": "0", "D": aspect})
        add_geom_row(shape, geom_ix, 3, "EllipticalArcTo", {"X": x_min, "Y": cy, "A": cx, "B": y_min, "C": "0", "D": aspect})
    else:
        rx = f"({x_max})-({cx})"
        ry = f"({y_max})-({cy})"
        theta1 = math.radians(float(start_angle))
        theta2 = math.radians(float(start_angle) + float(sweep_angle))
        thetam = math.radians(float(start_angle) + float(sweep_angle) / 2.0)
        add_geom_row(shape, geom_ix, 1, "MoveTo", {"X": f"({cx})+({rx})*({math.cos(theta1)})", "Y": f"({cy})+({ry})*({math.sin(theta1)})"})
        add_geom_row(shape, geom_ix, 2, "EllipticalArcTo", {"X": f"({cx})+({rx})*({math.cos(theta2)})", "Y": f"({cy})+({ry})*({math.sin(theta2)})", "A": f"({cx})+({rx})*({math.cos(thetam)})", "B": f"({cy})+({ry})*({math.sin(thetam)})", "C": "0", "D": aspect})


def apply_symbol_command(doc, target, cmd):
    if cmd.get("action") == "recalculate_formula_cache":
        return
    shape = resolve_shape_path(doc, target)
    action = cmd.get("action")
    if action == "update_transform":
        set_cell_formula_value(shape, cmd.get("property"), cmd.get("value"), cmd.get("formula"), cmd.get("unit"), bool(cmd.get("preserve_formula")))
    elif action == "set_shape_cell":
        set_cell_formula_value(shape, cmd_value(cmd, "cell_name", cmd_value(cmd, "property")), cmd_value(cmd, "value", cmd_value(cmd, "val")), cmd.get("formula"), cmd.get("unit"), bool(cmd.get("preserve_formula")))
    elif action == "add_connection_pin":
        ensure_section(shape, "Connection", 0)
        row_ix = shape.AddRow(VIS_SECTION_CONNECTION, VIS_ROW_LAST, VIS_TAG_CONNECTION_POINT)
        for cell_name in ("X", "Y", "DirX", "DirY"):
            cell = shape.CellsSRC(VIS_SECTION_CONNECTION, row_ix, connection_cell_column(cell_name))
            value, formula = connection_command_values(cmd, cell_name)
            set_cell_object_formula_value(cell, value, formula, preserve_formula=bool(cmd.get("preserve_formula")))
    elif action == "delete_connection_pin":
        try:
            shape.DeleteRow(VIS_SECTION_CONNECTION, int(cmd.get("id")))
        except Exception:
            pass
    elif action == "modify_geometry":
        geom_ix = int(cmd_value(cmd, "geom_ix", "0"))
        row_ix = int(cmd_value(cmd, "row_ix", "1"))
        for cell_name in ("X", "Y"):
            prop = cell_name.lower()
            if prop in cmd:
                set_cell_formula_value(shape, f"Geometry{geom_ix + 1}.{cell_name}{row_ix}", cmd[prop], preserve_formula=bool(cmd.get("preserve_formula")))
    elif action == "update_text":
        shape.Text = "" if cmd.get("text") is None else str(cmd.get("text"))
    elif action == "draw_rectangle":
        add_rectangle_geometry(shape, cmd)
    elif action == "draw_line":
        add_line_geometry(shape, cmd)
    elif action == "draw_circle":
        cx = cmd_value(cmd, "cx", "Width*0.5")
        cy = cmd_value(cmd, "cy", "Height*0.5")
        radius = cmd_value(cmd, "r", "Width*0.5")
        add_ellipse_geometry(shape, {"x_min": f"({cx})-({radius})", "y_min": f"({cy})-({radius})", "x_max": f"({cx})+({radius})", "y_max": f"({cy})+({radius})"})
    elif action == "draw_ellipse":
        add_ellipse_geometry(shape, cmd)
    elif action == "draw_elliptical_arc":
        add_ellipse_geometry(shape, cmd, cmd_value(cmd, "start_angle", 0.0), cmd_value(cmd, "sweep_angle", 360.0))
    elif action == "update_shape_user_cell":
        set_user_row(shape, cmd.get("name"), cmd.get("value"), cmd.get("formula"), cmd.get("unit"))
    elif action == "delete_shape_user_cell":
        delete_user_row(shape, cmd.get("name"))
    elif action == "set_section_cell":
        section_name = cmd.get("section")
        section_ix = int(cmd_value(cmd, "section_ix", "0"))
        row_ix = int(cmd_value(cmd, "row_ix", "0"))
        row_name = cmd_value(cmd, "row_name")
        row_type = cmd_value(cmd, "row_type")
        ensure_section_row(shape, section_name, section_ix, row_ix, row_name, row_type)
        if section_name == "Connection":
            cell = shape.CellsSRC(VIS_SECTION_CONNECTION, row_ix, connection_cell_column(cmd.get("cell_name")))
            set_cell_object_formula_value(cell, cmd_value(cmd, "value", cmd_value(cmd, "val")), cmd.get("formula"), cmd.get("unit"), bool(cmd.get("preserve_formula")))
        else:
            cell_name = section_cell_name(section_name, section_ix, row_ix, row_name, cmd.get("cell_name"))
            set_cell_formula_value(shape, cell_name, cmd_value(cmd, "value", cmd_value(cmd, "val")), cmd.get("formula"), cmd.get("unit"), bool(cmd.get("preserve_formula")))
    elif action == "delete_section_row":
        try:
            shape.DeleteRow(section_index(cmd.get("section"), cmd_value(cmd, "section_ix", "0")), int(cmd_value(cmd, "row_ix", "0")))
        except Exception:
            pass
    else:
        raise ValueError(f"Unknown symbol_editor action: {action}")


def apply_settings_command(doc, cmd):
    action = cmd.get("action")
    if action == "update_doc_user_cell":
        set_user_row(doc.DocumentSheet, cmd.get("name"), cmd.get("value"), cmd.get("formula"), cmd.get("unit"))
    elif action == "delete_doc_user_cell":
        delete_user_row(doc.DocumentSheet, cmd.get("name"))
    elif action == "update_page_cell":
        page = find_page(doc, cmd.get("page"))
        set_cell_formula_value(page.PageSheet, cmd.get("property"), cmd.get("value"), cmd.get("formula"), cmd.get("unit"))
    elif action == "update_page_user_cell":
        page = find_page(doc, cmd.get("page"))
        set_user_row(page.PageSheet, cmd.get("name"), cmd.get("value"), cmd.get("formula"), cmd.get("unit"))
    elif action == "delete_page_user_cell":
        page = find_page(doc, cmd.get("page"))
        delete_user_row(page.PageSheet, cmd.get("name"))
    else:
        raise ValueError(f"Unknown doc_page_settings action: {action}")


def delete_shape(shape):
    for method_name in ("DeleteEx", "Delete"):
        try:
            if method_name == "DeleteEx":
                getattr(shape, method_name)(0)
            else:
                getattr(shape, method_name)()
            return
        except Exception:
            pass
    app = shape.Application
    window = app.ActiveWindow
    if window is None:
        app.Visible = True
        window = app.ActiveWindow
    window.DeselectAll()
    window.Select(shape, 2)
    window.Selection.Delete()


def active_window(app):
    window = app.ActiveWindow
    if window is None:
        app.Visible = True
        window = app.ActiveWindow
    return window


def activate_page(page):
    window = active_window(page.Application)
    try:
        window.Page = page
        return window
    except Exception:
        pass
    try:
        page.Activate()
    except Exception:
        pass
    return active_window(page.Application)


def page_ref_from_shape_path(path):
    parts = [part for part in str(path).strip("/").split("/") if part]
    if len(parts) < 4 or parts[0] != "pages" or parts[2] != "shape":
        raise ValueError(
            "selection_shape_paths for saved-file PDF export must point to page shapes, "
            f"got: {path!r}"
        )
    return parts[1]


def prepare_saved_file_selection(doc, shape_paths):
    if not isinstance(shape_paths, (list, tuple)) or not shape_paths:
        raise ValueError("selection_shape_paths must contain at least one page shape path.")
    normalized = [str(path) for path in shape_paths]
    page_ref = page_ref_from_shape_path(normalized[0])
    for path in normalized[1:]:
        if page_ref_from_shape_path(path) != page_ref:
            raise ValueError(
                "selection_shape_paths must all belong to the same page when "
                "exporting from source='saved_file'."
            )
    page = find_page(doc, page_ref)
    window = activate_page(page)
    window.DeselectAll()
    for path in normalized:
        window.Select(resolve_shape_path(doc, path), VIS_SELECT)
    return window


def export_pdf(doc, output_pdf_path, options):
    if not output_pdf_path:
        return
    options = options or {}
    intent = str(options.get("intent", "print")).strip().lower()
    page_range = str(options.get("page_range", "all")).strip().lower()

    if page_range == "current_page":
        page_ref = options.get("page")
        if page_ref:
            activate_page(find_page(doc, page_ref))
    elif page_range == "selection":
        prepare_saved_file_selection(doc, options.get("selection_shape_paths") or [])

    intent_code = VIS_DOC_EX_INTENT_PRINT if intent == "print" else VIS_DOC_EX_INTENT_SCREEN
    range_code = {
        "all": VIS_PRINT_ALL,
        "from_to": VIS_PRINT_FROM_TO,
        "current_page": VIS_PRINT_CURRENT_PAGE,
        "selection": VIS_PRINT_SELECTION,
        "current_view": VIS_PRINT_CURRENT_VIEW,
    }[page_range]

    doc.ExportAsFixedFormat(
        VIS_FIXED_FORMAT_PDF,
        output_pdf_path,
        intent_code,
        range_code,
        int(options.get("from_page", 1)),
        int(options.get("to_page", -1)),
        bool(options.get("color_as_black", False)),
        bool(options.get("include_background", True)),
        bool(options.get("include_document_properties", True)),
        bool(options.get("include_structure_tags", True)),
        bool(options.get("pdfa", False)),
        None,
    )


def ungroup_shape(shape):
    for method_name in ("Ungroup",):
        try:
            getattr(shape, method_name)()
            return
        except Exception:
            pass
    app = shape.Application
    window = active_window(app)
    window.DeselectAll()
    window.Select(shape, 2)
    window.Selection.Ungroup()


def group_shapes(doc, shape_paths):
    if not isinstance(shape_paths, (list, tuple)) or len(shape_paths) < 2:
        raise ValueError("group requires at least two 'shape_paths'.")
    normalized = [str(path) for path in shape_paths]
    if len(set(normalized)) != len(normalized):
        raise ValueError("group does not accept duplicate shape paths.")
    common_parent = parent_shape_path(normalized[0])
    for path in normalized[1:]:
        if parent_shape_path(path) != common_parent:
            raise ValueError("group requires all shapes to share the same direct parent container.")
    shapes = [resolve_shape_path(doc, path) for path in normalized]
    window = active_window(doc.Application)
    window.DeselectAll()
    for shape in shapes:
        window.Select(shape, 2)
    group_shape = window.Selection.Group()
    return common_parent, group_shape


def apply_annotation_command(doc, cmd):
    action = cmd.get("action")
    if action != "add_text_box":
        raise ValueError(f"Unknown test_annotation action: {action}")
    page = find_page(doc, cmd_value(cmd, "page", "Page-1"))
    x = float(cmd_value(cmd, "x", 0.5))
    y = float(cmd_value(cmd, "y", 10.0))
    width = float(cmd_value(cmd, "width", 2.0))
    height = float(cmd_value(cmd, "height", 0.35))
    shape = page.DrawRectangle(x, y, x + width, y - height)
    shape.Text = str(cmd_value(cmd, "text", ""))
    try:
        set_cell_formula_value(shape, "FillForegnd", cmd_value(cmd, "fill", "RGB(245,245,245)"))
        set_cell_formula_value(shape, "LineColor", cmd_value(cmd, "line", "RGB(90,90,90)"))
        set_cell_formula_value(shape, "LineWeight", cmd_value(cmd, "line_weight", "0.5 pt"))
    except Exception:
        pass
    return {"action": "add_text_box", "status": "success", "shape_id": shape.ID}


def apply_instance_command(doc, cmd):
    action = cmd.get("action")
    if action == "add_instance":
        container = resolve_container_path(doc, cmd.get("parent"))
        master = find_master(doc, cmd.get("master"))
        shape = container.Drop(master, float(cmd.get("x")), float(cmd.get("y")))
        if "width" in cmd:
            set_cell_formula_value(shape, "Width", cmd.get("width"))
        if "height" in cmd:
            set_cell_formula_value(shape, "Height", cmd.get("height"))
        set_cell_formula_value(shape, "Angle", cmd_value(cmd, "angle", "0"))
        return {"action": "add_instance", "status": "success", "shape_id": shape.ID}
    if action == "copy_instance":
        source = resolve_shape_path(doc, cmd.get("shape_path"))
        shape = source.Duplicate()
        set_cell_formula_value(shape, "PinX", cmd.get("x"))
        set_cell_formula_value(shape, "PinY", cmd.get("y"))
        return {"action": "copy_instance", "status": "success", "shape_id": shape.ID}
    if action == "delete_instance":
        shape = resolve_shape_path(doc, cmd.get("shape_path"))
        delete_shape(shape)
        return {"action": "delete_instance", "status": "success", "shape_path": cmd.get("shape_path")}
    if action == "ungroup":
        shape = resolve_shape_path(doc, cmd.get("shape_path"))
        moved_children = None
        try:
            moved_children = shape.Shapes.Count
        except Exception:
            pass
        ungroup_shape(shape)
        result = {"action": "ungroup", "status": "success", "shape_path": cmd.get("shape_path")}
        if moved_children is not None:
            result["moved_children"] = int(moved_children)
        return result
    if action == "group":
        parent_path, shape = group_shapes(doc, cmd.get("shape_paths"))
        return {
            "action": "group",
            "status": "success",
            "parent_path": parent_path,
            "shape_id": str(shape.ID),
            "shape_path": f"{parent_path}/shape/{shape.ID}",
            "shape_paths": [str(path) for path in cmd.get("shape_paths", [])],
            "child_count": len(cmd.get("shape_paths", [])),
        }
    raise ValueError(f"Unknown instance_manager action: {action}")


def main() -> int:
    payload = json.load(sys.stdin)

    log_step(payload, "payload_loaded")
    pythoncom.CoInitialize()
    app = None
    app_pid = None
    doc = None
    results = []
    failed = False
    try:
        open_path = payload["file_path"]
        output_path = payload.get("output_path")
        pdf_output_path = payload.get("pdf_output_path")
        pdf_options = payload.get("pdf_options") or {}
        command_groups = payload.get("command_groups", [])

        log_step(payload, "create_app_start")
        app = win32com.client.DispatchEx("Visio.Application")
        app_pid = application_process_id(app)
        app.Visible = bool(payload.get("visible", False))
        log_step(payload, f"create_app_done version={app.Version} pid={app_pid}")
        log_step(payload, f"open_start {open_path}")
        doc = app.Documents.OpenEx(open_path, VIS_OPEN_RW)
        log_step(payload, "open_done")

        for group in command_groups:
            executor = group.get("executor")
            for cmd in group.get("commands", []):
                log_step(payload, f"command_start executor={executor} action={cmd.get('action')} target={group.get('target')}")
                if executor == "symbol_editor":
                    apply_symbol_command(doc, group.get("target"), cmd)
                elif executor == "doc_page_settings":
                    apply_settings_command(doc, cmd)
                elif executor == "instance_manager":
                    result = apply_instance_command(doc, cmd)
                    if result is not None:
                        results.append(result)
                elif executor == "test_annotation":
                    result = apply_annotation_command(doc, cmd)
                    if result is not None:
                        results.append(result)
                else:
                    raise ValueError(f"Unsupported executor: {executor}")
                log_step(payload, f"command_done executor={executor} action={cmd.get('action')}")

        if output_path:
            log_step(payload, f"save_as_start {output_path}")
            doc.SaveAs(output_path)
            log_step(payload, "save_as_done")
        elif command_groups:
            log_step(payload, "save_start")
            doc.Save()
            log_step(payload, "save_done")

        if pdf_output_path:
            log_step(payload, f"export_pdf_start {pdf_output_path}")
            export_pdf(doc, pdf_output_path, pdf_options)
            log_step(payload, "export_pdf_done")

        log_step(payload, "success")
        if pdf_output_path:
            write_result(
                "ok",
                "",
                results,
                action="export_pdf",
                export_status="exported",
                output_pdf_path=pdf_output_path,
                source="saved_file",
            )
        else:
            write_result("ok", "", results)
        return 0
    except Exception as exc:
        failed = True
        log_step(payload, f"error {exc}")
        write_result("error", f"{exc}\n{traceback.format_exc()}", results)
        return 1
    finally:
        if not failed:
            try:
                if doc is not None:
                    doc.Close()
                doc = None
            except Exception:
                pass
            app = None
        terminate_process(app_pid)
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
'''

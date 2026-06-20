"""Visio desktop automation backend.

This module keeps the existing phase-two JSON command shape intact and sends
commands to a Windows Python runner that automates Visio desktop through
``pywin32`` / ``win32com.client``.  It supports two transports:

* macOS + Parallels Desktop: ``prlctl exec <vm> --current-user cmd /c python ...``
* native Windows: local ``python`` execution
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence


DEFAULT_PARALLELS_VM = ""


def _get_default_parallels_vm() -> str:
    """Attempt to dynamically find a running or registered Windows VM via prlctl."""
    prlctl_path = shutil.which("prlctl")
    if not prlctl_path:
        return ""
    
    # 1. Try to find the first running VM
    try:
        output = subprocess.check_output([prlctl_path, "list"], text=True, stderr=subprocess.DEVNULL)
        lines = output.strip().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 4:
                return " ".join(parts[3:])
            elif len(parts) == 3:
                return parts[2]
    except Exception:
        pass

    # 2. Fall back to the first registered VM (even if stopped)
    try:
        output = subprocess.check_output([prlctl_path, "list", "--all"], text=True, stderr=subprocess.DEVNULL)
        lines = output.strip().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 4:
                return " ".join(parts[3:])
            elif len(parts) == 3:
                return parts[2]
    except Exception:
        pass
        
    return ""


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
    stage_local_default = False
    host_artifact_stage_default = False

    def map_path(self, path: str | os.PathLike[str]) -> str:
        raise NotImplementedError

    def artifact_dir(self, host_file: Path) -> Path:
        return host_file.parent

    def run_python_file(
        self,
        script_path: str,
        payload_path: str,
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        raise NotImplementedError


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

    vm_name: str = DEFAULT_PARALLELS_VM
    home: str | os.PathLike[str] | None = None
    prlctl: str = "prlctl"
    current_user: bool = True

    mode: str = "parallels"
    stage_local_default: bool = True
    host_artifact_stage_default: bool = True

    def map_path(self, path: str | os.PathLike[str]) -> str:
        return mac_path_to_parallels_unc(path, home=self.home)

    def artifact_dir(self, host_file: Path) -> Path:
        base_home = Path(self.home).expanduser() if self.home is not None else Path.home()
        return base_home / "Documents" / "visio_bridge_desktop_runs"

    def run_python_file(
        self,
        script_path: str,
        payload_path: str,
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        vm = self.vm_name or _get_default_parallels_vm()
        if not vm:
            raise RuntimeError(
                "Parallels VM name is not specified and could not be auto-detected via prlctl."
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
                f'python "{script_path}" "{payload_path}"',
            ]
        )
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
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
    stage_local_default: bool = False
    host_artifact_stage_default: bool = False

    def map_path(self, path: str | os.PathLike[str]) -> str:
        return str(path)

    def run_python_file(
        self,
        script_path: str,
        payload_path: str,
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            self.python,
            script_path,
            payload_path,
        ]
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
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
        mode = cfg.get("desktop_transport_mode", "auto")
    
    if not vm_name:
        vm_name = cfg.get("vm_name")
    if not vm_name:
        vm_name = _get_default_parallels_vm() or DEFAULT_PARALLELS_VM

    normalized = str(mode).lower()
    if normalized in {"windows", "windows-local", "local"}:
        return LocalWindowsTransport()
    if normalized in {"parallels", "parallels-desktop"}:
        return ParallelsTransport(vm_name=vm_name)
    if normalized != "auto":
        raise ValueError(f"Unsupported desktop transport mode: {mode}")

    if platform.system() == "Windows":
        return LocalWindowsTransport()
    if shutil.which("prlctl"):
        return ParallelsTransport(vm_name=vm_name)
    raise RuntimeError(
        "Could not auto-detect a Visio desktop transport. Install Parallels "
        "Tools/prlctl on macOS or run on Windows."
    )


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
            mode = cfg.get("desktop_transport_mode", "auto")
        
        if not vm_name:
            vm_name = cfg.get("vm_name")
        if not vm_name:
            vm_name = _get_default_parallels_vm() or DEFAULT_PARALLELS_VM

        self.transport = transport or create_default_transport(mode, vm_name=vm_name)
        self.timeout = timeout if timeout is not None else cfg.get("timeout", 180)
        self.visible = visible if visible is not None else cfg.get("visible", False)
        self.keep_artifacts = keep_artifacts
        
        if stage_local is None:
            stage_local = cfg.get("stage_local")
        self.stage_local = (
            getattr(self.transport, "stage_local_default", False)
            if stage_local is None
            else stage_local
        )

    def run(
        self,
        file_path: str | os.PathLike[str],
        command_groups: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        output_path: str | os.PathLike[str] | None = None,
    ) -> DesktopCommandResult:
        host_file = Path(file_path).expanduser()
        host_output = Path(output_path).expanduser() if output_path else None
        artifact_dir_getter = getattr(self.transport, "artifact_dir", None)
        artifact_dir = (
            artifact_dir_getter(host_file)
            if artifact_dir_getter is not None
            else host_file.parent
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        run_id = uuid.uuid4().hex
        script_host = artifact_dir / f".visio_bridge_desktop_{run_id}.py"
        payload_host = artifact_dir / f".visio_bridge_desktop_{run_id}.json"
        log_host = artifact_dir / f".visio_bridge_desktop_{run_id}.log"
        cleanup_paths = [script_host, payload_host]
        if not self.keep_artifacts:
            cleanup_paths.append(log_host)

        payload_input_host = host_file
        payload_output_host = host_output
        host_copyback_source: Path | None = None
        host_copyback_dest: Path | None = None
        if getattr(self.transport, "host_artifact_stage_default", False):
            input_ext = host_file.suffix or ".vsdx"
            staged_input = artifact_dir / f"visio_bridge_input_{run_id}{input_ext}"
            shutil.copy2(host_file, staged_input)
            cleanup_paths.append(staged_input)
            payload_input_host = staged_input

            if host_output is not None:
                output_ext = host_output.suffix or input_ext
                staged_output = artifact_dir / f"visio_bridge_output_{run_id}{output_ext}"
                cleanup_paths.append(staged_output)
                payload_output_host = staged_output
                host_copyback_source = staged_output
                host_copyback_dest = host_output
            else:
                payload_output_host = None
                host_copyback_source = staged_input
                host_copyback_dest = host_file

        payload = {
            "file_path": self.transport.map_path(payload_input_host),
            "output_path": (
                self.transport.map_path(payload_output_host) if payload_output_host else None
            ),
            "visible": self.visible,
            "stage_local": self.stage_local,
            "log_path": self.transport.map_path(log_host),
            "command_groups": _normalize_command_groups(command_groups),
        }

        script_host.write_text(PYTHON_RUNNER, encoding="utf-8")
        payload_host.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        try:
            try:
                completed = self.transport.run_python_file(
                    self.transport.map_path(script_host),
                    self.transport.map_path(payload_host),
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as exc:
                log_text = _read_text_if_exists(log_host)
                raise RuntimeError(
                    f"Visio desktop command timed out after {self.timeout} seconds.\n"
                    f"Runner log:\n{log_text or '(no runner log written)'}"
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
            if host_copyback_source is not None and host_copyback_dest is not None:
                shutil.copy2(host_copyback_source, host_copyback_dest)
            return DesktopCommandResult(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                data=data,
            )
        finally:
            if not self.keep_artifacts:
                for path in cleanup_paths:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass


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


def _read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def apply_desktop_command_groups(
    file_path: str | os.PathLike[str],
    command_groups: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    output_path: str | os.PathLike[str] | None = None,
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
    return runner.run(file_path, command_groups, output_path=output_path)


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
import shutil
import subprocess
import sys
import tempfile
import traceback
import uuid
from datetime import datetime
from pathlib import Path

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


def log_step(payload: dict, message: str) -> None:
    log_path = payload.get("log_path")
    if not log_path:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception:
        pass


def write_result(status: str, message: str = "", results: list | None = None) -> None:
    print(
        json.dumps({"status": status, "message": message, "results": results or []}, ensure_ascii=False),
        flush=True,
    )


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
    raise ValueError(f"Unknown instance_manager action: {action}")


def main() -> int:
    if len(sys.argv) != 2:
        write_result("error", "Usage: runner.py <payload.json>")
        return 2
    payload_path = sys.argv[1]
    with open(payload_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    log_step(payload, "payload_loaded")
    pythoncom.CoInitialize()
    app = None
    app_pid = None
    doc = None
    results = []
    local_input = None
    local_output = None
    failed = False
    try:
        open_path = payload["file_path"]
        output_path = payload.get("output_path")
        if payload.get("stage_local"):
            input_ext = os.path.splitext(open_path)[1] or ".vsdx"
            local_input = os.path.join(tempfile.gettempdir(), f"visio_bridge_in_{uuid.uuid4().hex}{input_ext}")
            log_step(payload, f"copy_input_start {open_path} -> {local_input}")
            shutil.copy2(open_path, local_input)
            log_step(payload, f"copy_input_done {local_input}")
            open_path = local_input
            output_ext = os.path.splitext(output_path or payload["file_path"])[1] or input_ext
            local_output = os.path.join(tempfile.gettempdir(), f"visio_bridge_out_{uuid.uuid4().hex}{output_ext}")

        log_step(payload, "create_app_start")
        app = win32com.client.DispatchEx("Visio.Application")
        app_pid = application_process_id(app)
        app.Visible = bool(payload.get("visible", False))
        log_step(payload, f"create_app_done version={app.Version} pid={app_pid}")
        log_step(payload, f"open_start {open_path}")
        doc = app.Documents.OpenEx(open_path, VIS_OPEN_RW)
        log_step(payload, "open_done")

        for group in payload.get("command_groups", []):
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

        if payload.get("stage_local"):
            if output_path:
                log_step(payload, f"save_as_start {local_output}")
                doc.SaveAs(local_output)
                log_step(payload, "save_as_done")
                copy_source = local_output
                copy_dest = output_path
            else:
                log_step(payload, "save_start")
                doc.Save()
                log_step(payload, "save_done")
                copy_source = local_input
                copy_dest = payload["file_path"]
            log_step(payload, "close_start")
            doc.Close()
            doc = None
            log_step(payload, f"copy_output_start {copy_source} -> {copy_dest}")
            shutil.copy2(copy_source, copy_dest)
            log_step(payload, "copy_output_done")
        elif output_path:
            log_step(payload, f"save_as_start {output_path}")
            doc.SaveAs(output_path)
            log_step(payload, "save_as_done")
        else:
            log_step(payload, "save_start")
            doc.Save()
            log_step(payload, "save_done")

        log_step(payload, "success")
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
        for path in (local_input, local_output):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
'''

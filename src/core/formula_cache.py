"""Scoped ShapeSheet formula-cache recalculation.

This module evaluates a safe numeric subset of Visio ShapeSheet formulas and
updates cached ``V`` attributes only inside an explicit write scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import xml.etree.ElementTree as ET

from .bridge import MasterInfo, VisioBridge
from .locator import resolve_path
from .xml_utils import find_child, get_section, local, q


MAX_ITERATIONS = 8
ABS_TOL = 1e-12
REL_TOL = 1e-9

_LOCAL_CELL_NAMES = {
    "Width",
    "Height",
    "PinX",
    "PinY",
    "LocPinX",
    "LocPinY",
    "BeginX",
    "BeginY",
    "EndX",
    "EndY",
    "Angle",
    "FlipX",
    "FlipY",
}
_SKIP_FORMULAS = {"inh", "no formula"}
_SKIP_FUNCTIONS = (
    "THEMEVAL",
    "THEMEGUARD",
    "TEXTWIDTH",
    "TEXTHEIGHT",
    "LOOKUP",
    "DEPENDSON",
    "SETF",
    "SETATREF",
    "RGB",
)


@dataclass
class FormulaCacheWarning:
    cell: str
    formula: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"cell": self.cell, "formula": self.formula, "reason": self.reason}


@dataclass
class FormulaCacheResult:
    target: str
    scope: str
    updated_cells: list[str] = field(default_factory=list)
    computed_cells: dict[str, str] = field(default_factory=dict)
    skipped_cells: list[str] = field(default_factory=list)
    warnings: list[FormulaCacheWarning] = field(default_factory=list)
    modified_parts: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "scope": self.scope,
            "updated_cells": list(self.updated_cells),
            "computed_cells": dict(self.computed_cells),
            "skipped_cells": list(self.skipped_cells),
            "warnings": [w.to_dict() for w in self.warnings],
            "modified_parts": sorted(self.modified_parts),
        }


@dataclass
class _CellRecord:
    key: str
    owner_id: str
    name: str
    element: ET.Element
    part: str
    writable: bool
    inherited: bool = False
    materialize_shape: ET.Element | None = None
    cell_kind: str = "top"
    cell_n: str = ""
    user_row_name: str = ""
    section_attrs: dict[str, str] = field(default_factory=dict)
    row_attrs: dict[str, str] = field(default_factory=dict)

    @property
    def formula(self) -> str | None:
        return self.element.get("F")

    @property
    def value(self) -> str | None:
        return self.element.get("V")


@dataclass
class _ScopeData:
    target: str
    scope: str
    records: list[_CellRecord]
    writable_parts: set[str]
    shape_ids: set[str]
    root_shape_id: str
    master_to_instance: dict[str, str] = field(default_factory=dict)


class _FormulaNotReady(Exception):
    pass


class _FormulaUnsupported(Exception):
    pass


def recalculate_formula_cache(
    bridge: VisioBridge,
    target: str,
    scope: str,
    abs_tol: float = ABS_TOL,
    rel_tol: float = REL_TOL,
    max_iterations: int = MAX_ITERATIONS,
    materialize_inherited: bool = True,
) -> FormulaCacheResult:
    """Recalculate formula-driven cached values within a master or instance.

    In instance scope, ``materialize_inherited`` defaults to true to mirror
    Visio's save behavior: inherited formulas affected by local overrides are
    written into the instance subtree as effective cache cells with ``F="Inh"``
    and the computed ``V``. This is cache materialization, not a local formula
    override; the master formula is not copied.
    """
    if scope not in {"master", "instance"}:
        raise ValueError(f"Unsupported formula-cache scope: {scope}")

    result = FormulaCacheResult(target=target, scope=scope)
    data = _build_scope(bridge, target, scope)
    values = _initial_values(data.records)
    tainted = _initial_tainted(data.records, data)
    candidates = _effective_formula_records(data.records)

    unresolved: dict[str, str] = {}
    for _ in range(max_iterations):
        changed = False
        unresolved.clear()
        for record in candidates:
            formula = record.formula or ""
            skip_reason = _skip_reason(formula)
            if skip_reason:
                result.skipped_cells.append(record.key)
                continue
            try:
                value = _eval_formula(formula, record.owner_id, values, data, bridge)
            except _FormulaNotReady as exc:
                unresolved[record.key] = str(exc)
                continue
            except _FormulaUnsupported as exc:
                unresolved[record.key] = str(exc)
                continue

            current = values.setdefault(record.owner_id, {}).get(record.name)
            deps = _formula_dependencies(formula, record.owner_id, data)
            is_tainted = any(dep in tainted for dep in deps)
            if current is None or not _close(current, value, abs_tol, rel_tol):
                values[record.owner_id][record.name] = value
                changed = True
            if is_tainted and (record.owner_id, record.name) not in tainted:
                tainted.add((record.owner_id, record.name))
                changed = True
        if not changed:
            break
    else:
        for record in candidates:
            if record.formula:
                result.warnings.append(
                    FormulaCacheWarning(record.key, record.formula, "Formula did not converge")
                )

    for record in candidates:
        if record.key in unresolved and record.formula:
            result.warnings.append(
                FormulaCacheWarning(record.key, record.formula, unresolved[record.key])
            )

    seen_skipped = set()
    result.skipped_cells = [
        key for key in result.skipped_cells if not (key in seen_skipped or seen_skipped.add(key))
    ]

    for record in data.records:
        if not record.formula:
            continue
        if _skip_reason(record.formula):
            continue
        new_value = values.get(record.owner_id, {}).get(record.name)
        if new_value is None:
            continue
        if not record.writable:
            result.computed_cells[record.key] = format(new_value, ".16g")
        old_value = _float_or_none(record.value)
        if record.writable:
            if old_value is not None and _close(old_value, new_value, abs_tol, rel_tol):
                continue
            record.element.set("V", format(new_value, ".16g"))
            result.updated_cells.append(record.key)
            result.modified_parts.add(record.part)
            continue

        if not materialize_inherited:
            continue
        if not _should_materialize_inherited(record, tainted):
            continue
        local_cell = _materialize_instance_cell(record)
        if local_cell is None:
            continue
        local_cell.set("F", "Inh")
        local_cell.set("V", format(new_value, ".16g"))
        if record.element.get("U") is not None:
            local_cell.set("U", record.element.get("U", ""))
        result.updated_cells.append(record.key)
        result.modified_parts.add(record.part)

    for part in result.modified_parts:
        bridge.mark_modified(part)
    return result


def eval_formula_for_cache(
    formula: str,
    shape_id: str,
    evaluated: dict[str, dict[str, float]],
    root_id: str,
    doc_users: dict[str, str] | None = None,
) -> float | None:
    """Compatibility helper used by older tests and callers."""
    bridge = _DocUserBridge(doc_users or {})
    data = _ScopeData(
        target="compat",
        scope="master",
        records=[],
        writable_parts=set(),
        shape_ids=set(evaluated),
        root_shape_id=root_id,
    )
    try:
        return _eval_formula(formula, shape_id, evaluated, data, bridge)  # type: ignore[arg-type]
    except (_FormulaNotReady, _FormulaUnsupported):
        return None


class _DocUserBridge:
    def __init__(self, doc_users: dict[str, str]):
        self.doc_users = doc_users

    def get_xml(self, path: str) -> ET.ElementTree | None:
        return None


def _build_scope(bridge: VisioBridge, target: str, scope: str) -> _ScopeData:
    if scope == "master":
        return _build_master_scope(bridge, target)
    return _build_instance_scope(bridge, target)


def _build_master_scope(bridge: VisioBridge, target: str) -> _ScopeData:
    parts = [p for p in target.strip("/").split("/") if p]
    if len(parts) < 2 or parts[0] != "masters":
        raise ValueError(f"Master scope target must start with masters/<master>: {target}")
    info = _find_master_info(bridge, parts[1])
    if info is None:
        raise ValueError(f"Could not resolve master target: {target}")
    master_tree = bridge.get_xml(info.xml_path)
    if master_tree is None:
        raise ValueError(f"Could not load master XML: {info.xml_path}")
    shapes = _iter_shapes(master_tree.getroot())
    root_shape_id = shapes[0].get("ID", "") if shapes else ""

    records: list[_CellRecord] = []
    for shape in shapes:
        records.extend(_collect_shape_records(shape, shape.get("ID", ""), info.xml_path, True))

    masters_tree = bridge.get_xml("visio/masters/masters.xml")
    if masters_tree is not None:
        master_elem = _find_master_element(masters_tree, info)
        if master_elem is not None:
            page_sheet = find_child(master_elem, "PageSheet")
            if page_sheet is not None:
                records.extend(
                    _collect_container_cells(
                        page_sheet,
                        f"master:{info.master_id}/pagesheet",
                        "__pagesheet__",
                        "visio/masters/masters.xml",
                        True,
                        None,
                    )
                )

    return _ScopeData(
        target=target,
        scope="master",
        records=records,
        writable_parts={info.xml_path, "visio/masters/masters.xml"},
        shape_ids={s.get("ID", "") for s in shapes if s.get("ID")},
        root_shape_id=root_shape_id,
    )


def _build_instance_scope(bridge: VisioBridge, target: str) -> _ScopeData:
    parts = [p for p in target.strip("/").split("/") if p]
    if len(parts) < 4 or parts[0] != "pages" or parts[2] != "shape":
        raise ValueError(f"Instance scope target must be pages/<page>/shape/<id>: {target}")
    resolved = resolve_path(bridge, target)
    if resolved is None:
        raise ValueError(f"Could not resolve instance target: {target}")
    root_shape, page_part = resolved
    if local(root_shape.tag) != "Shape":
        raise ValueError(f"Instance target is not a Shape: {target}")

    records: list[_CellRecord] = []
    instance_shapes = _iter_shapes(root_shape)
    owned_keys: set[tuple[str, str]] = set()
    for shape in instance_shapes:
        owner_id = shape.get("ID", "")
        owned = _collect_shape_records(shape, owner_id, page_part, True)
        records.extend(owned)
        owned_keys.update((record.owner_id, record.name) for record in owned)

    master_to_instance: dict[str, str] = {}
    inherited = _collect_instance_inherited_records(bridge, root_shape, page_part, owned_keys, master_to_instance)
    records.extend(inherited)

    return _ScopeData(
        target=target,
        scope="instance",
        records=records,
        writable_parts={page_part},
        shape_ids={s.get("ID", "") for s in instance_shapes if s.get("ID")},
        root_shape_id=root_shape.get("ID", ""),
        master_to_instance=master_to_instance,
    )


def _collect_instance_inherited_records(
    bridge: VisioBridge,
    instance_root: ET.Element,
    page_part: str,
    owned_keys: set[tuple[str, str]],
    master_to_instance: dict[str, str],
) -> list[_CellRecord]:
    master_id = instance_root.get("Master")
    info = _find_master_info(bridge, master_id or "")
    if info is None:
        return []
    master_tree = bridge.get_xml(info.xml_path)
    if master_tree is None:
        return []
    master_shapes = _iter_shapes(master_tree.getroot())
    if not master_shapes:
        return []
    by_master_shape_id = {shape.get("ID", ""): shape for shape in master_shapes if shape.get("ID")}
    records: list[_CellRecord] = []

    instance_shapes = _iter_shapes(instance_root)
    for index, instance_shape in enumerate(instance_shapes):
        instance_id = instance_shape.get("ID", "")
        if not instance_id:
            continue
        if index == 0:
            master_shape = master_shapes[0]
        else:
            master_shape = by_master_shape_id.get(instance_shape.get("MasterShape", ""))
        if master_shape is None:
            continue
        master_shape_id = master_shape.get("ID", "")
        if master_shape_id:
            master_to_instance[master_shape_id] = instance_id
        inherited = _collect_shape_records(
            master_shape,
            instance_id,
            page_part,
            False,
            materialize_shape=instance_shape,
        )
        for record in inherited:
            if (record.owner_id, record.name) in owned_keys:
                continue
            record.inherited = True
            record.key = record.key.replace("shape:", "inherited-shape:", 1)
            records.append(record)
    return records


def _find_master_info(bridge: VisioBridge, ref: str) -> MasterInfo | None:
    for info in bridge.masters:
        if info.master_id == ref or info.name_u == ref or info.name == ref:
            return info
    return None


def _find_master_element(tree: ET.ElementTree, info: MasterInfo) -> ET.Element | None:
    for master in tree.getroot():
        if local(master.tag) != "Master":
            continue
        if (
            master.get("ID") == info.master_id
            or master.get("NameU") == info.name_u
            or master.get("Name") == info.name
        ):
            return master
    return None


def _iter_shapes(elem: ET.Element) -> list[ET.Element]:
    result: list[ET.Element] = []
    if local(elem.tag) == "Shape":
        result.append(elem)
    for child in elem:
        result.extend(_iter_shapes(child))
    return result


def _collect_shape_records(
    shape: ET.Element,
    owner_id: str,
    part: str,
    writable: bool,
    materialize_shape: ET.Element | None = None,
) -> list[_CellRecord]:
    records: list[_CellRecord] = []
    if not owner_id:
        return records
    prefix = f"shape:{owner_id}"
    records.extend(_collect_container_cells(shape, prefix, owner_id, part, writable, materialize_shape))

    user_section = get_section(shape, "User")
    if user_section is not None:
        for row in user_section:
            if local(row.tag) != "Row" or not row.get("N"):
                continue
            value_cell = find_child(row, "Cell", N="Value")
            if value_cell is None:
                continue
            name = f"User.{row.get('N')}"
            records.append(
                _CellRecord(
                    key=f"{prefix}/user:{row.get('N')}/cell:Value",
                    owner_id=owner_id,
                    name=name,
                    element=value_cell,
                    part=part,
                    writable=writable,
                    materialize_shape=materialize_shape,
                    cell_kind="user",
                    cell_n="Value",
                    user_row_name=row.get("N", ""),
                )
            )

    for section in shape:
        if local(section.tag) != "Section" or section.get("N") == "User":
            continue
        section_name = section.get("N", "")
        section_ix = section.get("IX", "")
        for row in section:
            if local(row.tag) != "Row":
                continue
            row_id = row.get("IX") or row.get("N") or row.get("T") or ""
            for cell in row:
                if local(cell.tag) != "Cell" or not cell.get("N"):
                    continue
                cell_name = cell.get("N", "")
                name = f"{section_name}.{section_ix}.{row_id}.{cell_name}"
                records.append(
                    _CellRecord(
                        key=f"{prefix}/section:{section_name}:{section_ix}/row:{row_id}/cell:{cell_name}",
                        owner_id=owner_id,
                        name=name,
                        element=cell,
                        part=part,
                        writable=writable,
                        materialize_shape=materialize_shape,
                        cell_kind="section",
                        cell_n=cell_name,
                        section_attrs=dict(section.attrib),
                        row_attrs=dict(row.attrib),
                    )
                )
    return records


def _collect_container_cells(
    elem: ET.Element,
    prefix: str,
    owner_id: str,
    part: str,
    writable: bool,
    materialize_shape: ET.Element | None = None,
) -> list[_CellRecord]:
    records: list[_CellRecord] = []
    for child in elem:
        if local(child.tag) != "Cell" or not child.get("N"):
            continue
        name = child.get("N", "")
        records.append(
            _CellRecord(
                key=f"{prefix}/cell:{name}",
                owner_id=owner_id,
                name=name,
                element=child,
                part=part,
                writable=writable,
                materialize_shape=materialize_shape,
                cell_kind="top",
                cell_n=name,
            )
        )
    return records


def _initial_values(records: list[_CellRecord]) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for record in records:
        value = _float_or_none(record.value)
        if value is None:
            continue
        bucket = values.setdefault(record.owner_id, {})
        if record.name not in bucket or record.writable:
            bucket[record.name] = value
    return values


def _initial_tainted(records: list[_CellRecord], data: _ScopeData) -> set[tuple[str, str]]:
    if data.scope != "instance":
        return set()
    return {
        (record.owner_id, record.name)
        for record in records
        if record.writable and not record.inherited
    }


def _effective_formula_records(records: list[_CellRecord]) -> list[_CellRecord]:
    seen: set[tuple[str, str]] = set()
    ordered: list[_CellRecord] = []
    for record in sorted(records, key=lambda rec: (rec.inherited, rec.key)):
        identity = (record.owner_id, record.name)
        if identity in seen:
            continue
        seen.add(identity)
        if record.formula:
            ordered.append(record)
    return ordered


def _skip_reason(formula: str) -> str | None:
    stripped = formula.strip()
    if stripped.lower() in _SKIP_FORMULAS:
        return stripped
    upper = stripped.upper()
    for fn in _SKIP_FUNCTIONS:
        if re.search(rf"\b{fn}\s*\(", upper):
            return f"Unsupported ShapeSheet function: {fn}"
    return None


def _should_materialize_inherited(
    record: _CellRecord,
    tainted: set[tuple[str, str]],
) -> bool:
    if not record.inherited or record.materialize_shape is None:
        return False
    if not record.formula or _skip_reason(record.formula):
        return False
    return (record.owner_id, record.name) in tainted


def _materialize_instance_cell(record: _CellRecord) -> ET.Element | None:
    shape = record.materialize_shape
    if shape is None:
        return None
    if record.cell_kind == "top":
        return _ensure_cell(shape, record.cell_n)
    if record.cell_kind == "user":
        section = _ensure_section(shape, {"N": "User"})
        row = _ensure_row(section, {"N": record.user_row_name})
        return _ensure_cell(row, record.cell_n)
    if record.cell_kind == "section":
        section = _ensure_section(shape, _section_identity(record.section_attrs))
        row = _ensure_row(section, record.row_attrs)
        return _ensure_cell(row, record.cell_n)
    return None


def _section_identity(attrs: dict[str, str]) -> dict[str, str]:
    identity = {"N": attrs.get("N", "")}
    if attrs.get("IX") is not None:
        identity["IX"] = attrs.get("IX", "")
    return identity


def _ensure_section(shape: ET.Element, attrs: dict[str, str]) -> ET.Element:
    name = attrs.get("N", "")
    ix = attrs.get("IX")
    for child in shape:
        if local(child.tag) != "Section" or child.get("N") != name:
            continue
        if ix is None or child.get("IX") == ix:
            return child
    section = ET.SubElement(shape, q("Section"))
    for key, value in attrs.items():
        if value:
            section.set(key, value)
    return section


def _ensure_row(section: ET.Element, attrs: dict[str, str]) -> ET.Element:
    for row in section:
        if local(row.tag) != "Row":
            continue
        if attrs.get("N") and row.get("N") == attrs.get("N"):
            return row
        if attrs.get("IX") and row.get("IX") == attrs.get("IX"):
            return row
        if not attrs.get("N") and not attrs.get("IX") and attrs.get("T") and row.get("T") == attrs.get("T"):
            return row
    row = ET.SubElement(section, q("Row"))
    for key, value in attrs.items():
        if value:
            row.set(key, value)
    return row


def _ensure_cell(parent: ET.Element, name: str) -> ET.Element:
    cell = find_child(parent, "Cell", N=name)
    if cell is not None:
        return cell
    return ET.SubElement(parent, q("Cell"), {"N": name})


def _formula_dependencies(
    formula: str,
    owner_id: str,
    data: _ScopeData,
) -> set[tuple[str, str]]:
    deps: set[tuple[str, str]] = set()

    for match in re.finditer(r"\bSheet\.(\d+)!([A-Za-z_][A-Za-z0-9_.]*)\b", formula):
        ref_id = match.group(1)
        prop = match.group(2)
        if data.scope == "instance" and ref_id in data.master_to_instance:
            ref_id = data.master_to_instance[ref_id]
        if ref_id in data.shape_ids:
            deps.add((ref_id, prop))

    for match in re.finditer(r"\bUser\.([A-Za-z_][A-Za-z0-9_]*)\b", formula):
        key = f"User.{match.group(1)}"
        deps.add((owner_id, key))
        if data.root_shape_id != owner_id:
            deps.add((data.root_shape_id, key))

    formula_without_refs = re.sub(r"\bSheet\.\d+![A-Za-z_][A-Za-z0-9_.]*\b", " ", formula)
    formula_without_refs = re.sub(r"\b(?:TheDoc!)?User\.[A-Za-z_][A-Za-z0-9_]*\b", " ", formula_without_refs)
    for name in _LOCAL_CELL_NAMES:
        if re.search(rf"\b{name}\b", formula_without_refs):
            deps.add((owner_id, name))
    return deps


def _eval_formula(
    formula: str,
    owner_id: str,
    values: dict[str, dict[str, float]],
    data: _ScopeData,
    bridge: VisioBridge | _DocUserBridge,
) -> float:
    if not formula:
        raise _FormulaUnsupported("Empty formula")
    skip = _skip_reason(formula)
    if skip:
        raise _FormulaUnsupported(skip)

    expr = _unwrap_guard(formula)
    expr = _replace_units(expr)
    expr = expr.replace("^", "**")
    expr = _replace_functions(expr)
    expr = _replace_doc_users(expr, bridge)
    expr = _replace_sheet_refs(expr, values, data)
    expr = _replace_user_refs(expr, owner_id, values, data, bridge)
    expr = _replace_local_refs(expr, owner_id, values)
    _assert_safe_expression(expr)
    try:
        return float(eval(expr, {"__builtins__": None}, {"math": math, "min": min, "max": max, "abs": abs}))  # noqa: S307
    except ZeroDivisionError as exc:
        raise _FormulaUnsupported("Division by zero") from exc
    except Exception as exc:
        raise _FormulaUnsupported("Unsupported expression") from exc


def _unwrap_guard(expr: str) -> str:
    while True:
        match = re.fullmatch(r"\s*GUARD\((.*)\)\s*", expr, flags=re.IGNORECASE)
        if match is None:
            return expr
        expr = match.group(1)


def _replace_units(expr: str) -> str:
    number = r"(?<![\w.])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"

    def repl(match: re.Match) -> str:
        value = match.group(1)
        unit = match.group(2).upper()
        if unit == "DEG":
            return f"({value} * math.pi / 180)"
        if unit == "MM":
            return f"({value} / 25.4)"
        if unit == "PT":
            return f"({value} / 72)"
        return value

    return re.sub(number + r"\s*(DEG|MM|PT|IN|DL|DT)\b", repl, expr, flags=re.IGNORECASE)


def _replace_functions(expr: str) -> str:
    replacements = {
        "SQRT": "math.sqrt",
        "ATAN2": "math.atan2",
        "SIN": "math.sin",
        "COS": "math.cos",
        "MIN": "min",
        "MAX": "max",
        "ABS": "abs",
    }
    for name, replacement in replacements.items():
        expr = re.sub(rf"\b{name}\s*\(", replacement + "(", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bTRUE\b", "1", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bFALSE\b", "0", expr, flags=re.IGNORECASE)
    return expr


def _replace_doc_users(expr: str, bridge: VisioBridge | _DocUserBridge) -> str:
    doc_users = _get_doc_users(bridge)

    def repl(match: re.Match) -> str:
        name = match.group(1)
        value = _float_or_none(doc_users.get(name))
        if value is None:
            raise _FormulaNotReady(f"Missing document User.{name}")
        return str(value)

    return re.sub(r"\bTheDoc!User\.([A-Za-z_][A-Za-z0-9_]*)\b", repl, expr)


def _replace_sheet_refs(
    expr: str,
    values: dict[str, dict[str, float]],
    data: _ScopeData,
) -> str:
    def repl(match: re.Match) -> str:
        ref_id = match.group(1)
        prop = match.group(2)
        if data.scope == "instance" and ref_id in data.master_to_instance:
            ref_id = data.master_to_instance[ref_id]
        if ref_id not in data.shape_ids:
            raise _FormulaUnsupported(f"Sheet.{match.group(1)} is outside current {data.scope} scope")
        value = values.get(ref_id, {}).get(prop)
        if value is None:
            raise _FormulaNotReady(f"Missing dependency Sheet.{ref_id}!{prop}")
        return str(value)

    return re.sub(r"\bSheet\.(\d+)!([A-Za-z_][A-Za-z0-9_.]*)\b", repl, expr)


def _replace_user_refs(
    expr: str,
    owner_id: str,
    values: dict[str, dict[str, float]],
    data: _ScopeData,
    bridge: VisioBridge | _DocUserBridge,
) -> str:
    doc_users = _get_doc_users(bridge)

    def repl(match: re.Match) -> str:
        name = match.group(1)
        key = f"User.{name}"
        value = values.get(owner_id, {}).get(key)
        if value is None and data.root_shape_id != owner_id:
            value = values.get(data.root_shape_id, {}).get(key)
        if value is None:
            value = _float_or_none(doc_users.get(name))
        if value is None:
            raise _FormulaNotReady(f"Missing User.{name}")
        return str(value)

    return re.sub(r"\bUser\.([A-Za-z_][A-Za-z0-9_]*)\b", repl, expr)


def _replace_local_refs(
    expr: str,
    owner_id: str,
    values: dict[str, dict[str, float]],
) -> str:
    bucket = values.get(owner_id, {})
    for name in sorted(_LOCAL_CELL_NAMES, key=len, reverse=True):
        if not re.search(rf"\b{name}\b", expr):
            continue
        value = bucket.get(name)
        if value is None:
            raise _FormulaNotReady(f"Missing local {name}")
        expr = re.sub(rf"\b{name}\b", str(value), expr)
    return expr


def _assert_safe_expression(expr: str) -> None:
    allowed = {"math", "sqrt", "atan2", "sin", "cos", "min", "max", "abs", "pi", "e"}
    for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expr):
        if word not in allowed:
            raise _FormulaUnsupported(f"Unsupported identifier: {word}")


def _get_doc_users(bridge: VisioBridge | _DocUserBridge) -> dict[str, str]:
    if isinstance(bridge, _DocUserBridge):
        return bridge.doc_users
    doc_tree = bridge.get_xml("visio/document.xml")
    if doc_tree is None:
        return {}
    doc_sheet = find_child(doc_tree.getroot(), "DocumentSheet")
    if doc_sheet is None:
        return {}
    user_section = get_section(doc_sheet, "User")
    if user_section is None:
        return {}
    values: dict[str, str] = {}
    for row in user_section:
        if local(row.tag) != "Row" or not row.get("N"):
            continue
        value_cell = find_child(row, "Cell", N="Value")
        if value_cell is not None and value_cell.get("V") is not None:
            values[row.get("N", "")] = value_cell.get("V", "")
    return values


def _float_or_none(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(left: float, right: float, abs_tol: float, rel_tol: float) -> bool:
    return abs(left - right) <= max(abs_tol, rel_tol * max(abs(left), abs(right)))

"""SKILL interface implementation to extract clean JSON formats and apply AI-generated commands for symbol editing."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from ..core.bridge import VisioBridge
from ..core.locator import ElementLocator, resolve_path
from ..core.xml_utils import get_cell, set_cell, get_section, ensure_section, find_child, local, q, set_user_row, ensure_child
from ..core.formula_cache import eval_formula_for_cache, recalculate_formula_cache
from ..desktop import apply_skill_commands_desktop
from .backend import save_xml_fallback_if_requested, try_desktop_backend

def extract_cells(shape: ET.Element, names: list[str]) -> dict[str, dict[str, str]]:
    """Extract cell values and formulas into a dict."""
    res = {}
    for name in names:
        cell = get_cell(shape, name)
        if cell is not None:
            c_data = {}
            if cell.get("V") is not None:
                c_data["val"] = cell.get("V")
            if cell.get("F") is not None:
                c_data["formula"] = cell.get("F")
            if cell.get("U") is not None:
                c_data["unit"] = cell.get("U")
            if c_data:
                res[name] = c_data
    return res

def extract_connections(shape: ET.Element) -> list[dict[str, str]]:
    """Extract all connection points (pins)."""
    conn_sec = get_section(shape, "Connection")
    if conn_sec is None:
        return []
    
    connections = []
    for row in conn_sec:
        if local(row.tag) != "Row":
            continue
        
        row_id = row.get("IX") or row.get("N") or ""
        conn_data = {"id": row_id}
        
        for cell in row:
            if local(cell.tag) == "Cell":
                name = cell.get("N")
                if name in ("X", "Y", "DirX", "DirY"):
                    formula = cell.get("F")
                    if formula and formula != "No Formula":
                        conn_data[name] = cell.get("F")
                    else:
                        conn_data[name] = cell.get("V", "0")
        connections.append(conn_data)
    return connections

def extract_geometry(shape: ET.Element) -> list[dict]:
    """Extract geometry sections."""
    geoms = []
    # A shape can have multiple Geometry sections (IX="0", IX="1", etc.)
    for child in shape:
        if local(child.tag) == "Section" and child.get("N") == "Geometry":
            geom_data = {
                "ix": child.get("IX", "0"),
                "rows": []
            }
            for row in child:
                if local(row.tag) != "Row":
                    continue
                row_type = row.get("T", "LineTo")
                row_ix = row.get("IX", "")
                row_data = {"type": row_type, "ix": row_ix}
                for cell in row:
                    if local(cell.tag) == "Cell":
                        name = cell.get("N")
                        if cell.get("F"):
                            row_data[name] = cell.get("F")
                        else:
                            row_data[name] = cell.get("V", "0")
                geom_data["rows"].append(row_data)
            geoms.append(geom_data)
    return geoms

def extract_generic_sections(shape: ET.Element) -> list[dict]:
    """Extract all Section elements generically from a shape."""
    sections = []
    for child in shape:
        if local(child.tag) == "Section":
            sec_data = {
                "name": child.get("N", ""),
                "ix": child.get("IX", "0"),
                "rows": []
            }
            for row in child:
                if local(row.tag) != "Row":
                    continue
                row_data = {
                    "n": row.get("N", ""),
                    "ix": row.get("IX", ""),
                    "cells": {}
                }
                if row.get("T") is not None:
                    row_data["t"] = row.get("T")
                for cell in row:
                    if local(cell.tag) == "Cell":
                        cell_name = cell.get("N", "")
                        c_data = {}
                        if cell.get("V") is not None:
                            c_data["val"] = cell.get("V")
                        if cell.get("F") is not None:
                            c_data["formula"] = cell.get("F")
                        if cell.get("U") is not None:
                            c_data["unit"] = cell.get("U")
                        if cell_name:
                            row_data["cells"][cell_name] = c_data
                sec_data["rows"].append(row_data)
            sections.append(sec_data)
    return sections

def to_skill(shape: ET.Element) -> dict:
    """Convert a shape Element to the simplified AI-readable SKILL structure."""
    if local(shape.tag) != "Shape":
        raise ValueError("Root element must be a Shape")

    transform_cells = ["Width", "Height", "PinX", "PinY", "LocPinX", "LocPinY", "Angle", "FlipX", "FlipY"]
    
    skill_data = {
        "id": shape.get("ID"),
        "name": shape.get("NameU") or shape.get("Name") or "",
        "type": shape.get("Type", "Shape"),
        "transform": extract_cells(shape, transform_cells),
        "connections": extract_connections(shape),
        "geometry": extract_geometry(shape),
        "sections": extract_generic_sections(shape),
    }

    # Extract text if present
    text_elem = find_child(shape, "Text")
    if text_elem is not None and text_elem.text:
        skill_data["text"] = text_elem.text.strip()

    # Extract children shapes if it's a group
    shapes_elem = find_child(shape, "Shapes")
    if shapes_elem is not None:
        skill_data["children"] = []
        for child in shapes_elem:
            if local(child.tag) == "Shape":
                skill_data["children"].append(to_skill(child))

    return skill_data


def _add_geom_cell(parent: ET.Element, name: str, val: str, unit: str | None = None) -> ET.Element:
    """Append a Cell to a geometry Row, automatically promoting val to formula if it contains expressions."""
    formula = None
    if val and any(c in str(val) for c in ('*', '/', '+', '-', 'Width', 'Height', 'Geometry')):
        formula = str(val)
        val = "0"
    cell = ET.SubElement(parent, q("Cell"), {"N": name})
    if val is not None:
        cell.set("V", str(val))
    if formula is not None:
        cell.set("F", formula)
    if unit is not None:
        cell.set("U", unit)
    return cell


def _set_cell_value_formula(
    cell: ET.Element,
    value: str | None = None,
    formula: str | None = None,
    unit: str | None = None,
    preserve_formula: bool = False,
) -> None:
    """Apply command semantics to an existing Cell element."""
    if value is not None:
        cell.set("V", str(value))
    if formula is not None:
        if formula:
            cell.set("F", formula)
        else:
            cell.attrib.pop("F", None)
    elif value is not None and not preserve_formula:
        cell.attrib.pop("F", None)
    if unit is not None:
        cell.set("U", unit)


def _set_named_cell_value_formula(
    elem: ET.Element,
    name: str,
    value: str | None = None,
    formula: str | None = None,
    unit: str | None = None,
    preserve_formula: bool = False,
) -> ET.Element:
    cell = get_cell(elem, name)
    if cell is None:
        cell = ET.SubElement(elem, q("Cell"), {"N": name})
    _set_cell_value_formula(cell, value=value, formula=formula, unit=unit, preserve_formula=preserve_formula)
    return cell


def _iter_shapes(elem: ET.Element) -> list[ET.Element]:
    shapes: list[ET.Element] = []
    if local(elem.tag) == "Shape":
        shapes.append(elem)
    for child in elem:
        shapes.extend(_iter_shapes(child))
    return shapes


def _find_shape_by_id(elem: ET.Element, shape_id: str) -> ET.Element | None:
    if local(elem.tag) == "Shape" and elem.get("ID") == shape_id:
        return elem
    for child in elem:
        found = _find_shape_by_id(child, shape_id)
        if found is not None:
            return found
    return None


def _find_instance_master_id(bridge: VisioBridge, shape: ET.Element) -> str | None:
    if shape.get("Master"):
        return shape.get("Master")
    for page in bridge.pages:
        tree = bridge.get_xml(page.xml_path)
        if tree is None:
            continue
        found = _find_instance_master_id_in_tree(tree.getroot(), shape, [])
        if found:
            return found
    return None


def _find_instance_master_id_in_tree(
    elem: ET.Element,
    target: ET.Element,
    shape_stack: list[ET.Element],
) -> str | None:
    next_stack = shape_stack
    if local(elem.tag) == "Shape":
        next_stack = [*shape_stack, elem]
    if elem is target:
        for ancestor in reversed(next_stack):
            if ancestor.get("Master"):
                return ancestor.get("Master")
        return None
    for child in elem:
        found = _find_instance_master_id_in_tree(child, target, next_stack)
        if found:
            return found
    return None


def _find_master_info(bridge: VisioBridge, master_ref: str | None):
    if not master_ref:
        return None
    for master in bridge.masters:
        if master.master_id == master_ref or master.name_u == master_ref or master.name == master_ref:
            return master
    return None


def _inherited_unit_for_instance_cell(
    bridge: VisioBridge,
    shape_path: str,
    shape: ET.Element,
    cell_name: str,
) -> str | None:
    """Return inherited U for a new page-instance owned override cell."""
    if get_cell(shape, cell_name) is not None:
        return None
    parts = [p for p in shape_path.strip("/").split("/") if p]
    if len(parts) < 4 or parts[0] != "pages" or parts[2] != "shape":
        return None

    master_info = _find_master_info(bridge, _find_instance_master_id(bridge, shape))
    if master_info is None:
        return None
    master_tree = bridge.get_xml(master_info.xml_path)
    if master_tree is None:
        return None

    master_shape = None
    master_shape_id = shape.get("MasterShape")
    if master_shape_id:
        master_shape = _find_shape_by_id(master_tree.getroot(), master_shape_id)
    else:
        master_shapes = _iter_shapes(master_tree.getroot())
        master_shape = master_shapes[0] if master_shapes else None
    if master_shape is None:
        return None

    inherited_cell = get_cell(master_shape, cell_name)
    return inherited_cell.get("U") if inherited_cell is not None else None


def _build_ellipse_geom(
    shape: ET.Element,
    x_min: str,
    y_min: str,
    x_max: str,
    y_max: str,
    start_angle: float = 0.0,
    sweep_angle: float = 360.0
) -> None:
    """Append a closed ellipse or an open elliptical arc to *shape* under a single unified engine.

    The ellipse/arc is inscribed in the bounding box [x_min, y_min] x [x_max, y_max].
    
    Args:
      start_angle: Starting angle of the arc in degrees (default 0.0).
      sweep_angle: Total sweep angle in degrees (default 360.0). If >= 360, 
                   draws a full closed shape using two EllipticalArcTo rows.
                   If < 360, draws a single open arc.
    """
    geom_ix = get_next_geom_ix(shape)
    geom_sec = ET.SubElement(shape, q("Section"), {"N": "Geometry", "IX": geom_ix})
    
    # If it's a closed shape (sweep >= 360), enable fill. If it's an open arc, disable fill.
    is_closed = (sweep_angle >= 360.0)
    set_cell(geom_sec, "NoFill", "0" if is_closed else "1")
    set_cell(geom_sec, "NoLine", "0")
    set_cell(geom_sec, "NoShow", "0")
    set_cell(geom_sec, "NoSnap", "0")

    # Helpers to compute midpoints and differences of formula/value expressions
    def _mid(a: str, b: str) -> str:
        try:
            return str((float(a) + float(b)) / 2)
        except ValueError:
            return f"({a}+{b})*0.5"

    def _span(lo: str, hi: str) -> str:
        try:
            return str(float(hi) - float(lo))
        except ValueError:
            return f"({hi})-({lo})"

    cx = _mid(x_min, x_max)
    cy = _mid(y_min, y_max)
    rx = _span(cx, x_max)
    ry = _span(cy, y_max)

    def _ratio(w_expr: str, h_expr: str) -> str:
        try:
            w = float(w_expr)
            h = float(h_expr)
            return "1" if h == 0 else str(w / h)
        except ValueError:
            return f"({w_expr})/({h_expr})"

    # Aspect ratio D cell
    ew = _span(x_min, x_max)
    eh = _span(y_min, y_max)
    aspect = _ratio(ew, eh)

    if is_closed:
        # 1. Closed Ellipse Mode: Two-arc convention
        # Row 1: MoveTo left-mid
        r1 = ET.SubElement(geom_sec, q("Row"), {"T": "MoveTo", "IX": "1"})
        _add_geom_cell(r1, "X", x_min)
        _add_geom_cell(r1, "Y", cy)

        # Row 2: upper half arc -> right-mid
        r2 = ET.SubElement(geom_sec, q("Row"), {"T": "EllipticalArcTo", "IX": "2"})
        _add_geom_cell(r2, "X", x_max)
        _add_geom_cell(r2, "Y", cy)
        _add_geom_cell(r2, "A", cx, "DL")
        _add_geom_cell(r2, "B", y_max, "DL")
        _add_geom_cell(r2, "C", "0", "DA")
        _add_geom_cell(r2, "D", aspect)

        # Row 3: lower half arc -> back to MoveTo start
        back_x = f"Geometry{int(geom_ix)+1}.X1"
        back_y = f"Geometry{int(geom_ix)+1}.Y1"
        r3 = ET.SubElement(geom_sec, q("Row"), {"T": "EllipticalArcTo", "IX": "3"})
        _add_geom_cell(r3, "X", back_x)
        _add_geom_cell(r3, "Y", back_y)
        _add_geom_cell(r3, "A", cx, "DL")
        _add_geom_cell(r3, "B", y_min, "DL")
        _add_geom_cell(r3, "C", "0", "DA")
        _add_geom_cell(r3, "D", aspect)
    else:
        # 2. Open Arc Mode: Single elliptical arc
        import math
        theta1 = math.radians(start_angle)
        theta2 = math.radians(start_angle + sweep_angle)
        thetam = math.radians(start_angle + sweep_angle / 2.0)

        c1, s1 = math.cos(theta1), math.sin(theta1)
        c2, s2 = math.cos(theta2), math.sin(theta2)
        cm, sm = math.cos(thetam), math.sin(thetam)

        # Build parameterized formula strings
        x_start = f"({cx})+({rx})*({c1:.8f})"
        y_start = f"({cy})+({ry})*({s1:.8f})"
        x_end   = f"({cx})+({rx})*({c2:.8f})"
        y_end   = f"({cy})+({ry})*({s2:.8f})"
        x_ctrl  = f"({cx})+({rx})*({cm:.8f})"
        y_ctrl  = f"({cy})+({ry})*({sm:.8f})"

        # Row 1: MoveTo start point
        r1 = ET.SubElement(geom_sec, q("Row"), {"T": "MoveTo", "IX": "1"})
        _add_geom_cell(r1, "X", x_start)
        _add_geom_cell(r1, "Y", y_start)

        # Row 2: EllipticalArcTo end point
        r2 = ET.SubElement(geom_sec, q("Row"), {"T": "EllipticalArcTo", "IX": "2"})
        _add_geom_cell(r2, "X", x_end)
        _add_geom_cell(r2, "Y", y_end)
        _add_geom_cell(r2, "A", x_ctrl, "DL")
        _add_geom_cell(r2, "B", y_ctrl, "DL")
        _add_geom_cell(r2, "C", "0", "DA")
        _add_geom_cell(r2, "D", aspect)


def _formula_cache_target_for_path(shape_path: str) -> tuple[str, str] | None:
    parts = [p for p in shape_path.strip("/").split("/") if p]
    if len(parts) >= 2 and parts[0] == "masters":
        return f"masters/{parts[1]}", "master"
    if len(parts) >= 4 and parts[0] == "pages" and parts[2] == "shape":
        return f"pages/{parts[1]}/shape/{parts[3]}", "instance"
    return None


_FORMULA_CACHE_DIRTY_ACTIONS = {
    "update_transform",
    "add_connection_pin",
    "modify_geometry",
    "delete_connection_pin",
    "draw_rectangle",
    "draw_line",
    "draw_circle",
    "draw_ellipse",
    "draw_elliptical_arc",
    "update_shape_user_cell",
    "delete_shape_user_cell",
    "set_section_cell",
    "delete_section_row",
    "set_shape_cell",
}


def apply_skill_commands(
    bridge: VisioBridge,
    shape_path: str,
    commands: list[dict],
    *,
    backend: str | None = "auto",
    output_path: str | None = None,
    **desktop_kwargs,
) -> None:
    """Apply a list of modification commands generated by the AI to a shape.
    
    Supported commands:
      - {"action": "update_transform", "property": "Width", "value": "1.0", "formula": "..."}
      - {"action": "add_connection_pin", "id": "1", "x": "...", "y": "...", "dir_x": "...", "dir_y": "..."}
      - {"action": "modify_geometry", "geom_ix": "0", "row_ix": "1", "x": "...", "y": "..."}
      - {"action": "update_text", "text": "..."}
      - {"action": "delete_connection_pin", "id": "..."}
      - {"action": "draw_rectangle", "x_min": "...", "y_min": "...", "x_max": "...", "y_max": "..."}
      - {"action": "draw_line", "x1": "...", "y1": "...", "x2": "...", "y2": "..."}
      - {"action": "draw_circle", "cx": "...", "cy": "...", "r": "..."}
      - {"action": "draw_ellipse", "x_min": "...", "y_min": "...", "x_max": "...", "y_max": "..."}
      - {"action": "draw_elliptical_arc", "x_min": "...", "y_min": "...", "x_max": "...", "y_max": "...", "start_angle": 0.0, "sweep_angle": 180.0}
      - {"action": "update_shape_user_cell", "name": "...", "value": "...", "formula": "...", "unit": "..."}
      - {"action": "delete_shape_user_cell", "name": "..."}
    """
    handled, _result = try_desktop_backend(
        bridge,
        backend=backend,
        output_path=output_path,
        desktop_apply=lambda output_path=None: apply_skill_commands_desktop(
            bridge.file_path,
            shape_path,
            commands,
            output_path=output_path,
            **desktop_kwargs,
        ),
    )
    if handled:
        return

    res = resolve_path(bridge, shape_path)
    if not res:
        raise ValueError(f"Could not resolve shape path: {shape_path}")
    
    shape, xml_file_path = res
    if local(shape.tag) != "Shape":
        raise ValueError(f"Resolved element is not a Shape: {shape_path}")

    formula_cache_target = _formula_cache_target_for_path(shape_path)
    flush_after_batch = True
    formula_cache_dirty = False

    for cmd in commands:
        action = cmd.get("action")

        if action == "recalculate_formula_cache":
            target = cmd.get("target") or shape_path
            scope = cmd.get("scope")
            if not scope:
                inferred = _formula_cache_target_for_path(target)
                if inferred is None:
                    raise ValueError(f"Could not infer formula-cache scope for target: {target}")
                target, scope = inferred
            materialize_inherited = bool(cmd.get("materialize_inherited", True))
            recalculate_formula_cache(
                bridge,
                target,
                scope,
                materialize_inherited=materialize_inherited,
            )
            if materialize_inherited:
                bridge.clear_formula_cache_dirty(target, scope)
            continue

        if cmd.get("recalculate", True) is False:
            flush_after_batch = False
        if action in _FORMULA_CACHE_DIRTY_ACTIONS:
            if formula_cache_target is None:
                raise ValueError(f"Could not infer formula-cache scope for target: {shape_path}")
            target, scope = formula_cache_target
            bridge.mark_formula_cache_dirty(target, scope, reason=str(action))
            formula_cache_dirty = True
        
        if action == "update_transform":
            prop = cmd.get("property")
            val = cmd.get("value")
            formula = cmd.get("formula")
            unit = cmd.get("unit")
            if prop:
                if unit is None:
                    unit = _inherited_unit_for_instance_cell(bridge, shape_path, shape, prop)
                _set_named_cell_value_formula(
                    shape,
                    prop,
                    value=val,
                    formula=formula,
                    unit=unit,
                    preserve_formula=bool(cmd.get("preserve_formula")),
                )
                
        elif action == "add_connection_pin":
            conn_sec = ensure_section(shape, "Connection")
            pin_id = str(cmd.get("id", "0"))
            
            # Find or create Row
            row = None
            for r in conn_sec:
                if local(r.tag) == "Row" and (r.get("IX") == pin_id or r.get("N") == pin_id):
                    row = r
                    break
            if row is None:
                row = ET.SubElement(conn_sec, q("Row"), {"IX": pin_id})
                
            # Set pin coordinate cells
            for cell_name in ("X", "Y", "DirX", "DirY"):
                val_key = cell_name.lower()
                formula_key = f"{val_key}_formula"
                
                # Check command fields
                val = cmd.get(val_key)
                # If the value contains algebra, treat it as formula
                formula = None
                if val and any(char in str(val) for char in ('*', '/', '+', '-', 'Width', 'Height')):
                    formula = str(val)
                    val = "0"
                
                cell = find_child(row, "Cell", N=cell_name)
                if cell is None:
                    cell = ET.SubElement(row, q("Cell"), {"N": cell_name})
                _set_cell_value_formula(
                    cell,
                    value=val,
                    formula=formula,
                    preserve_formula=bool(cmd.get("preserve_formula")),
                )
                    
        elif action == "modify_geometry":
            geom_ix = str(cmd.get("geom_ix", "0"))
            row_ix = str(cmd.get("row_ix", "1"))
            
            # Find Geometry section
            geom_sec = None
            for child in shape:
                if local(child.tag) == "Section" and child.get("N") == "Geometry" and child.get("IX") == geom_ix:
                    geom_sec = child
                    break
            
            if geom_sec is not None:
                row = None
                for r in geom_sec:
                    if local(r.tag) == "Row" and r.get("IX") == row_ix:
                        row = r
                        break
                if row is not None:
                    # Update cells in row
                    for cell_name in ("X", "Y"):
                        val = cmd.get(cell_name.lower())
                        formula = None
                        if val and any(char in str(val) for char in ('*', '/', '+', '-', 'Width', 'Height')):
                            formula = str(val)
                            val = "0"
                        
                        cell = find_child(row, "Cell", N=cell_name)
                        if cell is None:
                            cell = ET.SubElement(row, q("Cell"), {"N": cell_name})
                        _set_cell_value_formula(
                            cell,
                            value=val,
                            formula=formula,
                            preserve_formula=bool(cmd.get("preserve_formula")),
                        )
                            
        elif action == "update_text":
            text_val = cmd.get("text")
            if text_val is not None:
                text_elem = ensure_child(shape, "Text")
                text_elem.text = text_val

        elif action == "delete_connection_pin":
            conn_sec = get_section(shape, "Connection")
            if conn_sec is not None:
                pin_id = str(cmd.get("id"))
                for row in list(conn_sec):
                    if local(row.tag) == "Row" and (row.get("IX") == pin_id or row.get("N") == pin_id):
                        conn_sec.remove(row)
                        break
                        
        elif action == "draw_rectangle":
            x_min = cmd.get("x_min", "0")
            y_min = cmd.get("y_min", "0")
            x_max = cmd.get("x_max", "Width")
            y_max = cmd.get("y_max", "Height")
            
            geom_ix = get_next_geom_ix(shape)
            geom_sec = ET.SubElement(shape, q("Section"), {"N": "Geometry", "IX": geom_ix})
            set_cell(geom_sec, "NoFill", "0")
            set_cell(geom_sec, "NoLine", "0")
            set_cell(geom_sec, "NoShow", "0")
            set_cell(geom_sec, "NoSnap", "0")
            
            def add_row(parent, ix, row_type, x, y):
                row = ET.SubElement(parent, q("Row"), {"T": row_type, "IX": str(ix)})
                for name, val in (("X", x), ("Y", y)):
                    formula = None
                    if val and any(char in str(val) for char in ('*', '/', '+', '-', 'Width', 'Height')):
                        formula = str(val)
                        val = "0"
                    cell = ET.SubElement(row, q("Cell"), {"N": name})
                    _set_cell_value_formula(
                        cell,
                        value=val,
                        formula=formula,
                        preserve_formula=bool(cmd.get("preserve_formula")),
                    )
                return row
            
            add_row(geom_sec, 1, "MoveTo", x_min, y_min)
            add_row(geom_sec, 2, "LineTo", x_max, y_min)
            add_row(geom_sec, 3, "LineTo", x_max, y_max)
            add_row(geom_sec, 4, "LineTo", x_min, y_max)
            add_row(geom_sec, 5, "LineTo", x_min, y_min)
            
        elif action == "draw_circle":
            cx = cmd.get("cx", "Width*0.5")
            cy = cmd.get("cy", "Height*0.5")
            r  = cmd.get("r",  "Width*0.5")

            def _sub(a: str, b: str) -> str:
                try:
                    return str(float(a) - float(b))
                except ValueError:
                    return f"({a})-({b})"

            def _add(a: str, b: str) -> str:
                try:
                    return str(float(a) + float(b))
                except ValueError:
                    return f"({a})+({b})"

            x_min = _sub(cx, r)
            x_max = _add(cx, r)
            y_min = _sub(cy, r)
            y_max = _add(cy, r)
            _build_ellipse_geom(shape, x_min, y_min, x_max, y_max, start_angle=0.0, sweep_angle=360.0)

        elif action == "draw_ellipse":
            x_min = cmd.get("x_min", "0")
            y_min = cmd.get("y_min", "0")
            x_max = cmd.get("x_max", "Width")
            y_max = cmd.get("y_max", "Height")
            _build_ellipse_geom(shape, x_min, y_min, x_max, y_max, start_angle=0.0, sweep_angle=360.0)

        elif action == "draw_elliptical_arc":
            x_min = cmd.get("x_min", "0")
            y_min = cmd.get("y_min", "0")
            x_max = cmd.get("x_max", "Width")
            y_max = cmd.get("y_max", "Height")
            
            try:
                start_angle = float(cmd.get("start_angle", 0.0))
            except (ValueError, TypeError):
                start_angle = 0.0
                
            try:
                sweep_angle = float(cmd.get("sweep_angle", 360.0))
            except (ValueError, TypeError):
                sweep_angle = 360.0
                
            _build_ellipse_geom(shape, x_min, y_min, x_max, y_max, start_angle, sweep_angle)

        elif action == "draw_line":
            x1 = cmd.get("x1", "0")
            y1 = cmd.get("y1", "0")
            x2 = cmd.get("x2", "Width")
            y2 = cmd.get("y2", "Height")
            
            geom_ix = get_next_geom_ix(shape)
            geom_sec = ET.SubElement(shape, q("Section"), {"N": "Geometry", "IX": geom_ix})
            set_cell(geom_sec, "NoFill", "1")
            set_cell(geom_sec, "NoLine", "0")
            set_cell(geom_sec, "NoShow", "0")
            set_cell(geom_sec, "NoSnap", "0")
            
            def add_row(parent, ix, row_type, x, y):
                row = ET.SubElement(parent, q("Row"), {"T": row_type, "IX": str(ix)})
                for name, val in (("X", x), ("Y", y)):
                    formula = None
                    if val and any(char in str(val) for char in ('*', '/', '+', '-', 'Width', 'Height')):
                        formula = str(val)
                        val = "0"
                    cell = ET.SubElement(row, q("Cell"), {"N": name})
                    _set_cell_value_formula(
                        cell,
                        value=val,
                        formula=formula,
                        preserve_formula=bool(cmd.get("preserve_formula")),
                    )
                return row
            
            add_row(geom_sec, 1, "MoveTo", x1, y1)
            add_row(geom_sec, 2, "LineTo", x2, y2)

        elif action == "update_shape_user_cell":
            name = cmd.get("name")
            val = cmd.get("value")
            formula = cmd.get("formula")
            unit = cmd.get("unit")
            if name:
                set_user_row(shape, name, formula or "", val or "0", unit)

        elif action == "delete_shape_user_cell":
            name = cmd.get("name")
            user_sec = get_section(shape, "User")
            if user_sec is not None:
                for row in list(user_sec):
                    if local(row.tag) == "Row" and row.get("N") == name:
                        user_sec.remove(row)
                        break
                        
        elif action == "set_section_cell":
            sec_name = cmd.get("section")
            sec_ix = str(cmd.get("section_ix", "0"))
            row_name = cmd.get("row_name")
            row_ix = str(cmd.get("row_ix", ""))
            row_type = cmd.get("row_type")
            cell_name = cmd.get("cell_name")
            val = cmd.get("value") or cmd.get("val")
            formula = cmd.get("formula")
            unit = cmd.get("unit")
            
            if sec_name and cell_name:
                # Find or create section
                sec = None
                for child in shape:
                    if local(child.tag) == "Section" and child.get("N") == sec_name:
                        if sec_name == "Geometry":
                            if child.get("IX", "0") == sec_ix:
                                sec = child
                                break
                        else:
                            sec = child
                            break
                if sec is None:
                    attrs = {"N": sec_name}
                    if sec_name == "Geometry" or sec_ix != "0":
                        attrs["IX"] = sec_ix
                    sec = ET.SubElement(shape, q("Section"), attrs)
                    
                # Find or create row
                row = None
                for r in sec:
                    if local(r.tag) != "Row":
                        continue
                    if row_name and r.get("N") == row_name:
                        row = r
                        break
                    elif row_ix and r.get("IX") == row_ix:
                        row = r
                        break
                if row is None:
                    row_attrs = {}
                    if row_name:
                        row_attrs["N"] = row_name
                    if row_ix:
                        row_attrs["IX"] = row_ix
                    if row_type:
                        row_attrs["T"] = row_type
                    row = ET.SubElement(sec, q("Row"), row_attrs)
                    
                # Find or create cell
                cell = find_child(row, "Cell", N=cell_name)
                if cell is None:
                    cell = ET.SubElement(row, q("Cell"), {"N": cell_name})
                    
                if val and not formula and any(char in str(val) for char in ('*', '/', '+', '-', 'Width', 'Height')):
                    formula = str(val)
                    val = "0"
                    
                if val is None and cell.get("V") is not None and formula is not None:
                    val = "0"
                _set_cell_value_formula(
                    cell,
                    value=val,
                    formula=formula,
                    unit=unit,
                    preserve_formula=bool(cmd.get("preserve_formula")),
                )

        elif action == "delete_section_row":
            sec_name = cmd.get("section")
            sec_ix = str(cmd.get("section_ix", "0"))
            row_name = cmd.get("row_name")
            row_ix = str(cmd.get("row_ix", ""))
            
            if sec_name:
                sec = None
                for child in shape:
                    if local(child.tag) == "Section" and child.get("N") == sec_name:
                        if sec_name == "Geometry":
                            if child.get("IX", "0") == sec_ix:
                                sec = child
                                break
                        else:
                            sec = child
                            break
                if sec is not None:
                    for r in list(sec):
                        if local(r.tag) != "Row":
                            continue
                        if row_name and r.get("N") == row_name:
                            sec.remove(r)
                            break
                        elif row_ix and r.get("IX") == row_ix:
                            sec.remove(r)
                            break

        elif action == "set_shape_cell":
            cell_name = cmd.get("cell_name") or cmd.get("property")
            val = cmd.get("value") or cmd.get("val")
            formula = cmd.get("formula")
            unit = cmd.get("unit")
            if cell_name:
                if unit is None:
                    unit = _inherited_unit_for_instance_cell(bridge, shape_path, shape, cell_name)
                if val and not formula and any(char in str(val) for char in ('*', '/', '+', '-', 'Width', 'Height')):
                    formula = str(val)
                    val = "0"
                _set_named_cell_value_formula(
                    shape,
                    cell_name,
                    value=val,
                    formula=formula,
                    unit=unit,
                    preserve_formula=bool(cmd.get("preserve_formula")),
                )
                
    # Mark XML as modified
    bridge.mark_modified(xml_file_path)
    if formula_cache_dirty and flush_after_batch:
        bridge.flush_formula_cache()
    save_xml_fallback_if_requested(bridge, output_path)

def get_next_geom_ix(shape: ET.Element) -> str:
    """Helper to find the next unused Geometry section index in a shape."""
    max_ix = -1
    for child in shape:
        if local(child.tag) == "Section" and child.get("N") == "Geometry":
            try:
                max_ix = max(max_ix, int(child.get("IX", "0")))
            except ValueError:
                pass
    return str(max_ix + 1)

def _element_contains_identity(root: ET.Element, needle: ET.Element) -> bool:
    if root is needle:
        return True
    return any(_element_contains_identity(child, needle) for child in root)


def _path_for_shape_identity(bridge: VisioBridge, shape: ET.Element) -> tuple[str, str] | None:
    shape_id = shape.get("ID")
    if not shape_id:
        return None
    for master in bridge.masters:
        tree = bridge.get_xml(master.xml_path)
        if tree is not None and _element_contains_identity(tree.getroot(), shape):
            return f"masters/{master.name_u or master.master_id}", "master"
    for page in bridge.pages:
        tree = bridge.get_xml(page.xml_path)
        if tree is not None and _element_contains_identity(tree.getroot(), shape):
            return f"pages/{page.name_u or page.page_id}/shape/{shape_id}", "instance"
    return None


def eval_visio_formula(
    formula: str,
    shape_id: str,
    evaluated: dict[str, dict[str, float]],
    root_id: str,
    doc_users: dict[str, str] | None = None,
) -> float | None:
    """Compatibility wrapper around the scoped formula-cache evaluator."""
    return eval_formula_for_cache(formula, shape_id, evaluated, root_id, doc_users)


def recalculate_formulas(root_shape: ET.Element, bridge: VisioBridge) -> None:
    """Compatibility wrapper for callers that still pass a Shape element."""
    inferred = _path_for_shape_identity(bridge, root_shape)
    if inferred is None:
        return
    target, scope = inferred
    recalculate_formula_cache(bridge, target, scope)

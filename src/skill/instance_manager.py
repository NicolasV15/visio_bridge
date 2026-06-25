"""SKILL interface implementation to manage shape instances and group structure."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from ..core.bridge import VisioBridge
from ..core.locator import ElementLocator, resolve_path
from ..core.xml_utils import get_cell, set_cell, find_child, local, q, ensure_child
from ..desktop import apply_instance_commands_desktop
from .backend import save_xml_if_requested, try_desktop_backend

_TRANSFORM_CELLS = (
    "Width",
    "Height",
    "PinX",
    "PinY",
    "LocPinX",
    "LocPinY",
    "Angle",
    "FlipX",
    "FlipY",
)

def _find_all_ids(elem: ET.Element) -> set[int]:
    """Collect all shape IDs currently in use inside the element tree."""
    ids = set()
    if local(elem.tag) == "Shape" and elem.get("ID"):
        try:
            ids.add(int(elem.get("ID")))
        except ValueError:
            pass
    for child in elem:
        ids.update(_find_all_ids(child))
    return ids

def _get_id_generator(root_elem: ET.Element):
    """Yield unique integer IDs not in use in root_elem."""
    used_ids = _find_all_ids(root_elem)
    next_id = max(used_ids) + 1 if used_ids else 1
    while True:
        yield next_id
        next_id += 1

def _get_parent_path(shape_path: str) -> str:
    """Derive parent container path by removing the last shape segment."""
    parts = shape_path.rstrip("/").split("/")
    if len(parts) >= 2 and parts[-2] == "shape":
        return "/".join(parts[:-2])
    return ""


def _format_number(value: float) -> str:
    return f"{value:.15g}"


def _shape_root_path(shape_path: str) -> str:
    return shape_path.split("/shape/")[0]


def _mark_structure_dirty(bridge: VisioBridge, reference_path: str, reason: str) -> bool:
    parts = [part for part in reference_path.strip("/").split("/") if part]
    if len(parts) >= 2 and parts[0] == "masters":
        bridge.mark_formula_cache_dirty(f"masters/{parts[1]}", "master", reason=reason)
        return True
    if len(parts) >= 4 and parts[0] == "pages" and parts[2] == "shape":
        bridge.mark_formula_cache_dirty(reference_path, "instance", reason=reason)
        return True
    return False


def _cell_float(shape: ET.Element, cell_name: str, *, default: float | None = None) -> float:
    cell = get_cell(shape, cell_name)
    if cell is None or cell.get("V") is None:
        if default is not None:
            return default
        raise ValueError(f"Shape is missing a cached {cell_name} value required for structural edits.")
    try:
        return float(cell.get("V", ""))
    except ValueError as exc:
        raise ValueError(f"Shape has a non-numeric cached {cell_name} value required for structural edits.") from exc


def _shape_bounds(shape: ET.Element, shape_path: str) -> tuple[float, float, float, float]:
    angle = _cell_float(shape, "Angle", default=0.0)
    if abs(angle) > 1e-9:
        raise ValueError(f"Only zero-angle shapes are supported for XML grouping: {shape_path}")
    width = _cell_float(shape, "Width")
    height = _cell_float(shape, "Height")
    pin_x = _cell_float(shape, "PinX")
    pin_y = _cell_float(shape, "PinY")
    loc_pin_x = _cell_float(shape, "LocPinX")
    loc_pin_y = _cell_float(shape, "LocPinY")
    left = pin_x - loc_pin_x
    bottom = pin_y - loc_pin_y
    return left, bottom, left + width, bottom + height


def _normalize_transform_values(
    shape: ET.Element,
    *,
    pin_x: float | None = None,
    pin_y: float | None = None,
) -> None:
    values = {
        "Width": _cell_float(shape, "Width"),
        "Height": _cell_float(shape, "Height"),
        "PinX": pin_x if pin_x is not None else _cell_float(shape, "PinX"),
        "PinY": pin_y if pin_y is not None else _cell_float(shape, "PinY"),
        "LocPinX": _cell_float(shape, "LocPinX"),
        "LocPinY": _cell_float(shape, "LocPinY"),
        "Angle": _cell_float(shape, "Angle", default=0.0),
        "FlipX": _cell_float(shape, "FlipX", default=0.0),
        "FlipY": _cell_float(shape, "FlipY", default=0.0),
    }
    for name, value in values.items():
        set_cell(shape, name, _format_number(value))


def _create_group_shape(id_gen, bounds: tuple[float, float, float, float]) -> ET.Element:
    left, bottom, right, top = bounds
    width = right - left
    height = top - bottom
    pin_x = left + width * 0.5
    pin_y = bottom + height * 0.5
    group_shape = ET.Element(q("Shape"), {"ID": str(next(id_gen)), "Type": "Group"})
    set_cell(group_shape, "Width", _format_number(width))
    set_cell(group_shape, "Height", _format_number(height))
    set_cell(group_shape, "PinX", _format_number(pin_x))
    set_cell(group_shape, "PinY", _format_number(pin_y))
    set_cell(group_shape, "LocPinX", _format_number(width * 0.5), "Width*0.5")
    set_cell(group_shape, "LocPinY", _format_number(height * 0.5), "Height*0.5")
    set_cell(group_shape, "Angle", "0")
    set_cell(group_shape, "FlipX", "0")
    set_cell(group_shape, "FlipY", "0")
    ET.SubElement(group_shape, q("Shapes"))
    return group_shape


def _direct_shapes(parent_elem: ET.Element) -> tuple[ET.Element, list[ET.Element]]:
    shapes_container = find_child(parent_elem, "Shapes")
    if shapes_container is None:
        raise ValueError("Target container has no direct child shapes.")
    return shapes_container, [child for child in shapes_container if local(child.tag) == "Shape"]

def _instantiate_master_shape(master_shape: ET.Element, id_gen) -> ET.Element:
    """Recursively clone a Master shape template, assigning new unique IDs and setting MasterShape attributes."""
    new_shape = ET.Element(q("Shape"))
    new_shape.set("ID", str(next(id_gen)))
    
    if master_shape.get("Type"):
        new_shape.set("Type", master_shape.get("Type"))
    if master_shape.get("Name"):
        new_shape.set("Name", master_shape.get("Name"))
    if master_shape.get("NameU"):
        new_shape.set("NameU", master_shape.get("NameU"))

    # Copy top-level Cell elements
    for child in master_shape:
        if local(child.tag) == "Cell":
            new_cell = ET.SubElement(new_shape, q("Cell"))
            for k, v in child.attrib.items():
                new_cell.set(k, v)
        elif local(child.tag) == "Section":
            # Copy Section and its child Row and Cell nodes
            new_sec = ET.SubElement(new_shape, q("Section"))
            for k, v in child.attrib.items():
                new_sec.set(k, v)
            for row in child:
                if local(row.tag) == "Row":
                    new_row = ET.SubElement(new_sec, q("Row"))
                    for k, v in row.attrib.items():
                        new_row.set(k, v)
                    for cell in row:
                        if local(cell.tag) == "Cell":
                            new_cell = ET.SubElement(new_row, q("Cell"))
                            for k, v in cell.attrib.items():
                                new_cell.set(k, v)
                            
    # Recursively copy child shapes if this is a group shape
    shapes_container = find_child(master_shape, "Shapes")
    if shapes_container is not None:
        new_shapes = ET.SubElement(new_shape, q("Shapes"))
        for child_master in shapes_container:
            if local(child_master.tag) == "Shape":
                new_child = _instantiate_master_shape(child_master, id_gen)
                new_child.set("MasterShape", child_master.get("ID"))
                new_shapes.append(new_child)
                
    return new_shape

def apply_instance_commands(
    bridge: VisioBridge,
    commands: list[dict],
    *,
    backend: str,
    output_path: str | None = None,
    **desktop_kwargs,
) -> list[dict]:
    """Execute shape instance management commands.
    
    Returns metadata list containing results of successfully executed operations.
    
    Supported commands:
      - {"action": "add_instance", "parent": "pages/Page-1", "master": "Cap", "x": "1.5", "y": "2.0", "width": "...", "height": "...", "angle": "0"}
      - {"action": "copy_instance", "shape_path": "pages/Page-1/shape/168", "x": "3.5", "y": "2.0"}
      - {"action": "delete_instance", "shape_path": "pages/Page-1/shape/168"}
      - {"action": "ungroup", "shape_path": "masters/NMOS_B/shape/5/shape/6"}
      - {"action": "group", "shape_paths": ["masters/NMOS/shape/5/shape/7", "masters/NMOS/shape/5/shape/8"]}
    """
    handled, result = try_desktop_backend(
        bridge,
        backend=backend,
        output_path=output_path,
        desktop_apply=lambda output_path=None: apply_instance_commands_desktop(
            bridge.file_path,
            commands,
            output_path=output_path,
            **desktop_kwargs,
        ),
    )
    if handled:
        return (result.data or {}).get("results", [])

    locator = ElementLocator(bridge)
    results = []
    formula_cache_dirty = False

    for cmd in commands:
        action = cmd.get("action")
        
        if action == "add_instance":
            parent_path = cmd.get("parent")
            master_ref = cmd.get("master")
            x = cmd.get("x")
            y = cmd.get("y")
            
            if not parent_path or not master_ref or x is None or y is None:
                raise ValueError("add_instance requires 'parent', 'master', 'x', and 'y' parameters.")

            # Resolve parent container
            res = resolve_path(bridge, parent_path)
            if not res:
                raise ValueError(f"Could not resolve parent container path: {parent_path}")
            parent_elem, xml_file_path = res
            
            # Find the master definition
            target_master = None
            for m in bridge.masters:
                if m.name_u == master_ref or m.name == master_ref or m.master_id == str(master_ref):
                    target_master = m
                    break
            if not target_master:
                raise ValueError(f"Could not find Master matching reference: {master_ref}")
            
            master_root = locator.find(f"masters/{target_master.name_u}")
            if master_root is None:
                raise ValueError(f"Could not load Master XML root for: {target_master.name_u}")
            
            # Find top shape of master
            master_shapes = find_child(master_root, "Shapes")
            if master_shapes is None or len(master_shapes) == 0:
                # Fallback to direct top shape
                master_shape = find_child(master_root, "Shape")
            else:
                master_shape = next((child for child in master_shapes if local(child.tag) == "Shape"), None)
            
            if master_shape is None:
                raise ValueError(f"Master {target_master.name_u} contains no shapes.")

            # Load page root to obtain ID generator
            page_root_path = parent_path.split("/shape/")[0]
            page_res = resolve_path(bridge, page_root_path)
            if not page_res:
                raise ValueError(f"Could not resolve page XML root for: {parent_path}")
            page_root, _ = page_res
            id_gen = _get_id_generator(page_root)
            
            # Clone Master Shape
            new_shape = _instantiate_master_shape(master_shape, id_gen)
            new_shape.set("Master", target_master.master_id)
            
            # Override coordinates and settings
            set_cell(new_shape, "PinX", str(x))
            set_cell(new_shape, "PinY", str(y))
            
            if cmd.get("width"):
                set_cell(new_shape, "Width", str(cmd["width"]))
            if cmd.get("height"):
                set_cell(new_shape, "Height", str(cmd["height"]))
                
            # Default or override LocPinX / LocPinY
            if get_cell(new_shape, "LocPinX") is None:
                set_cell(new_shape, "LocPinX", formula="Width*0.5")
            if get_cell(new_shape, "LocPinY") is None:
                set_cell(new_shape, "LocPinY", formula="Height*0.5")
                
            angle = cmd.get("angle", "0")
            set_cell(new_shape, "Angle", str(angle))

            # Add to shapes container of parent element
            shapes_container = ensure_child(parent_elem, "Shapes")
            shapes_container.append(new_shape)
            
            # Record modification
            bridge.mark_modified(xml_file_path)
            
            new_id = new_shape.get("ID")
            new_shape_path = f"{parent_path}/shape/{new_id}"
            bridge.mark_formula_cache_dirty(new_shape_path, "instance", reason="add_instance")
            formula_cache_dirty = True
            results.append({
                "action": "add_instance",
                "status": "success",
                "master": target_master.name_u,
                "shape_id": new_id,
                "shape_path": new_shape_path
            })
            
        elif action == "copy_instance":
            shape_path = cmd.get("shape_path")
            x = cmd.get("x")
            y = cmd.get("y")
            
            if not shape_path or x is None or y is None:
                raise ValueError("copy_instance requires 'shape_path', 'x', and 'y' parameters.")
                
            res = resolve_path(bridge, shape_path)
            if not res:
                raise ValueError(f"Could not resolve source shape path: {shape_path}")
            source_shape, xml_file_path = res
            
            # Find parent path and element
            parent_path = _get_parent_path(shape_path)
            parent_res = resolve_path(bridge, parent_path)
            if not parent_res:
                raise ValueError(f"Could not resolve parent container path for: {shape_path}")
            parent_elem, _ = parent_res
            
            # Load page root to obtain ID generator
            page_root_path = shape_path.split("/shape/")[0]
            page_res = resolve_path(bridge, page_root_path)
            if not page_res:
                raise ValueError(f"Could not resolve page XML root for: {shape_path}")
            page_root, _ = page_res
            id_gen = _get_id_generator(page_root)
            
            # Deep copy source shape
            new_shape = copy.deepcopy(source_shape)
            
            # Re-generate IDs recursively
            new_shape.set("ID", str(next(id_gen)))
            def update_children_ids(elem):
                for child in elem:
                    if local(child.tag) == "Shape":
                        child.set("ID", str(next(id_gen)))
                    update_children_ids(child)
            update_children_ids(new_shape)
            
            # Override coordinates
            set_cell(new_shape, "PinX", str(x))
            set_cell(new_shape, "PinY", str(y))
            
            # Add to shapes container
            shapes_container = ensure_child(parent_elem, "Shapes")
            shapes_container.append(new_shape)
            
            # Record modification
            bridge.mark_modified(xml_file_path)
            
            new_id = new_shape.get("ID")
            new_shape_path = f"{parent_path}/shape/{new_id}"
            bridge.mark_formula_cache_dirty(new_shape_path, "instance", reason="copy_instance")
            formula_cache_dirty = True
            results.append({
                "action": "copy_instance",
                "status": "success",
                "shape_id": new_id,
                "shape_path": new_shape_path
            })
            
        elif action == "delete_instance":
            shape_path = cmd.get("shape_path")
            if not shape_path:
                raise ValueError("delete_instance requires 'shape_path' parameter.")
                
            res = resolve_path(bridge, shape_path)
            if not res:
                raise ValueError(f"Could not resolve shape path to delete: {shape_path}")
            source_shape, xml_file_path = res
            
            # Find parent path and element
            parent_path = _get_parent_path(shape_path)
            parent_res = resolve_path(bridge, parent_path)
            if not parent_res:
                raise ValueError(f"Could not resolve parent container path for: {shape_path}")
            parent_elem, _ = parent_res
            
            # Remove shape from shapes container
            shapes_container = find_child(parent_elem, "Shapes")
            if shapes_container is not None:
                shapes_container.remove(source_shape)
                
            bridge.mark_modified(xml_file_path)
            results.append({
                "action": "delete_instance",
                "status": "success",
                "shape_path": shape_path
            })

        elif action == "ungroup":
            shape_path = cmd.get("shape_path")
            if not shape_path:
                raise ValueError("ungroup requires 'shape_path' parameter.")

            res = resolve_path(bridge, shape_path)
            if not res:
                raise ValueError(f"Could not resolve group shape path to ungroup: {shape_path}")
            group_shape, xml_file_path = res

            parent_path = _get_parent_path(shape_path)
            parent_res = resolve_path(bridge, parent_path)
            if not parent_res:
                raise ValueError(f"Could not resolve parent container path for: {shape_path}")
            parent_elem, _ = parent_res

            group_left, group_bottom, _group_right, _group_top = _shape_bounds(group_shape, shape_path)
            parent_shapes, direct_siblings = _direct_shapes(parent_elem)
            if group_shape not in direct_siblings:
                raise ValueError(f"Target shape is not a direct child of its parent container: {shape_path}")
            group_index = direct_siblings.index(group_shape)

            group_children = find_child(group_shape, "Shapes")
            if group_children is None:
                raise ValueError(f"Target shape has no child shapes to ungroup: {shape_path}")
            moved_children = [child for child in list(group_children) if local(child.tag) == "Shape"]
            if not moved_children:
                raise ValueError(f"Target shape has no child shapes to ungroup: {shape_path}")

            moved_paths: list[str] = []
            for child in moved_children:
                child_pin_x = _cell_float(child, "PinX") + group_left
                child_pin_y = _cell_float(child, "PinY") + group_bottom
                _normalize_transform_values(child, pin_x=child_pin_x, pin_y=child_pin_y)
                group_children.remove(child)
            for offset, child in enumerate(moved_children):
                parent_shapes.insert(group_index + offset, child)
                moved_paths.append(f"{parent_path}/shape/{child.get('ID', '')}")

            parent_shapes.remove(group_shape)

            bridge.mark_modified(xml_file_path)
            dirty_reference = moved_paths[0] if moved_paths else shape_path
            if _mark_structure_dirty(bridge, dirty_reference, "ungroup"):
                formula_cache_dirty = True
            results.append({
                "action": "ungroup",
                "status": "success",
                "shape_path": shape_path,
                "parent_path": parent_path,
                "moved_children": len(moved_children),
                "moved_shape_paths": moved_paths,
            })

        elif action == "group":
            shape_paths = cmd.get("shape_paths")
            if not isinstance(shape_paths, list) or len(shape_paths) < 2:
                raise ValueError("group requires at least two 'shape_paths'.")
            if len({str(path) for path in shape_paths}) != len(shape_paths):
                raise ValueError("group does not accept duplicate shape paths.")

            resolved_shapes: list[tuple[str, str, ET.Element, str]] = []
            common_parent_path: str | None = None
            common_parent_elem: ET.Element | None = None
            xml_file_path: str | None = None
            for shape_path in shape_paths:
                if not isinstance(shape_path, str) or not shape_path:
                    raise ValueError("group requires every entry in 'shape_paths' to be a non-empty string.")
                res = resolve_path(bridge, shape_path)
                if not res:
                    raise ValueError(f"Could not resolve shape path to group: {shape_path}")
                shape, path_xml = res
                parent_path = _get_parent_path(shape_path)
                parent_res = resolve_path(bridge, parent_path)
                if not parent_res:
                    raise ValueError(f"Could not resolve parent container path for: {shape_path}")
                parent_elem, _ = parent_res
                if common_parent_path is None:
                    common_parent_path = parent_path
                    common_parent_elem = parent_elem
                    xml_file_path = path_xml
                elif parent_path != common_parent_path:
                    raise ValueError("group requires all shapes to share the same direct parent container.")
                resolved_shapes.append((shape_path, parent_path, shape, path_xml))

            assert common_parent_path is not None
            assert common_parent_elem is not None
            assert xml_file_path is not None

            parent_shapes, direct_children = _direct_shapes(common_parent_elem)
            child_index_by_id = {id(child): index for index, child in enumerate(direct_children)}

            selected: list[tuple[str, ET.Element]] = []
            for shape_path, _parent_path, shape, _path_xml in resolved_shapes:
                if id(shape) not in child_index_by_id:
                    raise ValueError("group only supports direct sibling shapes from the same parent container.")
                selected.append((shape_path, shape))

            ordered_selected = sorted(selected, key=lambda item: child_index_by_id[id(item[1])])
            first_index = child_index_by_id[id(ordered_selected[0][1])]

            bounds = [_shape_bounds(shape, shape_path) for shape_path, shape in ordered_selected]
            left = min(bound[0] for bound in bounds)
            bottom = min(bound[1] for bound in bounds)
            right = max(bound[2] for bound in bounds)
            top = max(bound[3] for bound in bounds)

            root_res = resolve_path(bridge, _shape_root_path(common_parent_path))
            if not root_res:
                raise ValueError(f"Could not resolve root container for grouping: {common_parent_path}")
            root_elem, _ = root_res
            id_gen = _get_id_generator(root_elem)

            group_shape = _create_group_shape(id_gen, (left, bottom, right, top))
            group_shapes = ensure_child(group_shape, "Shapes")

            for _shape_path, shape in ordered_selected:
                child_pin_x = _cell_float(shape, "PinX") - left
                child_pin_y = _cell_float(shape, "PinY") - bottom
                _normalize_transform_values(shape, pin_x=child_pin_x, pin_y=child_pin_y)
                parent_shapes.remove(shape)
                group_shapes.append(shape)

            parent_shapes.insert(first_index, group_shape)
            bridge.mark_modified(xml_file_path)

            group_id = group_shape.get("ID", "")
            group_path = f"{common_parent_path}/shape/{group_id}"
            if _mark_structure_dirty(bridge, group_path, "group"):
                formula_cache_dirty = True
            results.append({
                "action": "group",
                "status": "success",
                "parent_path": common_parent_path,
                "shape_id": group_id,
                "shape_path": group_path,
                "shape_paths": [shape_path for shape_path, _shape in ordered_selected],
                "child_count": len(ordered_selected),
            })
            
        else:
            raise ValueError(f"Unknown instance command action: {action}")

    if formula_cache_dirty:
        bridge.flush_formula_cache()
    save_xml_if_requested(bridge, output_path)

    return results

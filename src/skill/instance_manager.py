"""SKILL interface implementation to manage shape instances (add, copy, and delete shapes) on a page or group shape."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from ..core.bridge import VisioBridge
from ..core.locator import ElementLocator, resolve_path
from ..core.xml_utils import get_cell, set_cell, find_child, local, q, ensure_child
from ..desktop import apply_instance_commands_desktop
from .backend import save_xml_if_requested, try_desktop_backend

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
    """Execute shape instance management commands (add, copy, delete).
    
    Returns metadata list containing results of successfully executed operations.
    
    Supported commands:
      - {"action": "add_instance", "parent": "pages/Page-1", "master": "Cap", "x": "1.5", "y": "2.0", "width": "...", "height": "...", "angle": "0"}
      - {"action": "copy_instance", "shape_path": "pages/Page-1/shape/168", "x": "3.5", "y": "2.0"}
      - {"action": "delete_instance", "shape_path": "pages/Page-1/shape/168"}
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
            
        else:
            raise ValueError(f"Unknown instance command action: {action}")

    if formula_cache_dirty:
        bridge.flush_formula_cache()
    save_xml_if_requested(bridge, output_path)

    return results

"""Helpers for creating new Visio masters through structured XML updates."""

from __future__ import annotations

import copy
import math
import uuid
import xml.etree.ElementTree as ET

from ..core.bridge import MasterInfo, VisioBridge, _RT_MASTER
from ..core.locator import ElementLocator
from ..core.xml_utils import R_NS, REL_NS, find_child, get_cell, local, q, rq, set_cell

CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _format_number(value: float) -> str:
    return f"{value:.15g}"


def _cell_float(shape: ET.Element, cell_name: str) -> float:
    cell = get_cell(shape, cell_name)
    if cell is None or cell.get("V") is None:
        raise ValueError(f"Shape is missing cached value for {cell_name}.")
    return float(cell.get("V", "0"))


def _find_master_info(bridge: VisioBridge, ref: str) -> MasterInfo:
    for master in bridge.masters:
        if master.master_id == ref or master.name_u == ref or master.name == ref:
            return master
    raise ValueError(f"Could not find master: {ref}")


def _find_master_elem(root: ET.Element, info: MasterInfo) -> ET.Element:
    for child in root:
        if local(child.tag) != "Master":
            continue
        if (
            child.get("ID") == info.master_id
            or child.get("NameU") == info.name_u
            or child.get("Name") == info.name
        ):
            return child
    raise ValueError(f"Could not locate master element for {info.name_u or info.master_id}.")


def _next_rel_id(rels_root: ET.Element) -> str:
    max_id = 0
    for rel in rels_root:
        if local(rel.tag) != "Relationship":
            continue
        rel_id = rel.get("Id", "")
        if rel_id.startswith("rId"):
            try:
                max_id = max(max_id, int(rel_id[3:]))
            except ValueError:
                continue
    return f"rId{max_id + 1}"


def _next_master_id(bridge: VisioBridge) -> str:
    max_id = 0
    for master in bridge.masters:
        try:
            max_id = max(max_id, int(master.master_id))
        except ValueError:
            continue
    return str(max_id + 1)


def _next_master_part(bridge: VisioBridge) -> str:
    max_num = 0
    for master in bridge.masters:
        path = master.xml_path.rsplit("/", 1)[-1]
        if not (path.startswith("master") and path.endswith(".xml")):
            continue
        try:
            max_num = max(max_num, int(path[len("master") : -len(".xml")]))
        except ValueError:
            continue
    return f"visio/masters/master{max_num + 1}.xml"


def _update_page_sheet(page_sheet: ET.Element, width_val: float, height_val: float) -> None:
    set_cell(page_sheet, "PageWidth", _format_number(width_val), "Sheet.5!Width", "MM")
    set_cell(page_sheet, "PageHeight", _format_number(height_val), "Sheet.5!Height", "MM")


def _build_arrow_master_contents(
    source_top_shape: ET.Element,
    source_upper_line: ET.Element,
    source_lower_line: ET.Element,
    *,
    name: str,
    name_u: str,
    width_val: float,
    height_val: float,
) -> ET.ElementTree:
    root = ET.Element(q("MasterContents"), {XML_SPACE: "preserve"})
    root_shapes = ET.SubElement(root, q("Shapes"))

    top_shape = copy.deepcopy(source_top_shape)
    top_shape.set("NameU", name_u)
    top_shape.set("IsCustomNameU", "1")
    top_shape.set("Name", name)
    top_shape.set("IsCustomName", "1")

    for child in list(top_shape):
        if local(child.tag) == "Section" and child.get("N") in {"Connection", "Geometry"}:
            top_shape.remove(child)
        elif local(child.tag) == "Shapes":
            top_shape.remove(child)

    set_cell(top_shape, "PinX", _format_number(width_val * 0.5), "Width*0.5", "MM")
    set_cell(top_shape, "PinY", _format_number(height_val * 0.5), "Height*0.5", "MM")
    set_cell(top_shape, "Width", _format_number(width_val), "TheDoc!User.M*0.12", "MM")
    set_cell(top_shape, "Height", _format_number(height_val), "TheDoc!User.M*0.24", "MM")
    set_cell(top_shape, "LocPinX", _format_number(width_val * 0.5), "Width*0.5", "MM")
    set_cell(top_shape, "LocPinY", _format_number(height_val * 0.5), "Height*0.5", "MM")
    set_cell(top_shape, "Angle", "0")
    set_cell(top_shape, "FlipX", "0")
    set_cell(top_shape, "FlipY", "0")
    set_cell(top_shape, "ResizeMode", "0")

    child_shapes = ET.SubElement(top_shape, q("Shapes"))
    line_len = math.hypot(width_val, height_val * 0.5)

    def configure_line(
        source_line: ET.Element,
        *,
        new_id: str,
        end_y_formula: str,
        end_y_value: float,
        pin_y_value: float,
        angle_value: float,
    ) -> ET.Element:
        line = copy.deepcopy(source_line)
        line.set("ID", new_id)
        set_cell(line, "PinX", _format_number(width_val * 0.5), "(BeginX+EndX)/2", "MM")
        set_cell(line, "PinY", _format_number(pin_y_value), "(BeginY+EndY)/2", "MM")
        set_cell(line, "Width", _format_number(line_len), "SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)", "MM")
        set_cell(line, "Height", "0")
        set_cell(line, "LocPinX", _format_number(line_len * 0.5), "Width*0.5", "MM")
        set_cell(line, "LocPinY", "0", "Height*0.5")
        set_cell(line, "Angle", _format_number(angle_value), "ATAN2(EndY-BeginY,EndX-BeginX)")
        set_cell(line, "BeginX", _format_number(width_val), "Sheet.5!Width*1", "MM")
        set_cell(line, "BeginY", _format_number(height_val * 0.5), "Sheet.5!Height*0.5", "MM")
        set_cell(line, "EndX", "0", "Sheet.5!Width*0", "MM")
        set_cell(line, "EndY", _format_number(end_y_value), end_y_formula, "MM")
        return line

    upper = configure_line(
        source_upper_line,
        new_id="6",
        end_y_formula="Sheet.5!Height*1",
        end_y_value=height_val,
        pin_y_value=height_val * 0.75,
        angle_value=math.atan2(height_val * 0.5, -width_val),
    )
    lower = configure_line(
        source_lower_line,
        new_id="7",
        end_y_formula="Sheet.5!Height*0",
        end_y_value=0.0,
        pin_y_value=height_val * 0.25,
        angle_value=math.atan2(-height_val * 0.5, -width_val),
    )
    child_shapes.append(upper)
    child_shapes.append(lower)
    root_shapes.append(top_shape)
    return ET.ElementTree(root)


def create_arrow_master(
    bridge: VisioBridge,
    *,
    name: str = "Arrow",
    name_u: str = "Arrow",
    source_master: str = "NMOS",
) -> MasterInfo:
    """Create a reusable Arrow master based on the NMOS V-arrow geometry."""
    for master in bridge.masters:
        if master.name_u == name_u or master.name == name:
            raise ValueError(f"Master {name_u} already exists.")

    source_info = _find_master_info(bridge, source_master)
    locator = ElementLocator(bridge)
    source_top_shape = locator.find(f"masters/{source_info.name_u}/shape/5")
    source_upper_line = locator.find(f"masters/{source_info.name_u}/shape/13")
    source_lower_line = locator.find(f"masters/{source_info.name_u}/shape/14")
    if source_top_shape is None or source_upper_line is None or source_lower_line is None:
        raise ValueError("Could not locate the NMOS arrow geometry source shapes.")

    source_width = _cell_float(source_top_shape, "Width")
    width_val = source_width * 0.12
    height_val = source_width * 0.24

    masters_tree = bridge.get_xml("visio/masters/masters.xml")
    rels_tree = bridge.get_xml("visio/masters/_rels/masters.xml.rels")
    content_types_tree = bridge.get_xml("[Content_Types].xml")
    if masters_tree is None or rels_tree is None or content_types_tree is None:
        raise ValueError("The Visio package is missing one of the required master registry parts.")

    new_master_id = _next_master_id(bridge)
    new_rel_id = _next_rel_id(rels_tree.getroot())
    new_master_path = _next_master_part(bridge)

    source_master_elem = _find_master_elem(masters_tree.getroot(), source_info)
    new_master_elem = copy.deepcopy(source_master_elem)
    new_master_elem.set("ID", new_master_id)
    new_master_elem.set("NameU", name_u)
    new_master_elem.set("IsCustomNameU", "1")
    new_master_elem.set("Name", name)
    new_master_elem.set("IsCustomName", "1")
    new_master_elem.set("UniqueID", "{" + str(uuid.uuid4()).upper() + "}")
    new_master_elem.set("BaseID", "{" + str(uuid.uuid4()).upper() + "}")

    page_sheet = find_child(new_master_elem, "PageSheet")
    if page_sheet is not None:
        _update_page_sheet(page_sheet, width_val, height_val)

    rel_elem = find_child(new_master_elem, "Rel")
    if rel_elem is None:
        rel_elem = ET.SubElement(new_master_elem, q("Rel"))
    rel_elem.set(f"{{{R_NS}}}id", new_rel_id)

    masters_tree.getroot().append(new_master_elem)
    bridge.mark_modified("visio/masters/masters.xml")

    rels_root = rels_tree.getroot()
    rels_root.append(
        ET.Element(
            rq("Relationship"),
            {
                "Id": new_rel_id,
                "Type": _RT_MASTER,
                "Target": new_master_path.rsplit("/", 1)[-1],
            },
        )
    )
    bridge.mark_modified("visio/masters/_rels/masters.xml.rels")

    ct_root = content_types_tree.getroot()
    ct_root.append(
        ET.Element(
            f"{{{CONTENT_TYPES_NS}}}Override",
            {
                "PartName": f"/{new_master_path}",
                "ContentType": "application/vnd.ms-visio.master+xml",
            },
        )
    )
    bridge.mark_modified("[Content_Types].xml")

    master_contents = _build_arrow_master_contents(
        source_top_shape,
        source_upper_line,
        source_lower_line,
        name=name,
        name_u=name_u,
        width_val=width_val,
        height_val=height_val,
    )
    bridge.update_xml(new_master_path, master_contents)

    info = MasterInfo(
        master_id=new_master_id,
        name_u=name_u,
        name=name,
        rel_id=new_rel_id,
        xml_path=new_master_path,
    )
    bridge.masters.append(info)
    bridge.mark_formula_cache_dirty(f"masters/{name_u}", "master", reason="create_arrow_master")
    return info

"""Low-level Visio XML helper functions for Visio Bridge.

Covers namespace constants, element lookup/creation, and ShapeSheet cell operations.
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

VISIO_NS = "http://schemas.microsoft.com/office/visio/2012/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# DrawingML namespace — used by visio/theme/theme*.xml (a: prefix)
# xml_utils Cell/Section helpers do NOT apply to this namespace.
DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

# Dublin Core / OPC namespaces — used by docProps/core.xml
DC_NS  = "http://purl.org/dc/elements/1.1/"
DCP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"

ET.register_namespace("", VISIO_NS)
ET.register_namespace("r", R_NS)


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

def q(name: str) -> str:
    """Qualify *name* with the main Visio namespace."""
    return f"{{{VISIO_NS}}}{name}"


def rq(name: str) -> str:
    """Qualify *name* with the OPC relationships namespace."""
    return f"{{{REL_NS}}}{name}"


def local(tag: str) -> str:
    """Strip the namespace prefix from a qualified tag string."""
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------------------
# ZIP / XML I/O
# ---------------------------------------------------------------------------

def read_xml(zf: zipfile.ZipFile, path: str) -> ET.ElementTree:
    return ET.ElementTree(ET.fromstring(zf.read(path)))


def tostring(tree: ET.ElementTree) -> bytes:
    return ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# Element lookup and creation
# ---------------------------------------------------------------------------

def find_child(elem: ET.Element, tag: str, **attrs: str) -> ET.Element | None:
    """Return the first child whose local tag and all *attrs* match."""
    for child in elem:
        if local(child.tag) != tag:
            continue
        if all(child.get(k) == v for k, v in attrs.items()):
            return child
    return None


def ensure_child(elem: ET.Element, tag: str, **attrs: str) -> ET.Element:
    """Return the matching child, creating it (with *attrs*) if absent."""
    found = find_child(elem, tag, **attrs)
    if found is not None:
        return found
    child = ET.SubElement(elem, q(tag))
    for key, value in attrs.items():
        child.set(key, value)
    return child


def remove_children(elem: ET.Element, tag: str, **attrs: str) -> None:
    """Remove all children whose local tag and *attrs* match."""
    for child in list(elem):
        if local(child.tag) != tag:
            continue
        if all(child.get(k) == v for k, v in attrs.items()):
            elem.remove(child)


# ---------------------------------------------------------------------------
# ShapeSheet Cell helpers
# ---------------------------------------------------------------------------

def get_cell(elem: ET.Element, name: str) -> ET.Element | None:
    return find_child(elem, "Cell", N=name)


def set_cell(
    elem: ET.Element,
    name: str,
    value: str | None = None,
    formula: str | None = None,
    unit: str | None = None,
) -> None:
    """Set (or create) a Cell child with the given *name*, *value*, *formula*, and *unit*."""
    cell = get_cell(elem, name)
    if cell is None:
        cell = ET.SubElement(elem, q("Cell"), {"N": name})
    if value is not None:
        cell.set("V", value)
    if formula is not None:
        if formula:
            cell.set("F", formula)
        else:
            cell.attrib.pop("F", None)
    elif value is not None:
        cell.attrib.pop("F", None)
    if unit is not None:
        cell.set("U", unit)


# ---------------------------------------------------------------------------
# ShapeSheet Section helpers
# ---------------------------------------------------------------------------

def get_section(elem: ET.Element, name: str) -> ET.Element | None:
    return find_child(elem, "Section", N=name)


def ensure_section(elem: ET.Element, name: str) -> ET.Element:
    return ensure_child(elem, "Section", N=name)


def remove_section(elem: ET.Element, name: str) -> None:
    remove_children(elem, "Section", N=name)


# ---------------------------------------------------------------------------
# User-defined row helpers
# ---------------------------------------------------------------------------

def get_user_row(shape: ET.Element, row_name: str) -> ET.Element | None:
    section = get_section(shape, "User")
    if section is None:
        return None
    return find_child(section, "Row", N=row_name)


def set_user_row(
    shape: ET.Element,
    row_name: str,
    formula: str | None,
    value: str = "0",
    unit: str | None = None,
) -> None:
    """Create or update a User-section row with a Value cell and a Prompt cell."""
    section = ensure_section(shape, "User")
    row = get_user_row(shape, row_name)
    if row is None:
        row = ET.SubElement(section, q("Row"), {"N": row_name})
    cell = find_child(row, "Cell", N="Value")
    if cell is None:
        cell = ET.SubElement(row, q("Cell"), {"N": "Value"})
    cell.set("V", value)
    if formula:
        cell.set("F", formula)
    else:
        cell.attrib.pop("F", None)
    if unit is not None:
        cell.set("U", unit)
    prompt = find_child(row, "Cell", N="Prompt")
    if prompt is None:
        prompt = ET.SubElement(row, q("Cell"), {"N": "Prompt"})
    prompt.set("V", "")

"""Element locator implementation for finding XML elements using a standard path query.

Supported path formats
-----------------------
  masters/<name_or_id>
  masters/<name_or_id>/shape/<id>
  masters/<name_or_id>/shape/<id>/cell/<cell_name>
  masters/<name_or_id>/shape/<id>/section/<section_name>
  masters/<name_or_id>/shape/<id>/section/<section_name>/row/<ix_or_n>

  pages/<name_or_id>
  pages/<name_or_id>/shape/<id>
  ... (same cell/section/row sub-paths as masters)

  document
    → root <VisioDocument> element of visio/document.xml

  document/sheet
    → <DocumentSheet> child (shortcut for common access pattern)

  theme/<index_or_name>
    → root <a:theme> element from the nth theme file (0-based index)
      or matching by theme name (e.g. "简单")
    ⚠ DrawingML namespace — xml_utils Cell/Section helpers do NOT apply here.
      Use ET directly with namespace {http://…/drawingml/2006/main}.

  windows
    → root <Windows> element of visio/windows.xml
      (uses Visio namespace — xml_utils helpers apply)

  doc_props/core
    → root element of docProps/core.xml   (Dublin Core, cp:/dc: namespaces)

  doc_props/app
    → root element of docProps/app.xml    (Office extended-props namespace)

  doc_props/custom
    → root element of docProps/custom.xml (Office custom-props namespace)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from .bridge import VisioBridge
from .xml_utils import local, find_child


# ---------------------------------------------------------------------------
# Shape recursive search (unchanged)
# ---------------------------------------------------------------------------

def find_shape_recursively(elem: ET.Element, shape_id: str) -> ET.Element | None:
    """Recursively search for a Shape element with a matching ID attribute."""
    if local(elem.tag) == "Shape" and elem.get("ID") == shape_id:
        return elem
    for child in elem:
        found = find_shape_recursively(child, shape_id)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# Path resolver
# ---------------------------------------------------------------------------

def resolve_path(bridge: VisioBridge, path: str) -> tuple[ET.Element, str] | None:
    """Resolve a locator path string into a (Element, xml_file_path) tuple.

    Returns None if any component of the path cannot be found.
    """
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return None

    category = parts[0]

    # ------------------------------------------------------------------ #
    #  masters / pages  (existing full navigation)                        #
    # ------------------------------------------------------------------ #
    if category in ("masters", "pages"):
        if len(parts) < 2:
            return None
        target_name = parts[1]
        xml_path    = None
        root_element = None

        if category == "masters":
            info = None
            for m in bridge.masters:
                if m.name_u == target_name or m.name == target_name or m.master_id == target_name:
                    info = m
                    break
            if not info:
                return None
            xml_path = info.xml_path
        else:  # pages
            info = None
            for p in bridge.pages:
                if p.name_u == target_name or p.name == target_name or p.page_id == target_name:
                    info = p
                    break
            if not info:
                return None
            xml_path = info.xml_path

        tree = bridge.get_xml(xml_path)
        if tree is None:
            return None
        root_element = tree.getroot()

        # Traverse remaining path tokens (shape / cell / section / row / text)
        current_elem = root_element
        idx = 2
        while idx < len(parts):
            token = parts[idx]

            if token == "shape":
                if idx + 1 >= len(parts):
                    return None
                shape_id = parts[idx + 1]
                current_elem = find_shape_recursively(current_elem, shape_id)
                if current_elem is None:
                    return None
                idx += 2

            elif token == "cell":
                if idx + 1 >= len(parts):
                    return None
                cell_name = parts[idx + 1]
                current_elem = find_child(current_elem, "Cell", N=cell_name)
                if current_elem is None:
                    return None
                idx += 2

            elif token == "section":
                if idx + 1 >= len(parts):
                    return None
                section_name = parts[idx + 1]
                current_elem = find_child(current_elem, "Section", N=section_name)
                if current_elem is None:
                    return None
                idx += 2

            elif token == "row":
                if idx + 1 >= len(parts):
                    return None
                row_identifier = parts[idx + 1]
                row_elem = None
                for child in current_elem:
                    if local(child.tag) == "Row":
                        if (child.get("N") == row_identifier
                                or child.get("IX") == row_identifier
                                or child.get("T")  == row_identifier):
                            row_elem = child
                            break
                if row_elem is None:
                    return None
                current_elem = row_elem
                idx += 2

            elif token == "text":
                current_elem = find_child(current_elem, "Text")
                if current_elem is None:
                    return None
                idx += 1

            else:
                return None  # unrecognised token

        return current_elem, xml_path

    # ------------------------------------------------------------------ #
    #  document                                                            #
    #  document/sheet   → <DocumentSheet>                                 #
    # ------------------------------------------------------------------ #
    elif category == "document":
        xml_path = bridge.document_path
        tree = bridge.get_xml(xml_path)
        if tree is None:
            return None
        root = tree.getroot()

        if len(parts) == 1:
            # Return the raw <VisioDocument> root
            return root, xml_path

        sub = parts[1]
        if sub == "sheet":
            # Shortcut: return <DocumentSheet>
            sheet = find_child(root, "DocumentSheet")
            if sheet is None:
                return None
            return sheet, xml_path

        return None   # unrecognised sub-path

    # ------------------------------------------------------------------ #
    #  theme/<index_or_name>                                              #
    # ------------------------------------------------------------------ #
    elif category == "theme":
        if not bridge.themes:
            return None
        if len(parts) < 2:
            # Default: first theme
            t = bridge.themes[0]
        else:
            key = parts[1]
            t = None
            # Try integer index first
            try:
                idx_val = int(key)
                if 0 <= idx_val < len(bridge.themes):
                    t = bridge.themes[idx_val]
            except ValueError:
                pass
            # Then try name match
            if t is None:
                for th in bridge.themes:
                    if th.name == key:
                        t = th
                        break
            if t is None:
                return None

        tree = bridge.get_xml(t.xml_path)
        if tree is None:
            return None
        # Root IS the <a:theme> element
        return tree.getroot(), t.xml_path

    # ------------------------------------------------------------------ #
    #  windows                                                             #
    # ------------------------------------------------------------------ #
    elif category == "windows":
        if bridge.windows is None:
            return None
        xml_path = bridge.windows.xml_path
        tree = bridge.get_xml(xml_path)
        if tree is None:
            return None
        return tree.getroot(), xml_path

    # ------------------------------------------------------------------ #
    #  doc_props/<core|app|custom>                                         #
    # ------------------------------------------------------------------ #
    elif category == "doc_props":
        if len(parts) < 2:
            return None
        sub = parts[1]
        dp  = bridge.doc_props

        if sub == "core":
            xml_path = dp.core_path
        elif sub == "app":
            xml_path = dp.app_path
        elif sub == "custom":
            xml_path = dp.custom_path
        else:
            return None

        if xml_path is None:
            return None
        tree = bridge.get_xml(xml_path)
        if tree is None:
            return None
        return tree.getroot(), xml_path

    return None


# ---------------------------------------------------------------------------
# ElementLocator — public class
# ---------------------------------------------------------------------------

class ElementLocator:
    """High-level wrapper around resolve_path for AI / skill script use."""

    def __init__(self, bridge: VisioBridge):
        self.bridge = bridge

    def find(self, path: str) -> ET.Element | None:
        """Return the element at *path*, or None if not found."""
        result = resolve_path(self.bridge, path)
        return result[0] if result else None

    def find_with_path(self, path: str) -> tuple[ET.Element, str] | None:
        """Return (element, xml_file_path) or None."""
        return resolve_path(self.bridge, path)

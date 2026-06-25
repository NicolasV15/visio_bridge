"""Core VisioBridge class to handle ZIP file structure and XML loading/saving.

All XML parts in a .vsdx/.vstx/.vssx file (which is a ZIP archive) are
discovered via OPC relationship chains and registered into structured Info
objects.  Every Info object exposes an ``xml_path`` attribute that can be
passed directly to ``bridge.get_xml(xml_path)`` for 100 % stable access.

Relationship chain discovery order
------------------------------------
  _rels/.rels
    └─ rType: .../document        → visio/document.xml   (DocumentSheet)
    └─ rType: .../core-properties → docProps/core.xml    (Dublin-Core meta)
    └─ rType: .../extended-props  → docProps/app.xml     (App-level meta)
    └─ rType: .../custom-props    → docProps/custom.xml  (Custom props)

  visio/_rels/document.xml.rels
    └─ rType: .../masters  → visio/masters/masters.xml
    └─ rType: .../pages    → visio/pages/pages.xml
    └─ rType: .../windows  → visio/windows.xml
    └─ rType: .../theme    → visio/theme/theme1.xml (DrawingML, a: namespace)

  visio/masters/_rels/masters.xml.rels
    └─ rType: .../master   → visio/masters/master*.xml  (one per Master)

  visio/pages/_rels/pages.xml.rels
    └─ rType: .../page     → visio/pages/page*.xml      (one per Page)
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from .xml_utils import read_xml, tostring, local, find_child, R_NS

# ---------------------------------------------------------------------------
# OPC / Visio relationship type constants
# ---------------------------------------------------------------------------
_RT_DOCUMENT = "http://schemas.microsoft.com/visio/2010/relationships/document"
_RT_MASTERS  = "http://schemas.microsoft.com/visio/2010/relationships/masters"
_RT_MASTER   = "http://schemas.microsoft.com/visio/2010/relationships/master"
_RT_PAGES    = "http://schemas.microsoft.com/visio/2010/relationships/pages"
_RT_PAGE     = "http://schemas.microsoft.com/visio/2010/relationships/page"
_RT_WINDOWS  = "http://schemas.microsoft.com/visio/2010/relationships/windows"
_RT_THEME    = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
_RT_CORE     = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
_RT_APP      = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
_RT_CUSTOM   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"


# ---------------------------------------------------------------------------
# Info data classes — one per logical "part" of the Visio file
# ---------------------------------------------------------------------------

class MasterInfo:
    """Represents one entry in visio/masters/masters.xml."""
    def __init__(self, master_id: str, name_u: str, name: str,
                 rel_id: str, xml_path: str):
        self.master_id = master_id
        self.name_u    = name_u
        self.name      = name
        self.rel_id    = rel_id
        self.xml_path  = xml_path   # e.g. "visio/masters/master1.xml"

    def __repr__(self) -> str:
        return f"MasterInfo(ID={self.master_id}, NameU={self.name_u}, Path={self.xml_path})"


class PageInfo:
    """Represents one entry in visio/pages/pages.xml."""
    def __init__(self, page_id: str, name_u: str, name: str,
                 rel_id: str, xml_path: str):
        self.page_id  = page_id
        self.name_u   = name_u
        self.name     = name
        self.rel_id   = rel_id
        self.xml_path = xml_path    # e.g. "visio/pages/page1.xml"

    def __repr__(self) -> str:
        return f"PageInfo(ID={self.page_id}, NameU={self.name_u}, Path={self.xml_path})"


class ThemeInfo:
    """Represents a DrawingML theme file (visio/theme/theme*.xml).

    Note: theme XML uses the ``a:`` namespace
    (http://schemas.openxmlformats.org/drawingml/2006/main), NOT the Visio
    namespace.  xml_utils helpers that rely on VISIO_NS do NOT apply here.
    """
    def __init__(self, rel_id: str, xml_path: str, name: str = ""):
        self.rel_id   = rel_id
        self.xml_path = xml_path    # e.g. "visio/theme/theme1.xml"
        self.name     = name        # value of the <a:theme name="..."> attribute

    def __repr__(self) -> str:
        return f"ThemeInfo(name={self.name!r}, Path={self.xml_path})"


class WindowsInfo:
    """Represents the visio/windows.xml part (Visio window layout state).

    Root element: <Windows> containing <Window> children.
    Uses the main Visio namespace — xml_utils helpers apply.
    """
    def __init__(self, rel_id: str, xml_path: str):
        self.rel_id   = rel_id
        self.xml_path = xml_path    # always "visio/windows.xml" in practice

    def __repr__(self) -> str:
        return f"WindowsInfo(Path={self.xml_path})"


class DocPropsInfo:
    """Wraps the three standard OPC document-property parts.

    Attributes
    ----------
    core_path   : str | None  — docProps/core.xml   (Dublin Core: title, author …)
    app_path    : str | None  — docProps/app.xml    (App: AppVersion, Pages count …)
    custom_path : str | None  — docProps/custom.xml (user-defined key/value pairs)
    """
    def __init__(self):
        self.core_path:   str | None = None
        self.app_path:    str | None = None
        self.custom_path: str | None = None

    def __repr__(self) -> str:
        parts = []
        if self.core_path:   parts.append(f"core={self.core_path}")
        if self.app_path:    parts.append(f"app={self.app_path}")
        if self.custom_path: parts.append(f"custom={self.custom_path}")
        return f"DocPropsInfo({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Helper: parse a .rels file into a {rel_type: target_path} mapping
# ---------------------------------------------------------------------------

def _parse_rels(tree: ET.ElementTree) -> dict[str, str]:
    """Return {Type: Target} for every <Relationship> in a .rels tree."""
    result: dict[str, str] = {}
    for rel in tree.getroot():
        if local(rel.tag) == "Relationship":
            rtype  = rel.get("Type", "")
            target = rel.get("Target", "")
            rel_id = rel.get("Id", "")
            # Store by type; also keep Id for callers that need it
            result[rtype]  = target
            result[rel_id] = target   # secondary index by Id
    return result


# ---------------------------------------------------------------------------
# VisioBridge — main class
# ---------------------------------------------------------------------------

class VisioBridge:
    """High-level accessor for all XML parts inside a Visio ZIP archive.

    After construction every discoverable part is registered in one of:
      self.masters     list[MasterInfo]
      self.pages       list[PageInfo]
      self.themes      list[ThemeInfo]
      self.windows     WindowsInfo | None
      self.doc_props   DocPropsInfo

    The document XML is always addressable at:
      self.document_path  →  "visio/document.xml"

    Use ``parts_manifest()`` to get a complete structured map of all parts,
    suitable for AI navigation without any further raw-XML parsing.
    """

    def __init__(self, file_path: str):
        self.file_path  = file_path
        self.file_type  = os.path.splitext(file_path)[1].lower()
        if self.file_type not in (".vsdx", ".vstx", ".vssx"):
            raise ValueError(
                f"Unsupported Visio file type: {self.file_type}. "
                "Only .vsdx, .vstx, and .vssx are supported."
            )

        self.xml_cache:      dict[str, ET.ElementTree] = {}
        self.modified_files: set[str]                  = set()
        self.formula_cache_dirty_scopes: dict[tuple[str, str], str] = {}

        # --- registered parts ---
        self.document_path: str           = "visio/document.xml"
        self.masters:       list[MasterInfo] = []
        self.pages:         list[PageInfo]   = []
        self.themes:        list[ThemeInfo]  = []
        self.windows:       WindowsInfo | None = None
        self.doc_props:     DocPropsInfo   = DocPropsInfo()

        self._load()

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load and cache all XML / .rels files from the ZIP, then parse parts."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")

        with zipfile.ZipFile(self.file_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".xml") or name.endswith(".rels"):
                    try:
                        self.xml_cache[name] = read_xml(zf, name)
                    except Exception:
                        pass  # skip corrupted / un-parseable entries

        # Follow OPC relationship chains to populate Info objects
        self._parse_root_rels()        # finds document, docProps
        self._parse_document_rels()    # finds masters, pages, theme, windows
        self._parse_masters()          # populates self.masters
        self._parse_pages()            # populates self.pages
        self._parse_themes()           # populates self.themes (name attribute)

    def _parse_root_rels(self) -> None:
        """Parse _rels/.rels → discover document_path and docProps."""
        rels_tree = self.xml_cache.get("_rels/.rels")
        if rels_tree is None:
            return
        for rel in rels_tree.getroot():
            if local(rel.tag) != "Relationship":
                continue
            rtype  = rel.get("Type", "")
            target = rel.get("Target", "")
            if rtype == _RT_DOCUMENT:
                self.document_path = target.lstrip("/")
            elif rtype == _RT_CORE:
                self.doc_props.core_path = target.lstrip("/")
            elif rtype == _RT_APP:
                self.doc_props.app_path = target.lstrip("/")
            elif rtype == _RT_CUSTOM:
                self.doc_props.custom_path = target.lstrip("/")

    def _parse_document_rels(self) -> None:
        """Parse visio/_rels/document.xml.rels → discover masters, pages, theme, windows."""
        # The rels file is always alongside document.xml in a _rels/ subfolder
        doc_dir  = os.path.dirname(self.document_path)          # "visio"
        rels_key = os.path.join(doc_dir, "_rels",
                                os.path.basename(self.document_path) + ".rels")
        rels_key = rels_key.replace("\\", "/")
        rels_tree = self.xml_cache.get(rels_key)
        if rels_tree is None:
            return

        for rel in rels_tree.getroot():
            if local(rel.tag) != "Relationship":
                continue
            rtype  = rel.get("Type", "")
            target = rel.get("Target", "")
            rel_id = rel.get("Id", "")

            # Target is relative to doc_dir (e.g. "visio")
            abs_path = os.path.normpath(
                os.path.join(doc_dir, target)
            ).replace("\\", "/")

            if rtype == _RT_WINDOWS:
                self.windows = WindowsInfo(rel_id=rel_id, xml_path=abs_path)
            elif rtype == _RT_THEME:
                # Name will be populated in _parse_themes()
                self.themes.append(ThemeInfo(rel_id=rel_id, xml_path=abs_path))

    def _parse_masters(self) -> None:
        """Populate self.masters from masters.xml + its .rels file."""
        masters_tree = self.xml_cache.get("visio/masters/masters.xml")
        rels_tree    = self.xml_cache.get("visio/masters/_rels/masters.xml.rels")
        if not masters_tree or not rels_tree:
            return

        rels: dict[str, str] = {}
        for rel in rels_tree.getroot():
            if local(rel.tag) == "Relationship":
                rels[rel.get("Id", "")] = rel.get("Target", "")

        for master in masters_tree.getroot():
            if local(master.tag) != "Master":
                continue
            rel_elem = find_child(master, "Rel")
            if rel_elem is None:
                continue
            rel_id = rel_elem.get(f"{{{R_NS}}}id", "")
            target = rels.get(rel_id)
            if not target:
                continue
            xml_path = os.path.normpath(
                os.path.join("visio/masters", target)
            ).replace("\\", "/")
            self.masters.append(MasterInfo(
                master_id = master.get("ID", ""),
                name_u    = master.get("NameU", ""),
                name      = master.get("Name", ""),
                rel_id    = rel_id,
                xml_path  = xml_path,
            ))

    def _parse_pages(self) -> None:
        """Populate self.pages from pages.xml + its .rels file."""
        pages_tree = self.xml_cache.get("visio/pages/pages.xml")
        rels_tree  = self.xml_cache.get("visio/pages/_rels/pages.xml.rels")
        if not pages_tree or not rels_tree:
            return

        rels: dict[str, str] = {}
        for rel in rels_tree.getroot():
            if local(rel.tag) == "Relationship":
                rels[rel.get("Id", "")] = rel.get("Target", "")

        for page in pages_tree.getroot():
            if local(page.tag) != "Page":
                continue
            rel_elem = find_child(page, "Rel")
            if rel_elem is None:
                continue
            rel_id = rel_elem.get(f"{{{R_NS}}}id", "")
            target = rels.get(rel_id)
            if not target:
                continue
            xml_path = os.path.normpath(
                os.path.join("visio/pages", target)
            ).replace("\\", "/")
            self.pages.append(PageInfo(
                page_id  = page.get("ID", ""),
                name_u   = page.get("NameU", ""),
                name     = page.get("Name", ""),
                rel_id   = rel_id,
                xml_path = xml_path,
            ))

    def _parse_themes(self) -> None:
        """Fill in ThemeInfo.name from the <a:theme name="..."> attribute."""
        DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
        for theme_info in self.themes:
            tree = self.xml_cache.get(theme_info.xml_path)
            if tree is None:
                continue
            root = tree.getroot()
            # The root IS the <a:theme> element
            theme_info.name = root.get("name", "")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_xml(self, path: str) -> ET.ElementTree | None:
        """Return the cached ElementTree for the given ZIP-relative path."""
        return self.xml_cache.get(path)

    def mark_modified(self, path: str) -> None:
        """Flag a cached tree as modified so it will be written on save()."""
        self.modified_files.add(path)

    def mark_formula_cache_dirty(self, target: str, scope: str, reason: str | None = None) -> None:
        """Flag a formula-cache scope for recalculation before save()."""
        if scope not in {"master", "instance"}:
            raise ValueError(f"Unsupported formula-cache scope: {scope}")
        self.formula_cache_dirty_scopes[(scope, target)] = reason or ""

    def clear_formula_cache_dirty(self, target: str, scope: str) -> None:
        """Clear one pending formula-cache dirty scope after a successful flush."""
        self.formula_cache_dirty_scopes.pop((scope, target), None)

    def flush_formula_cache(self, materialize_inherited: bool = True) -> list:
        """Recalculate every pending formula-cache scope.

        Dirty scopes are cleared only after all recalculations complete
        successfully. If any recalculation fails, the dirty registry is left
        intact so a later save or explicit flush cannot silently skip it.
        """
        if not self.formula_cache_dirty_scopes:
            return []

        from .formula_cache import recalculate_formula_cache

        pending = list(self.formula_cache_dirty_scopes.keys())
        results = []
        for scope, target in pending:
            results.append(
                recalculate_formula_cache(
                    self,
                    target,
                    scope,
                    materialize_inherited=materialize_inherited,
                )
            )
        for scope, target in pending:
            self.clear_formula_cache_dirty(target, scope)
        return results

    def update_xml(self, path: str, tree: ET.ElementTree) -> None:
        """Replace (or insert) a cached tree and mark it modified."""
        self.xml_cache[path] = tree
        self.mark_modified(path)

    def parts_manifest(self) -> dict:
        """Return a complete structural map of all discovered XML parts.

        The returned dict is designed for AI consumption: every value
        contains an ``xml_path`` that can be passed directly to
        ``bridge.get_xml(xml_path)`` for stable, 100 % reliable access.

        Structure
        ---------
        {
          "document": {
              "xml_path": "visio/document.xml",
              "description": "DocumentSheet — global User cells (Scale, M, LW …)"
          },
          "masters": [
              {"master_id": "1", "name_u": "VDD", "xml_path": "visio/masters/master1.xml"},
              ...
          ],
          "pages": [
              {"page_id": "0", "name_u": "Page-1", "xml_path": "visio/pages/page1.xml"},
              ...
          ],
          "themes": [
              {"name": "简单", "xml_path": "visio/theme/theme1.xml",
               "namespace": "http://schemas.openxmlformats.org/drawingml/2006/main",
               "note": "DrawingML — use a: prefix; xml_utils Cell helpers do NOT apply"}
          ],
          "windows": {
              "xml_path": "visio/windows.xml",
              "description": "Visio window layout state — uses main Visio namespace"
          },
          "doc_props": {
              "core":   {"xml_path": "docProps/core.xml",   "description": "Dublin Core: title, creator, created …"},
              "app":    {"xml_path": "docProps/app.xml",    "description": "App-level: AppVersion, Pages, ScaleCrop …"},
              "custom": {"xml_path": "docProps/custom.xml", "description": "User-defined custom document properties"}
          }
        }
        """
        manifest: dict = {}

        # Document
        manifest["document"] = {
            "xml_path":    self.document_path,
            "description": (
                "DocumentSheet — global User-defined cells "
                "(e.g. User.Scale, User.M, User.LW). "
                "Access via find_child(root, 'DocumentSheet') then get/set_section/cell."
            ),
        }

        # Masters
        manifest["masters"] = [
            {
                "master_id": m.master_id,
                "name_u":    m.name_u,
                "name":      m.name,
                "xml_path":  m.xml_path,
            }
            for m in self.masters
        ]

        # Pages
        manifest["pages"] = [
            {
                "page_id":  p.page_id,
                "name_u":   p.name_u,
                "name":     p.name,
                "xml_path": p.xml_path,
            }
            for p in self.pages
        ]

        # Themes
        manifest["themes"] = [
            {
                "name":      t.name,
                "xml_path":  t.xml_path,
                "namespace": "http://schemas.openxmlformats.org/drawingml/2006/main",
                "note": (
                    "DrawingML namespace (a: prefix). "
                    "xml_utils Cell/Section helpers do NOT apply. "
                    "Use ET directly: root.find('{...}clrScheme') etc."
                ),
            }
            for t in self.themes
        ]

        # Windows
        if self.windows:
            manifest["windows"] = {
                "xml_path":    self.windows.xml_path,
                "description": (
                    "Visio window layout state (<Windows> root, <Window> children). "
                    "Uses main Visio namespace — xml_utils helpers apply."
                ),
            }
        else:
            manifest["windows"] = None

        # DocProps
        dp = self.doc_props
        manifest["doc_props"] = {
            "core": {
                "xml_path":    dp.core_path,
                "description": "OPC core properties: dc:title, dc:creator, dcterms:created …",
            } if dp.core_path else None,
            "app": {
                "xml_path":    dp.app_path,
                "description": "App-level properties: AppVersion, Pages, ScaleCrop …",
            } if dp.app_path else None,
            "custom": {
                "xml_path":    dp.custom_path,
                "description": "User-defined custom document properties (vt:lpwstr / vt:i4 values).",
            } if dp.custom_path else None,
        }

        return manifest

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, output_path: str | None = None, *, skip_formula_cache: bool = False) -> None:
        """Write all modified XML parts back into the Visio ZIP archive."""
        target_path = output_path or self.file_path
        if not skip_formula_cache:
            self.flush_formula_cache()

        fd, temp_path = tempfile.mkstemp(suffix=self.file_type)
        os.close(fd)

        try:
            with zipfile.ZipFile(self.file_path, "r") as zin:
                with zipfile.ZipFile(temp_path, "w",
                                     compression=zipfile.ZIP_DEFLATED) as zout:
                    existing_files: set[str] = set()
                    for item in zin.infolist():
                        existing_files.add(item.filename)
                        if (item.filename in self.modified_files
                                and item.filename in self.xml_cache):
                            data = tostring(self.xml_cache[item.filename])
                            zout.writestr(item, data)
                        else:
                            zout.writestr(item, zin.read(item.filename))
                    for path in sorted(self.modified_files):
                        if path in existing_files:
                            continue
                        tree = self.xml_cache.get(path)
                        if tree is None:
                            continue
                        zout.writestr(path, tostring(tree))
            shutil.move(temp_path, target_path)
            self.modified_files.clear()
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

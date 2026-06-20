"""Design-layer context and capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import xml.etree.ElementTree as ET

from ..core.bridge import VisioBridge
from ..core.locator import ElementLocator
from ..core.xml_utils import get_cell, local, find_child
from ..skill.doc_settings import to_settings_skill
from ..skill.symbol_editor import to_skill


ReaderAdapter = Callable[["DesignContext"], None]
CommandAdapter = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


@dataclass
class DesignTarget:
    """A normalized Visio design target extracted from a file."""

    kind: str
    path: str
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    element: ET.Element | None = None
    info: Any = None


@dataclass
class DesignCapabilityRegistry:
    """Registry for reader and command adapters used by the design layer."""

    readers: dict[str, ReaderAdapter] = field(default_factory=dict)
    command_adapters: dict[str, CommandAdapter] = field(default_factory=dict)

    def register_reader(self, name: str, reader: ReaderAdapter) -> None:
        self.readers[name] = reader

    def register_command_adapter(self, executor: str, adapter: CommandAdapter) -> None:
        self.command_adapters[executor] = adapter

    def adapt_commands(self, executor: str, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        adapter = self.command_adapters.get(executor)
        if adapter is None:
            return commands
        return adapter(commands)


@dataclass
class DesignContext:
    """Read-only context shared by all design rules."""

    bridge: VisioBridge
    locator: ElementLocator
    registry: DesignCapabilityRegistry
    manifest: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    masters: dict[str, DesignTarget] = field(default_factory=dict)
    pages: dict[str, DesignTarget] = field(default_factory=dict)
    instances: dict[str, DesignTarget] = field(default_factory=dict)
    styles: dict[str, DesignTarget] = field(default_factory=dict)
    available_capabilities: set[str] = field(default_factory=set)
    reader_errors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_bridge(
        cls,
        bridge: VisioBridge,
        registry: DesignCapabilityRegistry | None = None,
    ) -> "DesignContext":
        active_registry = registry or default_design_registry()
        context = cls(
            bridge=bridge,
            locator=ElementLocator(bridge),
            registry=active_registry,
            manifest=bridge.parts_manifest(),
        )
        context.available_capabilities.add("core")

        for name, reader in active_registry.readers.items():
            try:
                reader(context)
                context.available_capabilities.add(name)
            except Exception as exc:  # keep one broken reader from stopping audit
                context.reader_errors[name] = str(exc)

        return context


def default_design_registry() -> DesignCapabilityRegistry:
    """Return the default registry backed by the current phase 1/2 APIs."""

    registry = DesignCapabilityRegistry()
    registry.register_reader("settings", _read_settings)
    registry.register_reader("styles", _read_styles)
    registry.register_reader("masters", _read_masters)
    registry.register_reader("pages", _read_pages)

    # Current command shapes already match the lower-level SKILL executors.
    registry.register_command_adapter("doc_page_settings", lambda commands: commands)
    registry.register_command_adapter("symbol_editor", lambda commands: commands)
    registry.register_command_adapter("instance_manager", lambda commands: commands)
    return registry


def _read_settings(context: DesignContext) -> None:
    context.settings = to_settings_skill(context.bridge)


def _read_styles(context: DesignContext) -> None:
    doc_tree = context.bridge.get_xml(context.bridge.document_path)
    if doc_tree is None:
        return
    root = doc_tree.getroot()
    stylesheets = find_child(root, "StyleSheets")
    if stylesheets is None:
        return

    for style in stylesheets:
        if local(style.tag) != "StyleSheet":
            continue
        style_id = style.get("ID", "")
        name = style.get("NameU") or style.get("Name") or style_id
        path = f"document/styles/{style_id or name}"
        data = {
            "id": style_id,
            "name_u": style.get("NameU", ""),
            "name": style.get("Name", ""),
            "line_style": style.get("LineStyle", ""),
            "fill_style": style.get("FillStyle", ""),
            "text_style": style.get("TextStyle", ""),
        "cells": {
            cell_name: data
            for cell_name in (
                "LineWeight",
                "LineColor",
                "LinePattern",
                "Rounding",
                "BeginArrow",
                "EndArrow",
                "LineCap",
                "ShapeRouteStyle",
                "ConLineRouteExt",
            )
            for data in [_cell_data(style, cell_name)]
            if data
        },
        }
        target = DesignTarget(
            kind="style",
            path=path,
            name=name,
            data=data,
            element=style,
        )
        context.styles[name] = target
        if style_id:
            context.styles[style_id] = target


def _read_masters(context: DesignContext) -> None:
    master_page_sheets = _read_master_page_sheets(context)
    for master in context.bridge.masters:
        name = master.name_u or master.name or master.master_id
        path = f"masters/{name}"
        root = context.locator.find(path)
        if root is None:
            context.masters[name] = DesignTarget(
                kind="master",
                path=path,
                name=name,
                info=master,
                data={"error": "master root not found"},
            )
            continue

        shape_path, shape = _find_master_top_shape(context, name, root)
        data: dict[str, Any] = {}
        if shape is not None:
            try:
                data = to_skill(shape)
            except Exception as exc:
                data = {"error": str(exc)}
        else:
            data = {"error": "top shape not found"}
        data["page_sheet"] = master_page_sheets.get(master.master_id, {})

        context.masters[name] = DesignTarget(
            kind="master",
            path=shape_path or path,
            name=name,
            data=data,
            element=shape,
            info=master,
        )


def _read_master_page_sheets(context: DesignContext) -> dict[str, dict[str, Any]]:
    masters_tree = context.bridge.get_xml("visio/masters/masters.xml")
    if masters_tree is None:
        return {}

    page_sheets: dict[str, dict[str, Any]] = {}
    for master in masters_tree.getroot():
        if local(master.tag) != "Master":
            continue
        master_id = master.get("ID", "")
        if not master_id:
            continue
        page_sheet = find_child(master, "PageSheet")
        if page_sheet is None:
            page_sheets[master_id] = {}
            continue
        page_sheets[master_id] = {
            "line_style": page_sheet.get("LineStyle", ""),
            "fill_style": page_sheet.get("FillStyle", ""),
            "text_style": page_sheet.get("TextStyle", ""),
            "cells": {
                cell_name: data
                for cell_name in (
                    "PageWidth",
                    "PageHeight",
                    "PageScale",
                    "DrawingScale",
                    "DrawingSizeType",
                    "DrawingScaleType",
                )
                for data in [_cell_data(page_sheet, cell_name)]
                if data
            },
        }
    return page_sheets


def _read_pages(context: DesignContext) -> None:
    for page in context.bridge.pages:
        name = page.name_u or page.name or page.page_id
        path = f"pages/{name}"
        root = context.locator.find(path)
        page_target = DesignTarget(
            kind="page",
            path=path,
            name=name,
            element=root,
            info=page,
            data={"instances": []},
        )
        context.pages[name] = page_target
        if root is None:
            page_target.data["error"] = "page root not found"
            continue

        for shape in _iter_shapes(root):
            shape_id = shape.get("ID", "")
            if not shape_id:
                continue
            shape_path = f"{path}/shape/{shape_id}"
            data = _summarize_instance(shape)
            target = DesignTarget(
                kind="instance",
                path=shape_path,
                name=data.get("name", ""),
                data=data,
                element=shape,
                info=page,
            )
            context.instances[shape_path] = target
            page_target.data["instances"].append(shape_path)


def _find_master_top_shape(
    context: DesignContext,
    master_name: str,
    root: ET.Element,
) -> tuple[str | None, ET.Element | None]:
    preferred_path = f"masters/{master_name}/shape/5"
    preferred = context.locator.find(preferred_path)
    if preferred is not None:
        return preferred_path, preferred

    shapes_container = find_child(root, "Shapes")
    if shapes_container is not None:
        for child in shapes_container:
            if local(child.tag) == "Shape":
                shape_id = child.get("ID", "")
                return f"masters/{master_name}/shape/{shape_id}", child

    for child in root:
        if local(child.tag) == "Shape":
            shape_id = child.get("ID", "")
            return f"masters/{master_name}/shape/{shape_id}", child

    return None, None


def _iter_shapes(elem: ET.Element):
    if local(elem.tag) == "Shape":
        yield elem
    for child in elem:
        yield from _iter_shapes(child)


def _cell_data(elem: ET.Element, name: str) -> dict[str, str]:
    cell = get_cell(elem, name)
    if cell is None:
        return {}
    data: dict[str, str] = {}
    if cell.get("V") is not None:
        data["val"] = cell.get("V", "")
    if cell.get("F") is not None:
        data["formula"] = cell.get("F", "")
    if cell.get("U") is not None:
        data["unit"] = cell.get("U", "")
    return data


def _summarize_instance(shape: ET.Element) -> dict[str, Any]:
    cells = {
        name: _cell_data(shape, name)
        for name in (
            "Width",
            "Height",
            "PinX",
            "PinY",
            "LocPinX",
            "LocPinY",
            "Angle",
            "BeginX",
            "BeginY",
            "EndX",
            "EndY",
            "LineWeight",
            "LineColor",
            "LinePattern",
        )
    }
    cells = {name: data for name, data in cells.items() if data}
    return {
        "id": shape.get("ID", ""),
        "name": shape.get("NameU") or shape.get("Name") or "",
        "type": shape.get("Type", ""),
        "master": shape.get("Master", ""),
        "master_shape": shape.get("MasterShape", ""),
        "line_style": shape.get("LineStyle", ""),
        "fill_style": shape.get("FillStyle", ""),
        "text_style": shape.get("TextStyle", ""),
        "cells": cells,
    }

"""SKILL interface implementation to extract and modify Visio page and document settings."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from ..core.bridge import VisioBridge
from ..core.xml_utils import get_cell, set_cell, get_section, find_child, local, q, set_user_row, ensure_child
from ..desktop import apply_settings_commands_desktop
from .backend import save_xml_fallback_if_requested, try_desktop_backend

def to_settings_skill(bridge: VisioBridge) -> dict:
    """Extract page and document settings from a Visio file into a clean JSON structure."""
    settings = {
        "document": {
            "user_cells": {}
        },
        "pages": []
    }
    
    # 1. Read document settings (User-defined cells)
    doc_tree = bridge.get_xml("visio/document.xml")
    if doc_tree is not None:
        doc_sheet = find_child(doc_tree.getroot(), "DocumentSheet")
        if doc_sheet is not None:
            user_sec = get_section(doc_sheet, "User")
            if user_sec is not None:
                for row in user_sec:
                    if local(row.tag) == "Row":
                        name = row.get("N")
                        if name:
                            val_cell = find_child(row, "Cell", N="Value")
                            if val_cell is not None:
                                c_data = {}
                                if val_cell.get("V") is not None:
                                    c_data["val"] = val_cell.get("V")
                                if val_cell.get("F") is not None:
                                    c_data["formula"] = val_cell.get("F")
                                if val_cell.get("U") is not None:
                                    c_data["unit"] = val_cell.get("U")
                                settings["document"]["user_cells"][name] = c_data

    # 2. Read page settings for all pages
    page_cells = ["PageWidth", "PageHeight", "PageScale", "DrawingScale", "DrawingSizeType", "DrawingScaleType"]
    pages_tree = bridge.get_xml("visio/pages/pages.xml")
    for page in bridge.pages:
        page_sheet = None
        if pages_tree is not None:
            for p_elem in pages_tree.getroot():
                if local(p_elem.tag) == "Page" and p_elem.get("ID") == page.page_id:
                    page_sheet = find_child(p_elem, "PageSheet")
                    break

        page_data = {
            "id": page.page_id,
            "name": page.name_u or page.name,
            "xml_path": page.xml_path,
            "cells": {}
        }
        if page_sheet is not None:
            # 2a. Read standard PageSheet cells
            for c_name in page_cells:
                cell = get_cell(page_sheet, c_name)
                if cell is not None:
                    c_data = {}
                    if cell.get("V") is not None:
                        c_data["val"] = cell.get("V")
                    if cell.get("F") is not None:
                        c_data["formula"] = cell.get("F")
                    if cell.get("U") is not None:
                        c_data["unit"] = cell.get("U")
                    page_data["cells"][c_name] = c_data
            
            # 2b. Read PageSheet User-defined cells (custom page variables)
            page_data["user_cells"] = {}
            user_sec = get_section(page_sheet, "User")
            if user_sec is not None:
                for row in user_sec:
                    if local(row.tag) == "Row":
                        name = row.get("N")
                        if name:
                            val_cell = find_child(row, "Cell", N="Value")
                            if val_cell is not None:
                                c_data = {}
                                if val_cell.get("V") is not None:
                                    c_data["val"] = val_cell.get("V")
                                if val_cell.get("F") is not None:
                                    c_data["formula"] = val_cell.get("F")
                                if val_cell.get("U") is not None:
                                    c_data["unit"] = val_cell.get("U")
                                page_data["user_cells"][name] = c_data
                                
        settings["pages"].append(page_data)

    return settings


def apply_settings_commands(
    bridge: VisioBridge,
    commands: list[dict],
    *,
    backend: str | None = "auto",
    output_path: str | None = None,
    **desktop_kwargs,
) -> None:
    """Apply doc/page setting modification commands.
    
    Supported commands:
      - {"action": "update_doc_user_cell", "name": "M", "value": "1.0", "formula": "...", "unit": "..."}
      - {"action": "update_page_cell", "page": "page_name_or_id", "property": "PageWidth", "value": "11 in", "formula": "..."}
      - {"action": "update_page_user_cell", "page": "page_name_or_id", "name": "VarName", "value": "...", "formula": "...", "unit": "..."}
    """
    handled, _result = try_desktop_backend(
        bridge,
        backend=backend,
        output_path=output_path,
        desktop_apply=lambda output_path=None: apply_settings_commands_desktop(
            bridge.file_path,
            commands,
            output_path=output_path,
            **desktop_kwargs,
        ),
    )
    if handled:
        return

    for cmd in commands:
        action = cmd.get("action")
        
        if action == "update_doc_user_cell":
            doc_tree = bridge.get_xml("visio/document.xml")
            if doc_tree is not None:
                doc_sheet = ensure_child(doc_tree.getroot(), "DocumentSheet")
                name = cmd.get("name")
                val = cmd.get("value")
                formula = cmd.get("formula")
                unit = cmd.get("unit")
                if name:
                    set_user_row(doc_sheet, name, formula or "", val or "0", unit)
                    bridge.mark_modified("visio/document.xml")
                    
        elif action == "update_page_cell":
            page_ref = cmd.get("page")
            prop = cmd.get("property")
            val = cmd.get("value")
            formula = cmd.get("formula")
            unit = cmd.get("unit")
            
            # Find the page
            target_page = None
            for p in bridge.pages:
                if p.name_u == page_ref or p.name == page_ref or p.page_id == page_ref:
                    target_page = p
                    break
            
            if target_page is not None:
                pages_tree = bridge.get_xml("visio/pages/pages.xml")
                if pages_tree is not None:
                    for p_elem in pages_tree.getroot():
                        if local(p_elem.tag) == "Page" and p_elem.get("ID") == target_page.page_id:
                            page_sheet = ensure_child(p_elem, "PageSheet")
                            if prop:
                                set_cell(page_sheet, prop, value=val, formula=formula, unit=unit)
                                bridge.mark_modified("visio/pages/pages.xml")
                            break

        elif action == "update_page_user_cell":
            page_ref = cmd.get("page")
            name = cmd.get("name")
            val = cmd.get("value")
            formula = cmd.get("formula")
            unit = cmd.get("unit")
            
            # Find the page
            target_page = None
            for p in bridge.pages:
                if p.name_u == page_ref or p.name == page_ref or p.page_id == page_ref:
                    target_page = p
                    break
            
            if target_page is not None:
                pages_tree = bridge.get_xml("visio/pages/pages.xml")
                if pages_tree is not None:
                    for p_elem in pages_tree.getroot():
                        if local(p_elem.tag) == "Page" and p_elem.get("ID") == target_page.page_id:
                            page_sheet = ensure_child(p_elem, "PageSheet")
                            if name:
                                set_user_row(page_sheet, name, formula or "", val or "0", unit)
                                bridge.mark_modified("visio/pages/pages.xml")
                            break

        elif action == "delete_doc_user_cell":
            doc_tree = bridge.get_xml("visio/document.xml")
            if doc_tree is not None:
                doc_sheet = find_child(doc_tree.getroot(), "DocumentSheet")
                if doc_sheet is not None:
                    user_sec = get_section(doc_sheet, "User")
                    if user_sec is not None:
                        name = cmd.get("name")
                        for row in list(user_sec):
                            if local(row.tag) == "Row" and row.get("N") == name:
                                user_sec.remove(row)
                                bridge.mark_modified("visio/document.xml")
                                break

        elif action == "delete_page_user_cell":
            page_ref = cmd.get("page")
            name = cmd.get("name")
            target_page = None
            for p in bridge.pages:
                if p.name_u == page_ref or p.name == page_ref or p.page_id == page_ref:
                    target_page = p
                    break
            if target_page is not None:
                pages_tree = bridge.get_xml("visio/pages/pages.xml")
                if pages_tree is not None:
                    for p_elem in pages_tree.getroot():
                        if local(p_elem.tag) == "Page" and p_elem.get("ID") == target_page.page_id:
                            page_sheet = find_child(p_elem, "PageSheet")
                            if page_sheet is not None:
                                user_sec = get_section(page_sheet, "User")
                                if user_sec is not None:
                                    for row in list(user_sec):
                                        if local(row.tag) == "Row" and row.get("N") == name:
                                            user_sec.remove(row)
                                            bridge.mark_modified("visio/pages/pages.xml")
                                            break
                            break

    save_xml_fallback_if_requested(bridge, output_path)


"""Circuit-diagram design profile.

This profile is the first concrete user of the generic design framework.  It
keeps the geometry of each electrical symbol flexible, while checking that
symbols, connectors, and document settings remain scalable and grid-friendly.
"""

from __future__ import annotations

from typing import Any, Iterable
import re

from ...core.xml_utils import get_cell
from ..context import DesignContext, DesignTarget
from ..model import DesignProfile, DesignRule, DesignViolation, FixSuggestion, RuleSeverity


GRID_FORMULA = "GUARD(3MM*User.Scale)"
LINE_WEIGHT_VALUE_IN = "0.01388888888888889"
CIRCUIT_WIRE_STYLE_NAME = "Circuit_Wire_Standard"
CIRCUIT_WIRE_STYLE_ID = "10"

POWER_SYMBOL_SPECS: dict[str, dict[str, Any]] = {
    "VDD": {
        "connection": {
            "X": "Width*0.5",
            "Y": "0",
            "DirX": "0",
            "DirY": "-1",
            "Prompt": "VDD terminal",
        }
    },
    "GND": {
        "connection": {
            "X": "Width*0.5",
            "Y": "Height",
            "DirX": "0",
            "DirY": "1",
            "Prompt": "GND terminal",
        }
    },
}

CIRCUIT_WIRE_STYLE_CELLS = {
    "LineWeight": {"value": LINE_WEIGHT_VALUE_IN, "unit": "PT"},
    "LineColor": {"value": "0"},
    "LinePattern": {"value": "1"},
    "Rounding": {"value": "0"},
    "BeginArrow": {"value": "0"},
    "EndArrow": {"value": "0"},
    "LineCap": {"value": "0"},
}

CIRCUIT_SCHEMATIC_SPEC: dict[str, Any] = {
    "document_settings": [
        {
            "name": "User.Scale",
            "value": "1",
            "requirement": "recommended",
            "rule_id": "circuit.document.required_user_cells",
        },
        {
            "name": "User.M",
            "value": "0.1181102362204724",
            "formula": GRID_FORMULA,
            "unit": "MM",
            "requirement": "recommended",
            "rule_id": "circuit.document.required_user_cells",
        },
        {
            "name": "User.LW",
            "value": LINE_WEIGHT_VALUE_IN,
            "unit": "PT",
            "requirement": "recommended",
            "rule_id": "circuit.document.required_user_cells",
        },
        {
            "name": "User.msvNoAutoConnect",
            "value": "1",
            "requirement": "recommended",
            "rule_id": "circuit.document.autoconnect",
        },
    ],
    "power_symbols": [
        {
            "name": name,
            "master": name,
            "top_shape": "shape/5",
            "type": "Group",
            "transform": {
                "Width": "TheDoc!User.M",
                "Height": "TheDoc!User.M",
                "PinX": "Width*0.5",
                "PinY": "Height*0.5",
                "LocPinX": "Width*0.5",
                "LocPinY": "Height*0.5",
            },
            "shape_cells": {
                "LineWeight": "TheDoc!User.LW",
                "LineColor": "#000000",
                "FillPattern": "0",
            },
            "canvas": {
                "PageWidth": "Sheet.5!Width",
                "PageHeight": "Sheet.5!Height",
                "meaning": "Master PageSheet canvas follows this symbol's top shape Width/Height.",
            },
            "connection": spec["connection"],
            "rule_id": f"circuit.power_symbol.{name.lower()}",
        }
        for name, spec in POWER_SYMBOL_SPECS.items()
    ],
    "symbol_canvas_rules": [
        {
            "name": "Master canvas matches symbol bounds",
            "applies_to": "all non-connector symbol masters",
            "page_width_formula": "Sheet.<top_shape_id>!Width",
            "page_height_formula": "Sheet.<top_shape_id>!Height",
            "cached_values": "PageWidth/PageHeight cached values should match the top shape Width/Height values.",
            "rule_id": "circuit.symbol.canvas_size",
        }
    ],
    "wire_style": {
        "name": CIRCUIT_WIRE_STYLE_NAME,
        "id": CIRCUIT_WIRE_STYLE_ID,
        "cells": CIRCUIT_WIRE_STYLE_CELLS,
        "rule_id": "circuit.connector.style_sheet",
    },
    "dynamic_connector": {
        "master": "Dynamic connector",
        "top_shape": "shape/5",
        "line_style": CIRCUIT_WIRE_STYLE_ID,
        "line_style_name": CIRCUIT_WIRE_STYLE_NAME,
        "endpoint_glue": "BeginX/BeginY/EndX/EndY should use PAR(PNT(...Connections...)) where endpoints are attached.",
        "rule_id": "circuit.connector.dynamic_connector_style",
    },
    "generic_rules": [
        {
            "name": "Component top shape",
            "rule_id": "circuit.component.top_shape",
            "setting": "Non-connector masters conventionally expose a reusable top shape, preferably shape/5.",
        },
        {
            "name": "Symbol canvas size",
            "rule_id": "circuit.symbol.canvas_size",
            "setting": "Master PageSheet.PageWidth/PageHeight must follow the symbol top shape Width/Height.",
        },
        {
            "name": "Component center anchor",
            "rule_id": "circuit.component.center_anchor",
            "setting": "LocPinX=Width*0.5 and LocPinY=Height*0.5.",
        },
        {
            "name": "Component scalable size",
            "rule_id": "circuit.component.scalable_size",
            "setting": "Width/Height should preferably reference User.M or another scalable formula.",
        },
        {
            "name": "Component pin conventions",
            "rule_id": "circuit.component.pins",
            "setting": "Pins should use Width/Height-relative coordinates and explicit -1/0/1 direction vectors.",
        },
        {
            "name": "Component scalable geometry",
            "rule_id": "circuit.component.scalable_geometry",
            "setting": "Geometry should prefer Width/Height formulas over absolute numeric points.",
        },
        {
            "name": "Connector instances",
            "rule_id": "circuit.connector.instances",
            "setting": "Page wires should use the shared Dynamic connector master and glue endpoints to connection points.",
        },
    ],
    "fixable_rules": [
        {
            "name": "Document user cells",
            "rule_id": "circuit.document.required_user_cells",
            "executor": "doc_page_settings",
        },
        {
            "name": "Autoconnect user cell",
            "rule_id": "circuit.document.autoconnect",
            "executor": "doc_page_settings",
        },
        {
            "name": "Standard power symbols",
            "rule_id": "circuit.power_symbol.vdd / circuit.power_symbol.gnd",
            "executor": "symbol_editor",
        },
        {
            "name": "Component center anchor",
            "rule_id": "circuit.component.center_anchor",
            "executor": "symbol_editor",
        },
    ],
}


def _document_globals_rule(context: DesignContext) -> Iterable[DesignViolation]:
    user_cells = context.settings.get("document", {}).get("user_cells", {})
    specs = {
        "Scale": {
            "message": "Document should define User.Scale so profile dimensions can be adjusted globally.",
            "command": {"action": "update_doc_user_cell", "name": "Scale", "value": "1"},
        },
        "M": {
            "message": "Document should define User.M as the circuit grid unit.",
            "command": {
                "action": "update_doc_user_cell",
                "name": "M",
                "value": "0.1181102362204724",
                "formula": GRID_FORMULA,
                "unit": "MM",
            },
        },
        "LW": {
            "message": "Document should define User.LW as the shared circuit line weight.",
            "command": {
                "action": "update_doc_user_cell",
                "name": "LW",
                "value": LINE_WEIGHT_VALUE_IN,
                "unit": "PT",
            },
        },
    }

    for name, spec in specs.items():
        target = f"document/sheet/User.{name}"
        cell = user_cells.get(name)
        if cell is None:
            yield DesignViolation(
                rule_id="circuit.document.required_user_cells",
                target=target,
                category="document",
                severity=RuleSeverity.WARNING,
                message=spec["message"],
                fixes=[
                    FixSuggestion(
                        executor="doc_page_settings",
                        target="document/sheet",
                        description=f"Create User.{name}.",
                        commands=[spec["command"]],
                    )
                ],
            )
            continue

        if name == "Scale" and _cell_expr(cell) != "1":
            yield DesignViolation(
                rule_id="circuit.document.required_user_cells",
                target=target,
                category="document",
                severity=RuleSeverity.WARNING,
                message="User.Scale should default to 1 for the base schematic profile.",
                details={"actual": cell},
                fixes=[
                    FixSuggestion(
                        executor="doc_page_settings",
                        target="document/sheet",
                        description="Reset User.Scale to the schematic default.",
                        commands=[spec["command"]],
                    )
                ],
            )

        if name == "M" and not _same_formula(cell.get("formula", ""), GRID_FORMULA):
            yield DesignViolation(
                rule_id="circuit.document.grid_formula",
                target=target,
                category="document",
                severity=RuleSeverity.WARNING,
                message="User.M should normally be guarded as 3MM times User.Scale.",
                details={"actual": cell},
                fixes=[
                    FixSuggestion(
                        executor="doc_page_settings",
                        target="document/sheet",
                        description="Normalize User.M to the profile grid formula.",
                        commands=[spec["command"]],
                    )
                ],
            )

        if name == "LW" and not _cell_matches_value(cell, LINE_WEIGHT_VALUE_IN, "PT"):
            yield DesignViolation(
                rule_id="circuit.document.required_user_cells",
                target=target,
                category="document",
                severity=RuleSeverity.WARNING,
                message="User.LW should match the standard schematic line weight.",
                details={"actual": cell},
                fixes=[
                    FixSuggestion(
                        executor="doc_page_settings",
                        target="document/sheet",
                        description="Reset User.LW to the schematic default.",
                        commands=[spec["command"]],
                    )
                ],
            )


def _document_autoconnect_rule(context: DesignContext) -> Iterable[DesignViolation]:
    user_cells = context.settings.get("document", {}).get("user_cells", {})
    cell = user_cells.get("msvNoAutoConnect")
    if cell is not None and _cell_expr(cell) == "1":
        return

    yield DesignViolation(
        rule_id="circuit.document.autoconnect",
        target="document/sheet/User.msvNoAutoConnect",
        category="document",
        severity=RuleSeverity.WARNING,
        message="Circuit schematic templates should disable Visio autoconnect with User.msvNoAutoConnect=1.",
        details={"actual": cell or {}},
        fixes=[
            FixSuggestion(
                executor="doc_page_settings",
                target="document/sheet",
                description="Disable automatic connector creation.",
                commands=[
                    {
                        "action": "update_doc_user_cell",
                        "name": "msvNoAutoConnect",
                        "value": "1",
                    }
                ],
            )
        ],
    )


def _page_grid_rule(context: DesignContext) -> Iterable[DesignViolation]:
    if not context.pages:
        return

    user_cells = context.settings.get("document", {}).get("user_cells", {})
    if "M" not in user_cells:
        for page_name in context.pages:
            yield DesignViolation(
                rule_id="circuit.page.grid_context",
                target=f"pages/{page_name}",
                category="page",
                severity=RuleSeverity.WARNING,
                message="Page can be free-sized, but circuit-grid checks need document User.M.",
            )


def _vdd_power_symbol_rule(context: DesignContext) -> Iterable[DesignViolation]:
    yield from _power_symbol_rule(context, "VDD")


def _gnd_power_symbol_rule(context: DesignContext) -> Iterable[DesignViolation]:
    yield from _power_symbol_rule(context, "GND")


def _power_symbol_rule(context: DesignContext, symbol_name: str) -> Iterable[DesignViolation]:
    target = context.masters.get(symbol_name)
    rule_id = f"circuit.power_symbol.{symbol_name.lower()}"
    if target is None:
        yield DesignViolation(
            rule_id=rule_id,
            target=f"masters/{symbol_name}",
            category="power_symbol",
            severity=RuleSeverity.WARNING,
            message=f"Standard power symbol master {symbol_name} is missing.",
        )
        return
    if target.data.get("error") or target.element is None:
        yield DesignViolation(
            rule_id=rule_id,
            target=target.path,
            category="power_symbol",
            severity=RuleSeverity.WARNING,
            message=f"Standard power symbol {symbol_name} could not be inspected: {target.data.get('error')}",
        )
        return

    transform = target.data.get("transform", {})
    expected_transform = {
        "Width": "TheDoc!User.M",
        "Height": "TheDoc!User.M",
        "PinX": "Width*0.5",
        "PinY": "Height*0.5",
        "LocPinX": "Width*0.5",
        "LocPinY": "Height*0.5",
    }
    details: dict[str, Any] = {}
    commands: list[dict[str, Any]] = []

    if target.element.get("Type") != "Group":
        details["type"] = target.element.get("Type", "")
    if not target.path.endswith("/shape/5"):
        details["top_shape"] = target.path

    for cell_name, expected in expected_transform.items():
        actual = _cell_expr(transform.get(cell_name, {}))
        if not _same_formula(actual, expected):
            details[cell_name] = actual
            commands.append(
                {
                    "action": "update_transform",
                    "property": cell_name,
                    "formula": expected,
                }
            )

    expected_shape_cells = {
        "LineWeight": {"formula": "TheDoc!User.LW", "unit": "PT"},
        "LineColor": {"value": "#000000"},
        "FillPattern": {"value": "0"},
    }
    for cell_name, expected in expected_shape_cells.items():
        actual = _shape_cell_data(target, cell_name)
        if not _matches_expected_cell(actual, expected):
            details[cell_name] = actual
            command = {
                "action": "set_shape_cell",
                "cell_name": cell_name,
            }
            if "formula" in expected:
                command["formula"] = expected["formula"]
            if "value" in expected:
                command["value"] = expected["value"]
            if "unit" in expected:
                command["unit"] = expected["unit"]
            commands.append(command)

    connections = target.data.get("connections", [])
    connection = connections[0] if connections else {}
    expected_connection = POWER_SYMBOL_SPECS[symbol_name]["connection"]
    if len(connections) != 1:
        details["connection_count"] = len(connections)

    connection_commands: list[dict[str, Any]] = []
    for cell_name in ("X", "Y", "DirX", "DirY"):
        actual = str(connection.get(cell_name, ""))
        expected = expected_connection[cell_name]
        if not _same_formula(actual, expected):
            details[f"Connection.{cell_name}"] = actual
            connection_commands.append(
                {
                    "cell_name": cell_name,
                    "value": expected,
                }
            )

    prompt = _connection_prompt(target, "0")
    if prompt != expected_connection["Prompt"]:
        details["Connection.Prompt"] = prompt
        connection_commands.append(
            {
                "cell_name": "Prompt",
                "value": expected_connection["Prompt"],
            }
        )

    if connection_commands:
        commands.append(
            {
                "action": "add_connection_pin",
                "id": "0",
                "x": expected_connection["X"],
                "y": expected_connection["Y"],
            }
        )
        for command in connection_commands:
            commands.append(
                {
                    "action": "set_section_cell",
                    "section": "Connection",
                    "row_ix": "0",
                    "row_type": "Connection",
                    "cell_name": command["cell_name"],
                    "value": command["value"],
                }
            )

    if details:
        fixes = []
        if commands:
            fixes.append(
                FixSuggestion(
                    executor="symbol_editor",
                    target=target.path,
                    description=f"Normalize the standard {symbol_name} power symbol.",
                    commands=commands,
                )
            )
        yield DesignViolation(
            rule_id=rule_id,
            target=target.path,
            category="power_symbol",
            severity=RuleSeverity.WARNING,
            message=f"{symbol_name} should match the standard schematic power symbol definition.",
            details=details,
            fixes=fixes,
        )


def _master_top_shape_rule(context: DesignContext) -> Iterable[DesignViolation]:
    for target in context.masters.values():
        if _is_connector_master(target):
            continue
        if target.data.get("error"):
            yield DesignViolation(
                rule_id="circuit.component.top_shape",
                target=target.path,
                category="component",
                severity=RuleSeverity.WARNING,
                message=f"Master could not be extracted as a reusable symbol: {target.data['error']}",
            )
            continue
        if not target.path.endswith("/shape/5"):
            yield DesignViolation(
                rule_id="circuit.component.top_shape",
                target=target.path,
                category="component",
                severity=RuleSeverity.INFO,
                message="Circuit symbols conventionally use top-level shape ID 5; this master uses another top shape.",
                details={"master": target.name},
            )


def _symbol_canvas_size_rule(context: DesignContext) -> Iterable[DesignViolation]:
    for target in context.masters.values():
        if _is_connector_master(target) or target.data.get("error"):
            continue

        top_shape_id = str(target.data.get("id") or "")
        expected = {
            "PageWidth": f"Sheet.{top_shape_id}!Width",
            "PageHeight": f"Sheet.{top_shape_id}!Height",
        }
        top_shape_cells = {
            "PageWidth": target.data.get("transform", {}).get("Width", {}),
            "PageHeight": target.data.get("transform", {}).get("Height", {}),
        }
        page_sheet = target.data.get("page_sheet", {})
        page_cells = page_sheet.get("cells", {})
        details: dict[str, Any] = {}

        for cell_name, expected_formula in expected.items():
            actual = page_cells.get(cell_name, {})
            if not actual:
                details[cell_name] = {"expected_formula": expected_formula, "actual": {}}
                continue
            if not _same_formula(str(actual.get("formula", "")), expected_formula):
                details[cell_name] = {
                    "expected_formula": expected_formula,
                    "actual": actual,
                }
                continue
            top_value = str(top_shape_cells[cell_name].get("val", ""))
            page_value = str(actual.get("val", ""))
            if top_value and page_value and not _same_value(page_value, top_value):
                details[cell_name] = {
                    "expected_formula": expected_formula,
                    "top_shape_value": top_value,
                    "actual": actual,
                }

        if details:
            yield DesignViolation(
                rule_id="circuit.symbol.canvas_size",
                target=target.path,
                category="component",
                severity=RuleSeverity.WARNING,
                message="Symbol master canvas PageWidth/PageHeight should follow the top shape Width/Height.",
                details=details,
            )


def _master_center_anchor_rule(context: DesignContext) -> Iterable[DesignViolation]:
    for target in context.masters.values():
        if _is_connector_master(target) or target.data.get("error"):
            continue
        transform = target.data.get("transform", {})
        expected = {"LocPinX": "Width*0.5", "LocPinY": "Height*0.5"}
        commands: list[dict[str, Any]] = []
        details: dict[str, Any] = {}

        for cell_name, formula in expected.items():
            actual = _cell_expr(transform.get(cell_name, {}))
            if not _same_formula(actual, formula):
                details[cell_name] = actual
                commands.append(
                    {
                        "action": "update_transform",
                        "property": cell_name,
                        "formula": formula,
                    }
                )

        if commands:
            yield DesignViolation(
                rule_id="circuit.component.center_anchor",
                target=target.path,
                category="component",
                severity=RuleSeverity.WARNING,
                message="Circuit component top shapes should use the center as LocPin for predictable placement.",
                details=details,
                fixes=[
                    FixSuggestion(
                        executor="symbol_editor",
                        target=target.path,
                        description="Set LocPinX and LocPinY to the shape center.",
                        commands=commands,
                    )
                ],
            )


def _master_scalable_size_rule(context: DesignContext) -> Iterable[DesignViolation]:
    for target in context.masters.values():
        if _is_connector_master(target) or target.data.get("error"):
            continue
        transform = target.data.get("transform", {})
        width = _cell_expr(transform.get("Width", {}))
        height = _cell_expr(transform.get("Height", {}))
        missing = [
            name
            for name, expr in (("Width", width), ("Height", height))
            if expr and not _looks_scalable_dimension(expr)
        ]
        if missing:
            yield DesignViolation(
                rule_id="circuit.component.scalable_size",
                target=target.path,
                category="component",
                severity=RuleSeverity.WARNING,
                message="Component dimensions should preferably reference User.M or another scalable formula.",
                details={"non_scalable_cells": missing, "width": width, "height": height},
            )


def _master_pin_rule(context: DesignContext) -> Iterable[DesignViolation]:
    for target in context.masters.values():
        if _is_connector_master(target) or target.data.get("error"):
            continue
        connections = target.data.get("connections", [])
        if not connections:
            yield DesignViolation(
                rule_id="circuit.component.pins",
                target=target.path,
                category="component",
                severity=RuleSeverity.INFO,
                message="Component master has no explicit connection pins.",
            )
            continue

        weak_pins = []
        weak_dirs = []
        for pin in connections:
            pin_id = pin.get("id", "")
            x_expr = pin.get("X", "")
            y_expr = pin.get("Y", "")
            if not (_looks_relative_pin_expr(x_expr, "Width") and _looks_relative_pin_expr(y_expr, "Height")):
                weak_pins.append({"id": pin_id, "X": x_expr, "Y": y_expr})
            if not _looks_direction(pin.get("DirX", "")) or not _looks_direction(pin.get("DirY", "")):
                weak_dirs.append({"id": pin_id, "DirX": pin.get("DirX", ""), "DirY": pin.get("DirY", "")})

        if weak_pins:
            yield DesignViolation(
                rule_id="circuit.component.relative_pins",
                target=target.path,
                category="component",
                severity=RuleSeverity.WARNING,
                message="Connection pins should use Width/Height-relative coordinates where possible.",
                details={"pins": weak_pins},
            )
        if weak_dirs:
            yield DesignViolation(
                rule_id="circuit.component.pin_directions",
                target=target.path,
                category="component",
                severity=RuleSeverity.INFO,
                message="Pin direction vectors should be explicit -1/0/1 values when the side is known.",
                details={"pins": weak_dirs},
            )


def _master_geometry_scaling_rule(context: DesignContext) -> Iterable[DesignViolation]:
    for target in context.masters.values():
        if _is_connector_master(target) or target.data.get("error"):
            continue
        absolute_points = []
        for geometry in target.data.get("geometry", []):
            for row in geometry.get("rows", []):
                for axis in ("X", "Y"):
                    expr = row.get(axis, "")
                    if _is_unscaled_geometry_number(expr):
                        absolute_points.append(
                            {
                                "geometry": geometry.get("ix"),
                                "row": row.get("ix"),
                                "axis": axis,
                                "value": expr,
                            }
                        )
        if absolute_points:
            yield DesignViolation(
                rule_id="circuit.component.scalable_geometry",
                target=target.path,
                category="component",
                severity=RuleSeverity.WARNING,
                message="Geometry uses absolute numeric points; scalable symbols should prefer Width/Height formulas.",
                details={"points": absolute_points[:20], "count": len(absolute_points)},
            )


def _connector_master_rule(context: DesignContext) -> Iterable[DesignViolation]:
    connector = _find_connector_master(context)
    if connector is None:
        yield DesignViolation(
            rule_id="circuit.connector.master",
            target="masters",
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Circuit diagrams should provide a shared connector master, preferably named Dynamic connector.",
        )
        return

    line_weight = _shape_cell_expr(connector, "LineWeight")
    if line_weight and "USER.LW" not in _normalize_formula(line_weight):
        yield DesignViolation(
            rule_id="circuit.connector.line_weight",
            target=connector.path,
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Connector line weight should preferably reference the document-level User.LW.",
            details={"actual": line_weight},
            fixes=[
                FixSuggestion(
                    executor="symbol_editor",
                    target=connector.path,
                    description="Link connector line weight to TheDoc!User.LW.",
                    commands=[
                        {
                            "action": "set_shape_cell",
                            "cell_name": "LineWeight",
                            "formula": "TheDoc!User.LW",
                            "unit": "PT",
                        }
                    ],
                )
            ],
        )


def _connector_style_sheet_rule(context: DesignContext) -> Iterable[DesignViolation]:
    style = context.styles.get(CIRCUIT_WIRE_STYLE_NAME) or context.styles.get(CIRCUIT_WIRE_STYLE_ID)
    if style is None:
        yield DesignViolation(
            rule_id="circuit.connector.style_sheet",
            target=f"document/styles/{CIRCUIT_WIRE_STYLE_NAME}",
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Circuit schematic should define the Circuit_Wire_Standard style sheet.",
        )
        return

    details: dict[str, Any] = {}
    data = style.data
    if data.get("id") != CIRCUIT_WIRE_STYLE_ID:
        details["ID"] = data.get("id", "")
    if data.get("name_u") != CIRCUIT_WIRE_STYLE_NAME:
        details["NameU"] = data.get("name_u", "")

    cells = data.get("cells", {})
    for cell_name, expected in CIRCUIT_WIRE_STYLE_CELLS.items():
        actual = cells.get(cell_name, {})
        if not _matches_expected_cell(actual, expected):
            details[cell_name] = actual

    if details:
        yield DesignViolation(
            rule_id="circuit.connector.style_sheet",
            target=style.path,
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Circuit_Wire_Standard should match the standard schematic wire style.",
            details=details,
        )


def _dynamic_connector_style_rule(context: DesignContext) -> Iterable[DesignViolation]:
    connector = _find_connector_master(context)
    if connector is None or connector.element is None:
        yield DesignViolation(
            rule_id="circuit.connector.dynamic_connector_style",
            target="masters/Dynamic connector",
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Dynamic connector master is required for the schematic wire style.",
        )
        return

    details: dict[str, Any] = {}
    if connector.element.get("LineStyle") != CIRCUIT_WIRE_STYLE_ID:
        details["LineStyle"] = connector.element.get("LineStyle", "")
    style = context.styles.get(connector.element.get("LineStyle", ""))
    if style is None:
        details["LineStyleTarget"] = "missing"
    elif style.data.get("name_u") != CIRCUIT_WIRE_STYLE_NAME:
        details["LineStyleTarget"] = style.data

    if details:
        yield DesignViolation(
            rule_id="circuit.connector.dynamic_connector_style",
            target=connector.path,
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Dynamic connector should use the Circuit_Wire_Standard line style.",
            details=details,
        )


def _page_connector_instances_rule(context: DesignContext) -> Iterable[DesignViolation]:
    connector = _find_connector_master(context)
    connector_id = connector.info.master_id if connector is not None and connector.info is not None else ""
    if not context.instances:
        return

    freeform_lines = []
    connector_instances = []
    unglued_connectors = []
    for instance in context.instances.values():
        data = instance.data
        if connector_id and data.get("master") == connector_id:
            connector_instances.append(instance.path)
            cells = data.get("cells", {})
            missing_glue = [
                name
                for name in ("BeginX", "BeginY", "EndX", "EndY")
                if "PAR(PNT(" not in _normalize_formula(_cell_expr(cells.get(name, {})))
            ]
            if missing_glue:
                unglued_connectors.append({"path": instance.path, "cells": missing_glue})
            continue
        if _looks_like_page_line(data):
            freeform_lines.append(instance.path)

    if freeform_lines:
        yield DesignViolation(
            rule_id="circuit.connector.instances",
            target="pages",
            category="connector",
            severity=RuleSeverity.WARNING,
            message="Page contains line-like shapes that do not use the shared connector master.",
            details={"instances": freeform_lines[:20], "count": len(freeform_lines)},
        )
    if unglued_connectors:
        yield DesignViolation(
            rule_id="circuit.connector.instances",
            target="pages",
            category="connector",
            severity=RuleSeverity.INFO,
            message="Some connector endpoints are not glued to shape connection points.",
            details={"instances": unglued_connectors[:20], "count": len(unglued_connectors)},
        )
    if connector is not None and not connector_instances and context.pages:
        yield DesignViolation(
            rule_id="circuit.connector.usage",
            target="pages",
            category="connector",
            severity=RuleSeverity.INFO,
            message="No page instances currently use the shared connector master.",
        )


def _same_formula(left: str, right: str) -> bool:
    return _normalize_formula(left) == _normalize_formula(right)


def _cell_matches_value(cell: dict[str, Any], value: str, unit: str | None = None) -> bool:
    if not _same_value(str(cell.get("val", "")), value):
        return False
    return unit is None or str(cell.get("unit", "")).upper() == unit.upper()


def _same_value(left: str, right: str) -> bool:
    if _is_number(left) and _is_number(right):
        return abs(float(left) - float(right)) < 1e-12
    return _normalize_formula(left) == _normalize_formula(right)


def _shape_cell_data(target: DesignTarget, name: str) -> dict[str, str]:
    if target.element is None:
        return {}
    cell = get_cell(target.element, name)
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


def _matches_expected_cell(actual: dict[str, Any], expected: dict[str, str]) -> bool:
    if "formula" in expected and not _same_formula(str(actual.get("formula", "")), expected["formula"]):
        return False
    if "value" in expected and not _same_value(str(actual.get("val", "")), expected["value"]):
        return False
    if "unit" in expected and str(actual.get("unit", "")).upper() != expected["unit"].upper():
        return False
    return True


def _connection_prompt(target: DesignTarget, row_id: str) -> str:
    for section in target.data.get("sections", []):
        if section.get("name") != "Connection":
            continue
        for row in section.get("rows", []):
            if row.get("ix") == row_id or row.get("n") == row_id:
                prompt = row.get("cells", {}).get("Prompt", {})
                formula = prompt.get("formula")
                if formula and formula != "No Formula":
                    return str(formula)
                return str(prompt.get("val", ""))
    return ""


def _normalize_formula(formula: str) -> str:
    return re.sub(r"\s+", "", str(formula or "")).upper()


def _cell_expr(cell: dict[str, Any]) -> str:
    return str(cell.get("formula") or cell.get("val") or "")


def _shape_cell_expr(target: DesignTarget, name: str) -> str:
    if target.element is None:
        return ""
    cell = get_cell(target.element, name)
    if cell is None:
        return ""
    return cell.get("F") or cell.get("V") or ""


def _is_connector_master(target: DesignTarget) -> bool:
    name = (target.name or target.data.get("name", "")).lower()
    return "connector" in name


def _find_connector_master(context: DesignContext) -> DesignTarget | None:
    for target in context.masters.values():
        if (target.name or "").lower() == "dynamic connector":
            return target
    for target in context.masters.values():
        if _is_connector_master(target):
            return target
    return None


def _looks_scalable_dimension(expr: str) -> bool:
    normalized = _normalize_formula(expr)
    if not normalized:
        return False
    return "USER.M" in normalized or "THEDOC!USER.M" in normalized or "WIDTH" in normalized or "HEIGHT" in normalized


def _looks_relative_pin_expr(expr: str, dimension: str) -> bool:
    normalized = _normalize_formula(expr)
    if normalized in {"0", "1", ""}:
        return True
    if normalized == "NOFORMULA":
        return False
    if dimension.upper() in normalized:
        return True
    return _is_number(expr) and float(expr) == 0.0


def _looks_direction(expr: str) -> bool:
    normalized = _normalize_formula(expr)
    if normalized == "NOFORMULA" or normalized == "":
        return False
    if normalized in {"-1", "0", "1"}:
        return True
    return _is_number(expr) and float(expr) in {-1.0, 0.0, 1.0}


def _is_unscaled_geometry_number(expr: str) -> bool:
    if not _is_number(expr):
        return False
    value = abs(float(expr))
    return value > 1e-9 and abs(value - 1.0) > 1e-9


def _is_number(value: str) -> bool:
    try:
        float(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _looks_like_page_line(data: dict[str, Any]) -> bool:
    name = str(data.get("name", "")).lower()
    shape_type = str(data.get("type", "")).lower()
    if "connector" in name:
        return True
    if shape_type == "shape":
        cells = data.get("cells", {})
        width = _cell_expr(cells.get("Width", {}))
        height = _cell_expr(cells.get("Height", {}))
        normalized = _normalize_formula(width + " " + height)
        return "ENDX-BEGINX" in normalized or "ENDY-BEGINY" in normalized
    return False


CIRCUIT_SCHEMATIC_PROFILE = DesignProfile(
    profile_id="circuit_diagram.v1",
    name="Circuit Schematic Style V1",
    description=(
        "Generic circuit-diagram constraints for reusable components, "
        "connector style, and grid-aware document settings."
    ),
    metadata={
        "domain": "circuit_diagram",
        "freedom": "geometry shape is flexible; scalability and connection conventions are audited",
        "spec": CIRCUIT_SCHEMATIC_SPEC,
    },
    rules=[
        DesignRule(
            rule_id="circuit.document.required_user_cells",
            title="Required circuit document variables",
            category="document",
            requirement="recommended",
            required_capabilities={"settings"},
            check=_document_globals_rule,
        ),
        DesignRule(
            rule_id="circuit.document.autoconnect",
            title="Disable Visio autoconnect",
            category="document",
            requirement="recommended",
            required_capabilities={"settings"},
            check=_document_autoconnect_rule,
        ),
        DesignRule(
            rule_id="circuit.page.grid_context",
            title="Page grid context",
            category="page",
            requirement="recommended",
            required_capabilities={"settings", "pages"},
            check=_page_grid_rule,
        ),
        DesignRule(
            rule_id="circuit.power_symbol.vdd",
            title="VDD standard power symbol",
            category="power_symbol",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_vdd_power_symbol_rule,
        ),
        DesignRule(
            rule_id="circuit.power_symbol.gnd",
            title="GND standard power symbol",
            category="power_symbol",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_gnd_power_symbol_rule,
        ),
        DesignRule(
            rule_id="circuit.component.top_shape",
            title="Component top shape",
            category="component",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_master_top_shape_rule,
        ),
        DesignRule(
            rule_id="circuit.symbol.canvas_size",
            title="Symbol canvas size",
            category="component",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_symbol_canvas_size_rule,
        ),
        DesignRule(
            rule_id="circuit.component.center_anchor",
            title="Component center anchor",
            category="component",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_master_center_anchor_rule,
        ),
        DesignRule(
            rule_id="circuit.component.scalable_size",
            title="Component scalable size",
            category="component",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_master_scalable_size_rule,
        ),
        DesignRule(
            rule_id="circuit.component.pins",
            title="Component pin conventions",
            category="component",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_master_pin_rule,
        ),
        DesignRule(
            rule_id="circuit.component.scalable_geometry",
            title="Component scalable geometry",
            category="component",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_master_geometry_scaling_rule,
        ),
        DesignRule(
            rule_id="circuit.connector.style_sheet",
            title="Standard wire style sheet",
            category="connector",
            requirement="recommended",
            required_capabilities={"styles"},
            check=_connector_style_sheet_rule,
        ),
        DesignRule(
            rule_id="circuit.connector.dynamic_connector_style",
            title="Dynamic connector style",
            category="connector",
            requirement="recommended",
            required_capabilities={"masters", "styles"},
            check=_dynamic_connector_style_rule,
        ),
        DesignRule(
            rule_id="circuit.connector.master",
            title="Shared connector master",
            category="connector",
            requirement="recommended",
            required_capabilities={"masters"},
            check=_connector_master_rule,
        ),
        DesignRule(
            rule_id="circuit.connector.instances",
            title="Connector instance usage",
            category="connector",
            requirement="recommended",
            required_capabilities={"pages"},
            check=_page_connector_instances_rule,
        ),
    ],
)

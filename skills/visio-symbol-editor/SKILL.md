---
name: visio-symbol-editor
description: Edit Visio master or page shapes through structured symbol_editor commands. Use for 修改形状, 改几何, 改引脚, 画, edit shape, geometry, pin, connection point, transform, line, rectangle, circle, ellipse, text, user cells, section cells, or formula-cache recalculation.
---

# Visio Symbol Editor

Use this skill to edit shape geometry, pins, transforms, text, style cells, and
shape-level User cells. Never edit raw XML or ZIP contents directly.

## Read First

Always inspect the target before planning commands:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, ElementLocator, to_skill, apply_skill_commands

bridge = VisioBridge("input.vstx")
locator = ElementLocator(bridge)
shape_path = "masters/Cap/shape/5"
shape = locator.find(shape_path)
if shape is None:
    print(json.dumps(bridge.parts_manifest(), indent=2, ensure_ascii=False))
else:
    print(json.dumps(to_skill(shape), indent=2, ensure_ascii=False))
```

If the shape path cannot be resolved, stop and ask for clarification with valid
paths from `parts_manifest()`.

## Execute

Batch all commands for the same `shape_path` in one call. Let
the explicit `backend` match the local `.visio_bridge.json` configuration.

```python
apply_skill_commands(bridge, shape_path, commands, backend="desktop")
bridge.save("input_modified.vstx")
```

Never overwrite the source file without explicit confirmation.

## Command Actions

| Action | Required fields | Notes |
|---|---|---|
| `update_transform` | `property`, `value` or `formula` | `Width`, `Height`, `PinX`, `PinY`, `LocPinX`, `LocPinY`, `Angle`, `FlipX`, `FlipY` |
| `set_shape_cell` | `cell_name` or `property`, `value` or `formula` | Generic shape cell writer, used for style cells such as `LineWeight`, `LineColor`, `FillPattern` |
| `add_connection_pin` | `id`, `x`, `y`, `dir_x`, `dir_y` | Creates or updates a row in the `Connection` section |
| `delete_connection_pin` | `id` | Removes one connection row |
| `modify_geometry` | `geom_ix`, `row_ix`, `x`, `y` | Edits `X` and `Y` on an existing geometry row |
| `draw_rectangle` | `x_min`, `y_min`, `x_max`, `y_max` | Adds a closed rectangular geometry section |
| `draw_line` | `x1`, `y1`, `x2`, `y2` | Adds an open line geometry section |
| `draw_circle` | optional `cx`, `cy`, `r` | Defaults to a centered circle using `Width*0.5` |
| `draw_ellipse` | optional `x_min`, `y_min`, `x_max`, `y_max` | Defaults to the full shape box |
| `draw_elliptical_arc` | optional box plus `start_angle`, `sweep_angle` | `sweep_angle >= 360` creates a closed ellipse |
| `update_text` | `text` | Replaces the shape text |
| `update_shape_user_cell` | `name`, `value` or `formula` | Optional `unit` |
| `delete_shape_user_cell` | `name` | Removes a shape User row |
| `set_section_cell` | `section`, `cell_name`, row selector, `value` or `formula` | Generic section row/cell writer; row selector is `row_ix` or `row_name` |
| `delete_section_row` | `section`, row selector | Removes a row from a section |
| `recalculate_formula_cache` | optional `target`, optional `scope` | Manual/debug recalculation; normal writes mark dirty scopes automatically |

`value` writes update cached `V`; `formula` writes persistent `F`. Formula-like
coordinate strings such as `Width*0.5` are intentionally valid.

## Examples

Resize a master and add one bottom pin:

```json
[
  {"action": "update_transform", "property": "Width", "formula": "TheDoc!User.M*2"},
  {"action": "update_transform", "property": "Height", "formula": "TheDoc!User.M*2"},
  {"action": "add_connection_pin", "id": "0", "x": "Width*0.5", "y": "0", "dir_x": "0", "dir_y": "-1"}
]
```

Normalize style cells:

```json
[
  {"action": "set_shape_cell", "cell_name": "LineWeight", "formula": "TheDoc!User.LW", "unit": "PT"},
  {"action": "set_shape_cell", "cell_name": "LineColor", "value": "#000000"},
  {"action": "set_shape_cell", "cell_name": "FillPattern", "value": "0"}
]
```

Set a connection prompt:

```json
[
  {
    "action": "set_section_cell",
    "section": "Connection",
    "row_ix": "0",
    "row_type": "Connection",
    "cell_name": "Prompt",
    "value": "VDD"
  }
]
```

## Formula Cache

Normal command batches mark the affected master or page instance dirty and
flush formula caches automatically before save. Use
`recalculate_formula_cache` only for explicit debug/report flows or when
delaying immediate recalculation with `"recalculate": false`.

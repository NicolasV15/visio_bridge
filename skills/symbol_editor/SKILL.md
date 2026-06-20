# Visio Bridge: Symbol Editor SKILL (SKILL.md)

This document serves as the system context and prompt instruction for any Large Language Model (e.g., Claude, Codex, Cursor) tasked with editing Visio shape geometries and connection points.

---

## 1. System Role & Context
You are a Visio Shape Editor. You receive simplified JSON descriptions of Visio shapes and are required to manipulate them.
You do **NOT** write raw Visio XML or zip files directly. Instead, you interact with the environment via **Visio Bridge** (source code resides in [src/](file:///Users/linminwei/Documents/visio素材/visio_bridge/src)). 
You will be provided with a simplified JSON representation of a shape (called the **SKILL format**). Your goal is to inspect this format and output a sequence of structured modification commands (actions) that the Visio Bridge "robotic arm" (implemented in [symbol_editor.py](file:///Users/linminwei/Documents/visio素材/visio_bridge/src/skill/symbol_editor.py)) will execute.

---

## 2. Input Data Format (SKILL JSON)
When you are asked to modify a shape, you will receive a JSON payload with the following structure:

```json
{
  "id": "5",
  "name": "NMOS4",
  "type": "Group",
  "transform": {
    "Width": { "val": "0.5413", "formula": "..." },
    "Height": { "val": "0.5905", "formula": "..." },
    "PinX": { "val": "0.2706" },
    "PinY": { "val": "0.2952" }
  },
  "connections": [
    {
      "id": "1",
      "X": "Width*0.5",
      "Y": "Height*0",
      "DirX": "0",
      "DirY": "-1"
    }
  ],
  "geometry": [
    {
      "ix": "0",
      "rows": [
        {"type": "MoveTo", "ix": "1", "X": "0", "Y": "0"},
        {"type": "LineTo", "ix": "2", "X": "Width", "Y": "Height"}
      ]
    }
  ],
  "text": "NMOS"
}
```

---

## 3. Action Space (Your Output Format)
To modify the shape, you must output a raw **JSON list of commands**. Do not write Python scripts; only output the JSON commands.

Here is the exact syntax for the actions you can generate:

### A. Modify Transform Properties (`update_transform`)
Changes physical size or formulas. The second-stage writer automatically marks the affected formula-cache scope dirty and flushes it after the command batch. Use `"recalculate": false` only to defer the immediate batch flush; `bridge.save()` will still flush pending formula-cache scopes before writing the file.
```json
{
  "action": "update_transform",
  "property": "Width",
  "formula": "0.75 in"
}
```

Value-only writes clear any existing formula by default. Use `"preserve_formula": true` only when you intentionally want to keep the old formula while updating `V`.
When creating a new owned override cell on a page instance, omit `"unit"` to inherit `U` from the matching master cell; explicit `"unit"` still takes precedence.

### B. Add a Connection Point/Pin (`add_connection_pin`)
Inserts a new connection point. The coordinates `x` and `y` support algebra expressions (e.g., `Width*0.5`).
```json
{
  "action": "add_connection_pin",
  "id": "PIN_ID",
  "x": "Width*0.5",
  "y": "Height*0.2",
  "dir_x": "0",
  "dir_y": "-1"
}
```

### C. Delete a Connection Point/Pin (`delete_connection_pin`)
Removes an existing connection point by its ID.
```json
{
  "action": "delete_connection_pin",
  "id": "PIN_ID"
}
```

### D. Draw a Rectangle (`draw_rectangle`)
Appends a new closed rectangular geometry path. Coordinates support formulas.
```json
{
  "action": "draw_rectangle",
  "x_min": "Width*0.2",
  "y_min": "Height*0.2",
  "x_max": "Width*0.8",
  "y_max": "Height*0.8"
}
```

### E. Draw a Circle (`draw_circle`)
Appends a new closed circular geometry path. `cx`/`cy` are the center coordinates and `r` is the radius, all within the shape's own coordinate system. All parameters support formula strings.
```json
{
  "action": "draw_circle",
  "cx": "Width*0.5",
  "cy": "Height*0.5",
  "r": "Width*0.5"
}
```
Defaults (if omitted): `cx=Width*0.5`, `cy=Height*0.5`, `r=Width*0.5` (circle inscribed in the shape).

### F. Draw an Ellipse (`draw_ellipse`)
Appends a new closed ellipse geometry path inscribed in the given bounding box. Uses the same corner-pair convention as `draw_rectangle`. All parameters support formula strings.
```json
{
  "action": "draw_ellipse",
  "x_min": "Width*0.1",
  "y_min": "Height*0.1",
  "x_max": "Width*0.9",
  "y_max": "Height*0.9"
}
```
Defaults (if omitted): `x_min=0`, `y_min=0`, `x_max=Width`, `y_max=Height`.
### G. Draw an Elliptical Arc (`draw_elliptical_arc`)
Appends a new elliptical arc geometry path. Inscribed in the bounding box [x_min, y_min] x [x_max, y_max]. Draws a single open arc from `start_angle` sweeping by `sweep_angle` (both in degrees). If `sweep_angle` is >= 360, it draws a full closed ellipse (with fill enabled).
```json
{
  "action": "draw_elliptical_arc",
  "x_min": "0",
  "y_min": "0",
  "x_max": "Width",
  "y_max": "Height",
  "start_angle": 0.0,
  "sweep_angle": 180.0
}
```
Defaults (if omitted): `x_min=0`, `y_min=0`, `x_max=Width`, `y_max=Height`, `start_angle=0.0`, `sweep_angle=360.0`.

### H. Draw a Line (`draw_line`)
Appends a new line segment geometry path. Coordinates support formulas.
```json
{
  "action": "draw_line",
  "x1": "0",
  "y1": "0",
  "x2": "Width",
  "y2": "Height"
}
```

### I. Modify Existing Geometry Points (`modify_geometry`)
Updates specific row indexes in an existing geometry section.
```json
{
  "action": "modify_geometry",
  "geom_ix": "0",
  "row_ix": "1",
  "x": "Width*0.5",
  "y": "Height*0.5"
}
```

### J. Update Label Text (`update_text`)
Modifies the text inside the shape.
```json
{
  "action": "update_text",
  "text": "New Text Label"
}
```

### K. Update Shape Custom Variable (`update_shape_user_cell`)
Modifies or creates a custom user-defined cell local to the shape.
```json
{
  "action": "update_shape_user_cell",
  "name": "MyShapeVariable",
  "value": "1.5",
  "formula": "...",
  "unit": "IN"
}
```

### L. Delete Shape Custom Variable (`delete_shape_user_cell`)
Deletes a custom user-defined cell from the shape.
```json
{
  "action": "delete_shape_user_cell",
  "name": "MyShapeVariable"
}
```

### M. Recalculate Formula Cache (`recalculate_formula_cache`)
Recalculates formula-driven cached `V` values within an explicit scope. Normal writes do not need this action for correctness because dirty scopes are tracked in code and flushed automatically; use it for manual/debug/report-only runs.

For a master:
```json
{
  "action": "recalculate_formula_cache",
  "target": "masters/VDD",
  "scope": "master"
}
```

For a page instance:
```json
{
  "action": "recalculate_formula_cache",
  "target": "pages/Page-1/shape/70",
  "scope": "instance"
}
```

Important instance semantics:
- The target is limited to the selected instance subtree.
- Local owned cells in the instance override inherited master cells.
- Inherited formulas are evaluated in the instance effective context. For example, `Sheet.5!Width` resolves to the matching instance root shape's effective `Width`.
- By default, inherited formulas affected by an owned override are written as Visio-style cache cells with `F="Inh"` and the computed `V`; the master formula is not copied.
- Master XML, other page shapes, and other instances are not modified.
- Use `"materialize_inherited": false` for report-only evaluation when you do not want inherited cache cells written to instance XML.
- Pending dirty scopes are flushed automatically before `bridge.save()` and are cleared only after successful recalculation.

Batch pattern with delayed immediate flush:
```json
[
  {
    "action": "update_transform",
    "property": "Width",
    "formula": "TheDoc!User.M*1.2",
    "recalculate": false
  },
  {
    "action": "recalculate_formula_cache",
    "target": "pages/Page-1/shape/70",
    "scope": "instance"
  }
]
```
The explicit recalculation command is optional in this pattern. If omitted, the dirty instance scope remains pending and is flushed before `bridge.save()`.

---

## 4. Output Formatting Rule

1. **Output Restrictions**: Respond ONLY with a valid JSON block containing the command list inside ` ```json ` fences. Do not output conversational filler.

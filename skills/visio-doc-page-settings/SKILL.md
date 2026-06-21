---
name: visio-doc-page-settings
description: Edit Visio document and page settings through doc_page_settings commands. Use for 改页面, 改文档, 比例, 页宽, page size, drawing scale, document settings, DocumentSheet User cells, PageSheet cells, and page-level User cells.
---

# Visio Document And Page Settings

Use this skill to inspect and update document-level User cells and PageSheet
settings. Never edit raw XML directly.

## Read First

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, to_settings_skill, apply_settings_commands

bridge = VisioBridge("input.vstx")
settings = to_settings_skill(bridge)
print(json.dumps(settings, indent=2, ensure_ascii=False))
```

Use the returned page `name` or `id` in page commands. Do not invent document
scale formulas or page names.

## Execute

```python
apply_settings_commands(bridge, commands, backend="desktop")
bridge.save("input_modified.vstx")
```

Pass an explicit `backend` that matches `.visio_bridge.json`. Save to a new output path unless the user
explicitly confirms overwriting the source.

## Readable Data

`to_settings_skill(bridge)` returns:

- `document.user_cells`: DocumentSheet User rows such as `Scale`, `M`, and `LW`.
- `pages[].cells`: PageSheet cells.
- `pages[].user_cells`: page-level User rows.

Supported standard page cells include `PageWidth`, `PageHeight`, `PageScale`,
`DrawingScale`, `DrawingSizeType`, and `DrawingScaleType`.

## Command Actions

| Action | Required fields | Notes |
|---|---|---|
| `update_doc_user_cell` | `name`, `value` or `formula` | Optional `unit`; writes DocumentSheet User cell |
| `delete_doc_user_cell` | `name` | Removes a DocumentSheet User row |
| `update_page_cell` | `page`, `property`, `value` or `formula` | `page` can be NameU, Name, or ID |
| `update_page_user_cell` | `page`, `name`, `value` or `formula` | Optional `unit`; writes PageSheet User cell |
| `delete_page_user_cell` | `page`, `name` | Removes a PageSheet User row |

## Examples

Update the global scale and page size:

```json
[
  {"action": "update_doc_user_cell", "name": "Scale", "value": "1"},
  {"action": "update_page_cell", "page": "Page-1", "property": "PageWidth", "value": "11 in"},
  {"action": "update_page_cell", "page": "Page-1", "property": "PageHeight", "value": "8.5 in"}
]
```

Set a page-local variable:

```json
[
  {"action": "update_page_user_cell", "page": "Page-1", "name": "GridPitch", "formula": "TheDoc!User.M", "unit": "IN"}
]
```

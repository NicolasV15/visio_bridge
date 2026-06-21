---
name: visio-instance-manager
description: Add, copy, or delete Visio shape instances through instance_manager commands. Use for 添加形状, 复制, 删除形状, add shape, drop master, copy shape, duplicate instance, delete instance, or place components on a page or inside a group.
---

# Visio Instance Manager

Use this skill to add master instances, copy existing instances, or delete page
instances. Do not use it to edit geometry or page settings.

## Read First

Inspect the file before changing instances:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, apply_instance_commands

bridge = VisioBridge("input.vsdx")
print(json.dumps(bridge.parts_manifest(), indent=2, ensure_ascii=False))
```

Use the manifest to confirm the page or group `parent`, source `shape_path`,
and master `NameU` or ID. If a target path is ambiguous, stop and ask for a
specific page, shape, or master.

## Execute

```python
results = apply_instance_commands(bridge, commands)
bridge.save("input_modified.vsdx")
print(json.dumps(results, indent=2, ensure_ascii=False))
```

Let `backend="auto"` be the default. Save to a new file unless the user
explicitly confirms overwriting.

## Command Actions

| Action | Required fields | Optional fields | Notes |
|---|---|---|---|
| `add_instance` | `parent`, `master`, `x`, `y` | `width`, `height`, `angle` | Drops a master into a page or group |
| `copy_instance` | `shape_path`, `x`, `y` | none | Deep-clones an existing instance with new IDs |
| `delete_instance` | `shape_path` | none | Removes the target shape and descendants |

## Examples

Add a resistor master to a page:

```json
[
  {
    "action": "add_instance",
    "parent": "pages/Page-1",
    "master": "Res",
    "x": "2 in",
    "y": "3 in",
    "width": "0.5 in",
    "height": "0.25 in",
    "angle": "0"
  }
]
```

Copy an existing shape:

```json
[
  {"action": "copy_instance", "shape_path": "pages/Page-1/shape/42", "x": "5 in", "y": "3 in"}
]
```

Delete an instance:

```json
[
  {"action": "delete_instance", "shape_path": "pages/Page-1/shape/42"}
]
```

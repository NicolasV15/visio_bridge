# Visio Bridge — Examples

[中文版](examples_cn.md) | [← Back to README](../README.md)

---

## Table of Contents

- [Example 1: Read-only File Inspection with `visio-file-inspector`](#example-1-read-only-file-inspection-with-visio-file-inspector)
- [Example 2: Edit Component Symbols with `visio-symbol-editor`](#example-2-edit-component-symbols-with-visio-symbol-editor)
- [Example 2b: Recalculate Formula Cache for Page Instances](#example-2b-recalculate-formula-cache-for-page-instances)
- [Example 3: Edit Document & Page Settings with `visio-doc-page-settings`](#example-3-edit-document--page-settings-with-visio-doc-page-settings)
- [Example 3b: Use Visio Desktop Backend by Default](#example-3b-use-visio-desktop-backend-by-default)
- [Example 3c: Refresh an Open Visio Document After XML Save](#example-3c-refresh-an-open-visio-document-after-xml-save)
- [Example 4: Audit Circuit Diagrams with `design` Framework](#example-4-audit-circuit-diagrams-with-design-framework)
- [Example 5: Manage Shape Instances with `visio-instance-manager`](#example-5-manage-shape-instances-with-visio-instance-manager)

---

## Example 1: Read-only File Inspection with `visio-file-inspector`

Use the parts manifest and locator engine to explore any Visio file's internal structure without modifying it.

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, ElementLocator
import xml.etree.ElementTree as ET

bridge = VisioBridge("circuit.vstx")
locator = ElementLocator(bridge)

# 1. Print the full package resource manifest map
print(bridge.parts_manifest())

# 2. Locate and read core custom metadata
custom_props = locator.find("doc_props/custom")
if custom_props is not None:
    for prop in custom_props:
        print("Property:", prop.get("name"), "Value:", prop[0].text)
```

---

## Example 2: Edit Component Symbols with `visio-symbol-editor`

Extract shape data in AI-readable format and apply structured modification commands.

```python
from visio_bridge import VisioBridge, ElementLocator, to_skill, apply_skill_commands

bridge = VisioBridge("circuit.vstx")
locator = ElementLocator(bridge)
shape_path = "masters/NMOS4/shape/5"
shape_element = locator.find(shape_path)

# Convert to AI-readable component data
skill_data = to_skill(shape_element)

# Execute modifications using the explicitly configured backend.
commands = [
    {"action": "update_transform", "property": "Width", "formula": "0.75 in"},
    {"action": "add_connection_pin", "id": "99", "x": "Width*0.5", "y": "Height*0.2", "dir_x": "0", "dir_y": "-1"}
]
apply_skill_commands(bridge, shape_path, commands, backend="desktop")
bridge.save("circuit_modified.vstx")
```

---

## Example 2b: Recalculate Formula Cache for Page Instances

Demonstrate instance-level formula recalculation with inherited cache synchronization.

```python
from visio_bridge import VisioBridge, ElementLocator, apply_skill_commands
from visio_bridge.src.core.xml_utils import get_cell

bridge = VisioBridge("circuit.vstx")
target = "pages/Page-1/shape/70"

apply_skill_commands(
    bridge,
    target,
    [
        {"action": "update_transform", "property": "Width", "formula": "TheDoc!User.M*1.2"},
    ],
    backend="desktop",
)

shape = ElementLocator(bridge).find(target)
print("Instance Width:", get_cell(shape, "Width").attrib)

# By default, inherited formulas affected by the Width override in the current
# instance subtree are written as F="Inh" cache entries (e.g., LocPinX,
# Connection.X, child shape BeginX/PinX/Width effective cache).
bridge.save("circuit_instance_width_modified.vsdx")
```

---

## Example 3: Edit Document & Page Settings with `visio-doc-page-settings`

Extract and modify global document variables and page-level properties.

```python
from visio_bridge import VisioBridge, to_settings_skill, apply_settings_commands

bridge = VisioBridge("circuit.vstx")

# Extract current document and page settings
settings = to_settings_skill(bridge)
print("Global and page settings:", settings)

# Execute configuration commands using the explicitly configured backend.
commands = [
    {"action": "update_doc_user_cell", "name": "AntiGravityScale", "value": "1.5", "unit": "IN"},
    {"action": "update_page_cell", "page": "Page-1", "property": "PageWidth", "formula": "12 in"}
]
apply_settings_commands(bridge, commands, backend="desktop")
bridge.save("circuit_settings_modified.vstx")
```

---

## Example 3b: Use the Explicit Visio Desktop Backend

Phase 2 entry points require an explicit backend that matches `.visio_bridge.json`.

```python
from visio_bridge import VisioBridge, apply_skill_commands, apply_settings_commands

bridge = VisioBridge("circuit.vstx")

apply_skill_commands(
    bridge,
    "masters/NMOS4/shape/5",
    [
        {"action": "update_transform", "property": "Width", "formula": "0.75 in"},
        {"action": "update_text", "text": "NMOS"},
    ],
    output_path="circuit_desktop_modified.vstx",
    backend="desktop",
)

modified = VisioBridge("circuit_desktop_modified.vstx")
apply_settings_commands(
    modified,
    [
        {"action": "update_doc_user_cell", "name": "M", "value": "1"},
    ],
    output_path="circuit_desktop_modified.vstx",
    backend="desktop",
)

# To use the XML ZIP backend, .visio_bridge.json must also set "backend": "xml".
apply_settings_commands(
    modified,
    [{"action": "update_doc_user_cell", "name": "M", "value": "1"}],
    backend="xml",
)
```

---

## Example 3c: Refresh an Open Visio Document After XML Save

When you modify a file through the XML backend while the same file is already
open in Visio Desktop, explicitly refresh the Visio window after saving.

```python
from visio_bridge import (
    VisioBridge,
    apply_settings_commands,
    find_visio_document,
    refresh_visio_file,
)

path = "circuit_settings_modified.vsdx"
bridge = VisioBridge(path)

apply_settings_commands(
    bridge,
    [{"action": "update_doc_user_cell", "name": "Scale", "value": "2"}],
    backend="xml",
)
bridge.save(path)

if find_visio_document(path) is not None:
    # Default behavior discards unsaved edits made in the Visio UI, then
    # closes and reopens the document so Visio reflects the latest disk file.
    refresh_visio_file(path)
```

---

## Example 4: Audit Circuit Diagrams with `design` Framework

Run a read-only design audit using a built-in profile and plan suggested fix commands.

```python
import json
from visio_bridge import (
    VisioBridge,
    CIRCUIT_SCHEMATIC_PROFILE,
    audit_design,
    render_design_profile_markdown,
    plan_design_commands,
)

bridge = VisioBridge("circuit.vstx")

# 1. View the full rule description of the Profile (no file needed)
print(render_design_profile_markdown(CIRCUIT_SCHEMATIC_PROFILE))

# 2. Read-only audit: does not modify the file
report = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

# 3. Plan optional fix commands: grouped by Phase 2 executor
command_groups = plan_design_commands(report)
print(json.dumps(command_groups, indent=2, ensure_ascii=False))
```

---

## Example 5: Manage Shape Instances with `visio-instance-manager`

Add, copy, and delete shape instances on pages or inside group containers.

```python
from visio_bridge import VisioBridge, apply_instance_commands

bridge = VisioBridge("circuit.vsdx")

commands = [
    # Add a new instance of the "Cap" master on Page-1
    {
        "action": "add_instance",
        "parent": "pages/Page-1",
        "master": "Cap",
        "x": "2.0 in",
        "y": "3.0 in",
        "width": "0.5 in",
        "height": "0.5 in",
    },
    # Copy an existing shape to a new location
    {
        "action": "copy_instance",
        "shape_path": "pages/Page-1/shape/168",
        "x": "4.0 in",
        "y": "3.0 in",
    },
    # Delete a shape instance
    {
        "action": "delete_instance",
        "shape_path": "pages/Page-1/shape/200",
    },
]

results = apply_instance_commands(bridge, commands, backend="desktop")
print("Results:", results)
bridge.save("circuit_instances_modified.vsdx")
```

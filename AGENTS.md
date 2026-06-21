# AGENTS.md — Visio Bridge Agent Playbook

This file is the authoritative operating guide for any AI coding agent (Claude Code, Codex, Cursor, Gemini CLI, etc.) working inside this repository. Read it **before** writing any code or running any command against a Visio file.

---

## 1. What This Repo Does

Visio Bridge is a Python toolkit for reading and modifying Visio files (`.vsdx` / `.vstx` / `.vssx`). It exposes a structured **SKILL interface**: the agent reads a Visio file through the bridge API, receives a JSON snapshot of the relevant data, outputs a JSON command list, and the library executes those commands and saves the file.

> **You never write raw XML or touch ZIP internals.** All interactions go through the Python API described below.

---

## 2. Workspace Setup

```python
import sys
sys.path.insert(0, "/path/to/parent/of/visio_bridge")  # adjust to actual workspace root

from visio_bridge import (
    VisioBridge,
    ElementLocator,
    to_skill,
    apply_skill_commands,
    to_settings_skill,
    apply_settings_commands,
    apply_instance_commands,
    list_visio_documents,
    find_visio_document,
    open_visio_file,
    close_visio_file,
    refresh_visio_file,
    audit_design,
    plan_design_commands,
    render_design_profile_markdown,
    CIRCUIT_SCHEMATIC_PROFILE,
)
```

Install (if not already):

```bash
pip install -e ./visio_bridge            # core only (zero third-party deps)
pip install -e "./visio_bridge[desktop]" # + Visio Desktop COM support (Windows/Parallels)
```

### 2.1 Workspace Configuration & Setup

You can configure the default backend, Parallels VM name, and timeout settings via a local `visio_bridge.json` or `.visio_bridge.json` configuration file. Run the interactive setup tool to configure your environment:

```bash
python -m visio_bridge.src.core.setup_cli
# Or after installing:
visio-bridge-setup
```

This generates a `.visio_bridge.json` file in the current working directory:

```json
{
  "backend": "auto",
  "desktop_transport_mode": "auto",
  "vm_name": "Windows 11",
  "visible": false,
  "timeout": 180
}
```

Agents should read `visio_bridge.json` or `.visio_bridge.json` if present to respect the user's customized default settings.

---

## 3. Intent → SKILL Dispatch Table

Parse the user's instruction and route to the matching SKILL module. When the intent spans multiple modules, execute them **in the order listed below**.

| User intent keywords | SKILL module | System prompt | Execute with |
|---|---|---|---|
| "读取" / "查看" / "诊断" / "列出" / inspect / read / diagnose / list | **file_inspector** | [`skills/file_inspector/SKILL.md`](skills/file_inspector/SKILL.md) | *(read-only, no apply)* |
| "修改形状" / "改几何" / "改引脚" / "画" / edit shape / geometry / pin / draw | **symbol_editor** | [`skills/symbol_editor/SKILL.md`](skills/symbol_editor/SKILL.md) | `apply_skill_commands()` |
| "改页面" / "改文档" / "比例" / "页宽" / page size / scale / document settings | **doc_page_settings** | [`skills/doc_page_settings/SKILL.md`](skills/doc_page_settings/SKILL.md) | `apply_settings_commands()` |
| "添加形状" / "复制" / "删除形状" / add shape / copy shape / drop / delete instance | **instance_manager** | [`skills/instance_manager/SKILL.md`](skills/instance_manager/SKILL.md) | `apply_instance_commands()` |
| "会话" / "打开" / "关闭" / "刷新" / reload / session / open in Visio / close in Visio | **visio_session_manager** | [`skills/visio_session_manager/SKILL.md`](skills/visio_session_manager/SKILL.md) | `list_visio_documents()` / `open_visio_file()` / `close_visio_file()` / `refresh_visio_file()` |
| "审计" / "检查规范" / "自动修复" / audit / design check / compliance / fix violations | **design_rules** | [`skills/design_rules/SKILL.md`](skills/design_rules/SKILL.md) | `plan_design_commands()` → then `apply_*` |

---

## 4. Standard Agent Workflow

Follow this three-step pattern for every modification task:

### Step 1 — Read

Inspect the file to understand current state. **Always inspect before editing.**

```python
bridge = VisioBridge("path/to/file.vstx")

# Option A: get the full topology map (use when target location is unknown)
import json
print(json.dumps(bridge.parts_manifest(), indent=2, ensure_ascii=False))

# Option B: read a specific element
locator = ElementLocator(bridge)

# Master shape data (symbol_editor input)
shape = locator.find("masters/NMOS4/shape/5")
skill_data = to_skill(shape)
print(json.dumps(skill_data, indent=2, ensure_ascii=False))

# Document & page settings (doc_page_settings input)
settings = to_settings_skill(bridge)
print(json.dumps(settings, indent=2, ensure_ascii=False))
```

### Step 2 — Plan (ask AI / build commands)

Feed `skill_data` or `settings` to the matching SKILL agent (or reason about it yourself) and produce a JSON command list. Example:

```json
[
    {"action": "update_transform", "property": "Width", "formula": "TheDoc!User.M*4"},
    {"action": "add_connection_pin", "id": "10", "x": "Width*0.5", "y": "0", "dir_x": "0", "dir_y": "-1"}
]
```

### Step 3 — Execute and Save

```python
# symbol_editor
apply_skill_commands(bridge, "masters/NMOS4/shape/5", commands, backend="xml")

# doc_page_settings
apply_settings_commands(bridge, commands, backend="xml")

# instance_manager
apply_instance_commands(bridge, commands, backend="xml")

bridge.save("path/to/output.vstx")
```

---

## 5. Module-by-Module Reference

### 5.1 `file_inspector` — Read-Only Inspection

**Use when:** the user wants to understand file structure before editing, or only needs a report.

```python
bridge  = VisioBridge("file.vstx")
locator = ElementLocator(bridge)

# --- Inspect structure ---
bridge.parts_manifest()                         # full topology JSON
locator.find("masters/Cap/shape/5")             # master shape element
locator.find("pages/Page-1/shape/70")           # page instance element
locator.find("document/sheet")                  # DocumentSheet
locator.find("theme/0")                         # DrawingML theme
locator.find("windows")                         # window state
locator.find("doc_props/core")                  # Dublin Core metadata
locator.find("doc_props/custom")                # custom properties
```

**Locator path cheat sheet:**

| Path pattern | What it resolves to |
|---|---|
| `masters/<NameU>` | Master root element |
| `masters/<NameU>/shape/<ID>` | Shape element inside a master |
| `masters/<NameU>/shape/<ID>/cell/<CellName>` | Single Cell inside a shape |
| `masters/<NameU>/shape/<ID>/section/<Name>` | Section element |
| `pages/<NameU_or_ID>` | Page root element |
| `pages/<NameU_or_ID>/shape/<ID>` | Shape element on a page |
| `document` | Document root |
| `document/sheet` | DocumentSheet (global User cells) |
| `theme/0` | DrawingML theme root |
| `windows` | Windows root |
| `doc_props/core` | Dublin Core metadata |
| `doc_props/app` | App-level metadata |
| `doc_props/custom` | Custom properties |

**Output rules:** produce a human-readable summary + a `json` code block with the raw data. Never call `apply_*` or `bridge.save()` in read-only mode.

---

### 5.2 `symbol_editor` — Shape Geometry & Pins

**Use when:** editing a master shape's geometry, connection pins, transforms, text, or user-defined cells.

**Full action list:**

| Action | Required fields | Notes |
|---|---|---|
| `update_transform` | `property`, `formula` | Properties: `Width`, `Height`, `PinX`, `PinY`, `LocPinX`, `LocPinY`, `Angle`, `FlipX`, `FlipY` |
| `recalculate_formula_cache` | `target`, `scope` | `scope`: `"master"` or `"instance"`. Use only for explicit/debug recalculation; normal writes auto-flush |
| `add_connection_pin` | `id`, `x`, `y`, `dir_x`, `dir_y` | Coordinates support formula strings |
| `delete_connection_pin` | `id` | |
| `draw_rectangle` | `x_min`, `y_min`, `x_max`, `y_max` | Closed filled rectangle |
| `draw_line` | `x1`, `y1`, `x2`, `y2` | Open line segment |
| `draw_circle` | `cx`, `cy`, `r` | Defaults: inscribed in shape |
| `draw_ellipse` | `x_min`, `y_min`, `x_max`, `y_max` | Closed filled ellipse |
| `draw_elliptical_arc` | `x_min`, `y_min`, `x_max`, `y_max`, `start_angle`, `sweep_angle` | `sweep_angle >= 360` → closed filled ellipse |
| `modify_geometry` | `geom_ix`, `row_ix`, `x`, `y` | Modifies existing geometry row |
| `update_text` | `text` | Replaces shape text label |
| `update_shape_user_cell` | `name`, `value` or `formula` | Optional `unit` |
| `delete_shape_user_cell` | `name` | |

**Execution:**

```python
shape_path = "masters/NMOS4/shape/5"  # or "pages/Page-1/shape/70" for instances
apply_skill_commands(bridge, shape_path, commands, backend="xml")
bridge.save("output.vstx")
```

**Formula cache rules (do not override these unless explicitly asked):**
- Writing to a master → dirty scope auto-set; flushed before `bridge.save()`.
- Writing to a page instance → only that instance subtree is recalculated; inherited formulas that are tainted get `F="Inh"` cache written.
- `recalculate: false` in a command defers the immediate flush but does NOT skip the pre-save flush.

---

### 5.3 `doc_page_settings` — Document & Page Configuration

**Use when:** changing page dimensions, drawing scale, or global/page-level `User.*` variables.

**Full action list:**

| Action | Required fields | Notes |
|---|---|---|
| `update_doc_user_cell` | `name`, `value` or `formula` | Optional `unit`. Global DocumentSheet User cells |
| `delete_doc_user_cell` | `name` | |
| `update_page_cell` | `page`, `property`, `value` or `formula` | `page` = page NameU (e.g. `"Page-1"`). Properties: `PageWidth`, `PageHeight`, `PageScale`, `DrawingScale`, `DrawingSizeType` |
| `update_page_user_cell` | `page`, `name`, `value` or `formula` | Optional `unit` |
| `delete_page_user_cell` | `page`, `name` | |

**Common document User cells:**

| Cell | Meaning |
|---|---|
| `User.Scale` | Global scale multiplier |
| `User.M` | Grid unit size = `3mm × Scale` |
| `User.LW` | Global line weight |

**Execution:**

```python
settings = to_settings_skill(bridge)  # read current state first
# ... plan commands ...
apply_settings_commands(bridge, commands, backend="xml")
bridge.save("output.vstx")
```

---

### 5.4 `instance_manager` — Shape Instance Lifecycle

**Use when:** adding new component instances to a page, duplicating existing shapes, or removing shapes.

**Full action list:**

| Action | Required fields | Optional fields | Notes |
|---|---|---|---|
| `add_instance` | `parent`, `master`, `x`, `y` | `width`, `height`, `angle` | `parent` = locator path of page or group; `master` = NameU or ID |
| `copy_instance` | `shape_path`, `x`, `y` | | Deep-clones the source shape with new unique IDs |
| `delete_instance` | `shape_path` | | Recursively removes all descendants |

**Example:**

```json
[
    {
        "action": "add_instance",
        "parent": "pages/Page-1",
        "master": "Res",
        "x": "3.0 in",
        "y": "4.0 in",
        "width": "0.5 in",
        "height": "0.25 in"
    },
    {
        "action": "copy_instance",
        "shape_path": "pages/Page-1/shape/42",
        "x": "5.0 in",
        "y": "4.0 in"
    }
]
```

**Execution:**

```python
results = apply_instance_commands(bridge, commands, backend="xml")
# results is a list of dicts with "action", "status", "shape_path" for each command
bridge.save("output.vsdx")
```

---

### 5.5 `design_rules` — Audit & Automated Fix Planning

**Use when:** checking a Visio file against a style profile or planning bulk fixes.

**Workflow:**

```python
# 1. Describe the profile (no file needed)
print(render_design_profile_markdown(CIRCUIT_SCHEMATIC_PROFILE))

# 2. Run read-only audit
report = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
import json
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

# 3. Plan fix commands (grouped by executor)
command_groups = plan_design_commands(report)
# command_groups = {
#   "symbol_editor": [{"target": "masters/Cap/shape/5", "commands": [...]}],
#   "doc_page_settings": [{"commands": [...]}],
#   "instance_manager": [{"commands": [...]}],
# }

# 4. Apply fix groups selectively (confirm with user before applying)
for group in command_groups.get("symbol_editor", []):
    apply_skill_commands(bridge, group["target"], group["commands"], backend="xml")

settings_cmds = [cmd for group in command_groups.get("doc_page_settings", []) for cmd in group["commands"]]
apply_settings_commands(bridge, settings_cmds, backend="xml")

instance_cmds = [cmd for group in command_groups.get("instance_manager", []) for cmd in group["commands"]]
apply_instance_commands(bridge, instance_cmds, backend="xml")

bridge.save("output_fixed.vstx")

# 5. Re-audit to verify
report2 = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
```

---

### 5.6 `visio_session_manager` — Visio Desktop Session Control

**Use when:** detecting currently open Visio documents, opening/closing files in Visio Desktop, or refreshing a file after Visio Bridge modified it on disk.

```python
from visio_bridge import (
    list_visio_documents,
    find_visio_document,
    open_visio_file,
    close_visio_file,
    refresh_visio_file,
)

# List open documents in the user's current Visio instance.
docs = list_visio_documents()

# Open or activate a document.
open_visio_file("circuit_modified.vsdx", visible=True, activate=True)

# Safe close: refuses to close if Visio has unsaved UI changes.
close_visio_file("circuit_modified.vsdx")

# Refresh after a disk write. Default behavior discards unsaved Visio UI edits.
refresh_visio_file("circuit_modified.vsdx")
```

**Important rules:**
- Session management requires the Desktop COM transport; it is not available through the XML ZIP backend.
- `refresh_visio_file()` is a close-and-reopen operation, not an in-place XML reload.
- The default refresh policy is `discard_unsaved=True`, so unsaved edits made in the Visio UI are intentionally discarded to show the latest file on disk.
- These helpers do not run shape/page/instance commands. Use the matching `apply_*` API first, save the file, then call `refresh_visio_file()` if the user has that file open in Visio.
- After saving a modified file, use `find_visio_document(output_path)` when Desktop transport is available. If it is already open, ask the user whether to refresh it; if it is not open, ask whether to open it. Do not refresh/open silently unless explicitly requested.

---

## 6. Backend Selection

All `apply_*` functions accept a `backend` keyword. Choose the right value:

| `backend` value | Behavior |
|---|---|
| `"auto"` *(default)* | Prefer Visio Desktop COM; fall back to XML ZIP if COM unavailable. **If a local configuration exists, the default backend defined in it is used.** |
| `"xml"` | Always use XML ZIP writer (cross-platform, no Visio installation needed) |
| `"desktop"` / `"visio"` | Require Visio Desktop COM; raise an error if unavailable (no fallback) |

**Rule of thumb for agents:** use the default `backend="auto"` (which prefers native Desktop Visio COM automation for full formula and layout calculation fidelity) unless native Visio is strictly unavailable (e.g., in headless Linux test runs) and only direct XML zip modifications are supported.

---

## 7. Output Path Rules

- **Default (no `output_path`):** modifications are buffered in memory; `bridge.save(path)` writes to disk.
- **With `output_path`:** the `apply_*` function calls `bridge.save(output_path)` automatically.
- **Never overwrite the source file without explicit user confirmation.** Always default to a new filename (e.g., append `_modified`).

```python
# Safe pattern
apply_skill_commands(bridge, shape_path, commands, backend="xml")
bridge.save("circuit_modified.vstx")   # new file, source untouched
```

After saving, agents may offer a Visio UI follow-up:

```python
doc = find_visio_document("circuit_modified.vstx")
if doc is not None:
    print("Offer to refresh the already-open Visio session.")
else:
    print("Offer to open the saved file in Visio.")
```

Only call `refresh_visio_file()` or `open_visio_file()` after the user confirms, unless the user explicitly asked for automatic refresh/open behavior.

---

## 8. Error Handling & Diagnostics

```python
# Check which backend was actually used after an apply call
print(bridge.last_phase2_backend)         # "xml" or "desktop"
print(bridge.last_phase2_desktop_error)   # None or error string if COM fell back

# If locator returns None, print the manifest and report the failure
element = locator.find("masters/SomeName/shape/5")
if element is None:
    print("Element not found. Valid paths from manifest:")
    print(json.dumps(bridge.parts_manifest(), indent=2, ensure_ascii=False))
```

Common failure modes:

| Symptom | Likely cause | Fix |
|---|---|---|
| `locator.find(...)` returns `None` | Wrong NameU or ID | Call `bridge.parts_manifest()` to list valid paths |
| `ValueError: Could not find Master matching reference` | Master NameU typo | Check `parts_manifest()["masters"]` for correct names |
| `backend="desktop"` raises | No Visio COM / no Parallels | Switch to `backend="xml"` |
| Saved file won't open in Visio | Formula syntax error in a command | Re-read with `to_skill()` and inspect the written cell |

---

## 9. Multi-Step Task Patterns

### Pattern A: Inspect → Edit Master → Save

```python
bridge  = VisioBridge("circuit.vstx")
locator = ElementLocator(bridge)

# 1. Inspect
data = to_skill(locator.find("masters/Cap/shape/5"))

# 2. Plan commands (agent reasoning goes here)
commands = [
    {"action": "update_transform", "property": "Width", "formula": "TheDoc!User.M*2"},
    {"action": "update_transform", "property": "Height", "formula": "TheDoc!User.M*2"},
    {"action": "add_connection_pin", "id": "3", "x": "Width", "y": "Height*0.5", "dir_x": "1", "dir_y": "0"},
]

# 3. Execute
apply_skill_commands(bridge, "masters/Cap/shape/5", commands, backend="xml")
bridge.save("circuit_modified.vstx")
```

### Pattern B: Add Instances → Adjust Settings → Save

```python
bridge = VisioBridge("schematic.vsdx")

# 1. Place components
apply_instance_commands(bridge, [
    {"action": "add_instance", "parent": "pages/Page-1", "master": "Res", "x": "2 in", "y": "3 in"},
    {"action": "add_instance", "parent": "pages/Page-1", "master": "Cap", "x": "4 in", "y": "3 in"},
], backend="xml")

# 2. Update global scale
apply_settings_commands(bridge, [
    {"action": "update_doc_user_cell", "name": "Scale", "value": "2"},
], backend="xml")

bridge.save("schematic_layout.vsdx")
```

### Pattern C: Audit → Review Violations → Apply Selective Fixes

```python
bridge = VisioBridge("circuit.vstx")
report = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)

# Show violations to user
for v in report.violations:
    print(f"[{v.severity}] {v.rule_name}: {v.message} (shape={v.shape_path})")

# Let user decide which groups to apply; here we apply all
groups = plan_design_commands(report)
for g in groups.get("symbol_editor", []):
    apply_skill_commands(bridge, g["target"], g["commands"], backend="xml")
settings_cmds = [cmd for g in groups.get("doc_page_settings", []) for cmd in g["commands"]]
apply_settings_commands(bridge, settings_cmds, backend="xml")

bridge.save("circuit_fixed.vstx")

# Verify
report2 = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
print(f"Remaining violations: {len(report2.violations)}")
```

---

## 10. Absolute Rules for Agents

1. **Read before writing.** Always call `bridge.parts_manifest()` or `to_skill()` / `to_settings_skill()` before generating modification commands.
2. **Never write raw XML.** Use only the `apply_*` functions and the command JSON schema defined in the SKILL.md files.
3. **Never overwrite the source file.** Save to a new path and confirm with the user before replacing originals.
4. **Validate locator paths.** If `locator.find()` returns `None`, stop, report the valid paths from `parts_manifest()`, and ask for clarification.
5. **Default to `backend="auto"`** to ensure Visio evaluates formulas and updates dependent geometries correctly; only use `backend="xml"` when native Visio is unavailable (e.g. cross-platform/Linux environments) or explicitly requested.
6. **Re-audit after bulk fixes.** If you applied `plan_design_commands()` output, run `audit_design()` again to report the remaining violation count.
7. **Batch commands per target.** Pass all commands for the same `shape_path` in a single `apply_skill_commands()` call rather than one call per command.
8. **Do not invent values.** If a formula requires knowledge of the current document's scale or a master's existing dimensions, read them first with `to_skill()` or `to_settings_skill()`.

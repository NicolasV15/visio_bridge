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
from pathlib import Path

# When running from this repository root, import the package from its parent.
sys.path.insert(0, str(Path.cwd().parent))

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
pip install -e .            # core only, when your shell is at this repo root
pip install -e ".[desktop]" # + Visio Desktop COM support (Windows/Parallels)
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

### 2.2 Desktop Session Prerequisites

Visio Desktop session control (`open_visio_file()`, `refresh_visio_file()`, etc.) has extra runtime prerequisites beyond the pure XML backend:

#### Windows Native

In Windows Native mode, Visio Bridge controls the locally installed Microsoft Visio process through Windows COM / `Visio.Application`.

- Microsoft Visio Desktop must be installed on Windows.
- The current Windows user must be able to launch Visio.
- Windows Python must be callable as `python`.
- `pywin32` must be installed so the runner can import `pythoncom` and `win32com.client`.

Recommended checks from Windows PowerShell or Command Prompt:

```bat
python --version
python -c "import pythoncom, win32com.client; print('pywin32 ok')"
python -c "import win32com.client; app = win32com.client.Dispatch('Visio.Application'); print(app.Version); app.Quit()"
```

If `python --version` fails, install Python and ensure it is on the current user's `PATH`. If `import pythoncom` fails, install `pywin32`:

```bat
python -m pip install pywin32
```

#### macOS + Parallels

In macOS + Parallels mode, the macOS side uses the Parallels transport to run a Python/COM runner inside the Windows guest. The guest runner controls Visio through `Visio.Application`.

- The configured Parallels VM must be running.
- The Windows guest must have a real Python interpreter callable as `python` (the Windows Store alias alone is not sufficient).
- The Windows guest must have `pywin32` installed so the runner can import `pythoncom` and `win32com.client`.
- Parallels shared folders must expose the macOS home directory to the guest as `\\Mac\Home`.

Recommended verification commands from macOS:

```bash
prlctl list --all
prlctl exec "<VM name>" --current-user cmd /c python --version
prlctl exec "<VM name>" --current-user cmd /c python -c "import pythoncom, win32com.client; print('ok')"
```

If `python --version` fails, install Python inside the Windows guest:

```bash
prlctl exec "<VM name>" --current-user cmd /c winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
```

If `import pythoncom` fails, install `pywin32` inside the Windows guest:

```bash
prlctl exec "<VM name>" --current-user cmd /c python -m pip install pywin32
```

To verify that the guest can actually see a host file path through Parallels sharing, test the mapped UNC path directly from the Windows guest:

```bash
prlctl exec "<VM name>" --current-user cmd /c python -c "import os; print(os.path.exists(r'\\\\Mac\\Home\\Documents\\path\\to\\file.vstx'))"
```

Agents should run these checks when Desktop session control unexpectedly fails before assuming the Visio file itself is broken.

---

## 3. Intent → SKILL Dispatch Table

Parse the user's instruction and route to the matching SKILL module. When the intent spans multiple modules, execute them **in the order listed below**.

| User intent keywords | Agent skill | Code executor/API |
|---|---|---|
| "读取" / "查看" / "诊断" / "列出" / inspect / read / diagnose / list | [`visio-file-inspector`](skills/visio-file-inspector/SKILL.md) | read-only, no apply |
| "修改形状" / "改几何" / "改引脚" / "画" / edit shape / geometry / pin / draw | [`visio-symbol-editor`](skills/visio-symbol-editor/SKILL.md) | `symbol_editor` via `apply_skill_commands()` |
| "改页面" / "改文档" / "比例" / "页宽" / page size / scale / document settings | [`visio-doc-page-settings`](skills/visio-doc-page-settings/SKILL.md) | `doc_page_settings` via `apply_settings_commands()` |
| "添加形状" / "复制" / "删除形状" / add shape / copy shape / drop / delete instance | [`visio-instance-manager`](skills/visio-instance-manager/SKILL.md) | `instance_manager` via `apply_instance_commands()` |
| "会话" / "打开" / "关闭" / "刷新" / reload / session / open in Visio / close in Visio | [`visio-session-manager`](skills/visio-session-manager/SKILL.md) | `list_visio_documents()` / `open_visio_file()` / `close_visio_file()` / `refresh_visio_file()` |
| "审计" / "检查规范" / "自动修复" / audit / design check / compliance / fix violations | [`visio-design-rules`](skills/visio-design-rules/SKILL.md) | `plan_design_commands()` then `apply_*` |

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
apply_skill_commands(bridge, "masters/NMOS4/shape/5", commands)

# doc_page_settings
apply_settings_commands(bridge, commands)

# instance_manager
apply_instance_commands(bridge, commands)

bridge.save("path/to/output.vstx")
```

---

## 5. Source Of Truth

Keep this file as a router and safety policy. Do not duplicate full command
schemas here.

| Knowledge | Source |
|---|---|
| User intent routing and global safety rules | `AGENTS.md` |
| Skill-specific workflow and command JSON schema | `skills/visio-*/SKILL.md` |
| Actual execution behavior | `src/skill/*.py`, `src/design/*.py`, `src/desktop/*.py` |
| Human-facing usage docs | `README.md`, `README_CN.md`, `docs/` |

If a skill document and code disagree, inspect the code before editing docs or
generating commands. Keep executor keys unchanged: `symbol_editor`,
`doc_page_settings`, and `instance_manager`.

---

## 6. Skill Contracts

Use this section to confirm the right capability, then load the matching skill
for details.

| Skill | Contract | Primary API |
|---|---|---|
| [`visio-file-inspector`](skills/visio-file-inspector/SKILL.md) | Read structure, shapes, settings, themes, windows, or doc props. No writes. | `parts_manifest()`, `ElementLocator`, `to_skill()`, `to_settings_skill()` |
| [`visio-symbol-editor`](skills/visio-symbol-editor/SKILL.md) | Edit shape transforms, geometry, pins, text, style cells, section cells, or shape User cells. | `apply_skill_commands()` |
| [`visio-doc-page-settings`](skills/visio-doc-page-settings/SKILL.md) | Edit DocumentSheet User cells and PageSheet cells/User cells. | `to_settings_skill()`, `apply_settings_commands()` |
| [`visio-instance-manager`](skills/visio-instance-manager/SKILL.md) | Add, copy, or delete shape instances on pages or inside groups. | `apply_instance_commands()` |
| [`visio-design-rules`](skills/visio-design-rules/SKILL.md) | Audit a design profile, plan fix groups, then apply selected groups. | `audit_design()`, `plan_design_commands()` |
| [`visio-session-manager`](skills/visio-session-manager/SKILL.md) | List, find, open, close, or refresh documents in Visio Desktop. Does not apply edit commands. | `list_visio_documents()`, `find_visio_document()`, `open_visio_file()`, `close_visio_file()`, `refresh_visio_file()` |

Load only the matching skill unless the user intent spans multiple capabilities.
When multiple skills are needed, follow the dispatch table order.

---

## 7. Backend Selection

All `apply_*` functions accept a `backend` keyword. Choose the right value:

| `backend` value | Behavior |
|---|---|
| `"auto"` *(default)* | Prefer Visio Desktop COM; fall back to XML ZIP if COM unavailable. **If a local configuration exists, the default backend defined in it is used.** |
| `"xml"` | Always use XML ZIP writer (cross-platform, no Visio installation needed) |
| `"desktop"` / `"visio"` | Require Visio Desktop COM; raise an error if unavailable (no fallback) |

**Rule of thumb for agents:** use the default `backend="auto"` (which prefers native Desktop Visio COM automation for full formula and layout calculation fidelity) unless native Visio is strictly unavailable (e.g., in headless Linux test runs) and only direct XML zip modifications are supported.

---

## 8. Output Path Rules

- **Default (no `output_path`):** modifications are buffered in memory; `bridge.save(path)` writes to disk.
- **With `output_path`:** the `apply_*` function calls `bridge.save(output_path)` automatically.
- **Never overwrite the source file without explicit user confirmation.** Always default to a new filename (e.g., append `_modified`).

```python
# Safe pattern
apply_skill_commands(bridge, shape_path, commands)
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

## 9. Error Handling & Diagnostics

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
| `backend="desktop"` raises | No Visio COM / no Parallels | Use default `backend="auto"` fallback, or force the XML backend only when Desktop fidelity is not required |
| `Visio session command failed (exit 255)` | Windows guest `python` is missing or not callable | Install real Python in the Windows VM and verify `python --version` via `prlctl exec ... cmd /c python --version` |
| `ModuleNotFoundError: No module named 'pythoncom'` | `pywin32` missing in the Windows guest | Run `python -m pip install pywin32` in the Windows VM |
| `pywintypes.com_error ... 文件未找到` / `file not found` while opening in Visio | The mapped `\\Mac\Home\...` path is not accessible from the Windows guest | Verify the UNC path with `os.path.exists(...)` inside the guest; if needed, move/copy the file to a guest-visible path and retry |
| Saved file won't open in Visio | Formula syntax error in a command | Re-read with `to_skill()` and inspect the written cell |

---

## 10. Multi-Step Task Patterns

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
apply_skill_commands(bridge, "masters/Cap/shape/5", commands)
bridge.save("circuit_modified.vstx")
```

### Pattern B: Add Instances → Adjust Settings → Save

```python
bridge = VisioBridge("schematic.vsdx")

# 1. Place components
apply_instance_commands(bridge, [
    {"action": "add_instance", "parent": "pages/Page-1", "master": "Res", "x": "2 in", "y": "3 in"},
    {"action": "add_instance", "parent": "pages/Page-1", "master": "Cap", "x": "4 in", "y": "3 in"},
])

# 2. Update global scale
apply_settings_commands(bridge, [
    {"action": "update_doc_user_cell", "name": "Scale", "value": "2"},
])

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
    apply_skill_commands(bridge, g["target"], g["commands"])
settings_cmds = [cmd for g in groups.get("doc_page_settings", []) for cmd in g["commands"]]
apply_settings_commands(bridge, settings_cmds)

bridge.save("circuit_fixed.vstx")

# Verify
report2 = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
print(f"Remaining violations: {len(report2.violations)}")
```

---

## 11. Absolute Rules for Agents

1. **Read before writing.** Always call `bridge.parts_manifest()` or `to_skill()` / `to_settings_skill()` before generating modification commands.
2. **Never write raw XML.** Use only the `apply_*` functions and the command JSON schema defined in the matching `skills/visio-*/SKILL.md`.
3. **Never overwrite the source file.** Save to a new path and confirm with the user before replacing originals.
4. **Validate locator paths.** If `locator.find()` returns `None`, stop, report the valid paths from `parts_manifest()`, and ask for clarification.
5. **Default to `backend="auto"`** to ensure Visio evaluates formulas and updates dependent geometries correctly; only use `backend="xml"` when native Visio is unavailable (e.g. cross-platform/Linux environments) or explicitly requested.
6. **Re-audit after bulk fixes.** If you applied `plan_design_commands()` output, run `audit_design()` again to report the remaining violation count.
7. **Batch commands per target.** Pass all commands for the same `shape_path` in a single `apply_skill_commands()` call rather than one call per command.
8. **Do not invent values.** If a formula requires knowledge of the current document's scale or a master's existing dimensions, read them first with `to_skill()` or `to_settings_skill()`.

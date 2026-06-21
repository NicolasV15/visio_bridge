# Visio Bridge

**A Python toolkit for parsing, locating, extracting, and modifying modern Visio files (`.vsdx` / `.vstx` / `.vssx`) — purpose-built for AI Agent automation, component configuration, and read-only diagnostic analysis.**

[中文版](README_CN.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/version-0.1.1-blue)
![Dependencies](https://img.shields.io/badge/dependencies-zero_(stdlib_only)-brightgreen)

---

## ✨ Features

- **Multi-format support** — Read and write `.vsdx` (drawings), `.vstx` (templates), and `.vssx` (stencils) out of the box.
- **Zero dependencies** — Pure Python standard library; no third-party packages required for core functionality.
- **OPC relationship mapping** — Automatically resolves Masters, Pages, Themes, Windows, and DocProps through the OPC relationship chain. `parts_manifest()` provides a full topology map with zero manual parsing.
- **Unified locator engine** — `ElementLocator.find(path)` supports precise and fuzzy multi-level path navigation across masters, pages, document settings, themes, windows, and metadata.
- **AI-native SKILL interface** — Structured SKILL modules let AI agents read, edit, manage, and control Visio files through Python APIs and JSON command lists — no raw XML required.
- **Formula cache engine** — Automatic ShapeSheet formula recalculation with master/instance scope support, inheritance chain resolution, and Visio-compatible `F="Inh"` cache synchronization.
- **Dual backend architecture** — Write via XML ZIP (cross-platform) or Visio Desktop COM API (Windows / macOS via Parallels); write calls require an explicit backend that matches local configuration.
- **Visio session management** — Detect documents open in Visio Desktop, open/close files, and refresh a document after Visio Bridge updates it on disk.
- **Design rule framework** — Pluggable audit profiles (`DesignProfile`) for automated style compliance checking, violation reporting, and suggested fix planning.

---


## 📦 Installation

### From source (recommended)

```bash
# Clone the repository
git clone --branch latest https://github.com/NicolasV15/visio_bridge.git

# Install in editable mode from the parent directory
pip install -e ./visio_bridge
```

`latest` tracks the most recent published release. Replace it with a fixed
tag such as `v0.1.1` when you need a reproducible snapshot.

> **Note**: The core library has **zero third-party dependencies** — it uses only Python standard library modules.

### Optional: Visio Desktop COM backend

For Visio Desktop COM automation (Windows / macOS via Parallels):

```bash
pip install -e "./visio_bridge[desktop]"
```

This installs `pywin32` for COM interop. The modification entry points (`apply_skill_commands`, `apply_settings_commands`, `apply_instance_commands`) require an explicit `backend="desktop"` or `backend="xml"` argument. The requested backend must match `.visio_bridge.json`; mismatches and missing backend configuration are hard errors.

**Windows Native prerequisites:**
- Python 3.12 with `python` in the current user's `PATH`
- `pywin32`: `python -m pip install pywin32`
- Visio Desktop installed with `Visio.Application` COM ProgID available

**macOS + Parallels prerequisites:**
- [Parallels Desktop](https://www.parallels.com/) with a Windows VM
- Python 3.12 and `pywin32` installed inside the Windows VM
- Visio Desktop installed inside the Windows VM
- `.visio_bridge.json` must set `"desktop_transport_mode": "parallels"` and a concrete `"vm_name"`.

**Linux prerequisites:**
- Python 3.10+
- Configure `"backend": "xml"` and pass `backend="xml"` explicitly for write calls.

### Configuring VM and Backend Preferences

You can customize the default VM name, preferred backend, and automation window visibility settings by running the configuration setup utility:

```bash
# Run the setup tool
visio-bridge-setup

# Or run via Python module directly
python -m visio_bridge.src.core.setup_cli
```

This generates a local `.visio_bridge.json` configuration file in the working directory to store VM names and backend overrides dynamically.
- Desktop transports send runner code and command payloads over stdin/stdout and read/write the target Visio paths directly; no host or VM staging files are created.

## 🔄 Dual-Backend Architecture

Visio Bridge employs a hybrid, dual-backend architecture to balance cross-platform efficiency with full application fidelity.

### 1. Direct XML ZIP Backend (`xml`)
Directly extracts, parses, modifies, and re-packages the Open XML files (`.vsdx`/`.vstx`/`.vssx`) using standard libraries.
* **Pros**: 
  - **Cross-platform**: Runs natively on macOS, Linux, and Windows.
  - **Extremely Fast**: Executes modifications in milliseconds.
  - **Zero-Dependency**: Requires only standard Python libraries (no Microsoft Visio installation needed).
  - **Highly Stable**: No GUI side-effects, hidden popup dialog blocks, or licensing hangs.
* **Cons**:
  - Does not evaluate complex Excel-like formulas or geometry dependencies natively (modified cells are written, but dependent cell *cache values* are not recalculated unless Visio opens them or you use the explicit `recalculate_formula_cache` SKILL API).
  - Cannot export PDF or render shape image previews directly.

### 2. Visio Desktop COM Backend (`desktop`)
Controls a real, headless/headed instance of Microsoft Visio via `pywin32` COM APIs. On macOS, this runs inside a Parallels Desktop Windows VM via CLI transport (`prlctl`).
* **Pros**:
  - **100% Fidelity**: Visio engine naturally recalculates all complex cell formulas, shape behaviors, stencils, and geometry rules.
  - **Rendering Support**: Can render/preview shapes or save/export drawing previews directly.
* **Cons**:
  - **Platform Lock-in**: Requires a Windows host or macOS Parallels Desktop VM.
  - **Prerequisites**: Must have a licensed Microsoft Visio Desktop installation.
  - **Slower Performance**: Takes 1 to 3 seconds per run to launch/attach the application and open files.
  - **Interactivity Risks**: Can hang if Visio displays modal error dialogs or prompts.

### Backend Configuration
* **Explicit mode required**: write calls must pass `backend="desktop"` or `backend="xml"`.
  - The requested backend must match `.visio_bridge.json`.
  - Desktop mode also requires an explicit `desktop_transport_mode` (`"windows-local"` or `"parallels"`).
  - XML mode is available only when both the config and call select `xml`.
* **Recommendation**: Use `backend="desktop"` with matching config for full cell formula calculation and layout fidelity. Use `backend="xml"` only when XML writing is intentionally configured.

### Visio Desktop Session Management

The Desktop transport also exposes helpers for managing the user's current Visio instance:

```python
from visio_bridge import (
    list_visio_documents,
    open_visio_file,
    close_visio_file,
    refresh_visio_file,
)

print(list_visio_documents())
open_visio_file("circuit_modified.vsdx")

# After an XML backend save, close and reopen the matching Visio document.
# Default refresh behavior discards unsaved edits made in the Visio UI.
refresh_visio_file("circuit_modified.vsdx")
```

`refresh_visio_file()` is implemented as a close-and-reopen operation because Visio does not expose a general in-place reload for an already-open Open XML document. By default it uses `discard_unsaved=True`, so the reopened document reflects the latest file on disk.

### 🤖 AI Agent Integration & Playbook

Visio Bridge is designed from the ground up for AI automation. We provide two levels of agent guidelines:

#### 1. Repository-Level Agent Playbook ([`AGENTS.md`](AGENTS.md))
If you are using an AI coding assistant (such as **Cursor**, **Claude Code**, or **Gemini CLI**) to edit files or build tools inside this repository, **feed the agent the [`AGENTS.md`](AGENTS.md) playbook**. It teaches the agent:
* How the workspace is organized.
* How to use the `to_skill()` read and `apply_*` execution workflow.
* Which backend transport settings and `.visio_bridge.json` options to select.
* The absolute rules of safe editing (e.g., read before writing, no raw XML edits).

#### 2. Module-Level Prompts (`SKILL.md`)
For granular tasks where you call an LLM programmatically to edit shapes or documents, each SKILL module contains a dedicated prompt template (`SKILL.md`) specifying inputs, roles, and output schemas:

| Agent Role | System Prompt | Execute with |
|---|---|---|
| Shape geometry editor | [`skills/visio-symbol-editor/SKILL.md`](skills/visio-symbol-editor/SKILL.md) | `apply_skill_commands()` |
| Document & page settings | [`skills/visio-doc-page-settings/SKILL.md`](skills/visio-doc-page-settings/SKILL.md) | `apply_settings_commands()` |
| Read-only file inspector | [`skills/visio-file-inspector/SKILL.md`](skills/visio-file-inspector/SKILL.md) | *(read-only, no apply needed)* |
| Shape instance manager | [`skills/visio-instance-manager/SKILL.md`](skills/visio-instance-manager/SKILL.md) | `apply_instance_commands()` |
| Visio desktop session manager | [`skills/visio-session-manager/SKILL.md`](skills/visio-session-manager/SKILL.md) | `list_visio_documents()` / `refresh_visio_file()` |
| Design rule auditor | [`skills/visio-design-rules/SKILL.md`](skills/visio-design-rules/SKILL.md) | `plan_design_commands()` |

### Install And Update Codex Skills

Install the latest published skill set:

```bash
python scripts/update_codex_skills.py
```

Install a specific published version:

```bash
python scripts/update_codex_skills.py --ref v0.1.1
```

Install only selected skills:

```bash
python scripts/update_codex_skills.py --skills visio-file-inspector visio-symbol-editor
```

The helper replaces the existing local copy of each skill in
`~/.codex/skills/<skill-name>` before installing the new version. Use a fixed
tag when you need a reproducible snapshot, and rerun the command whenever you
want to update to a newer release.

After any skill update, restart Codex to pick up the new skills.

---

## 🔧 Core Capabilities

### Capability 1: Foundation & Multi-format Adaptation (Core)

| Capability | Description |
|---|---|
| **Multi-format ZIP I/O** | Parse and rewrite `.vsdx`, `.vstx`, and `.vssx` files directly |
| **Relational Mapping** | Follow OPC relationship chains to dynamically associate Masters, Pages, Themes, Windows, and DocProps to their underlying XML paths. `bridge.parts_manifest()` provides the full topology with zero manual parsing |
| **Locator Engine** | `ElementLocator.find(path)` supports precise and fuzzy multi-level navigation |

Supported locator path formats:

| Path | Target |
|---|---|
| `masters/<NameU_or_ID>/shape/<ID>` | Master shape element |
| `document` / `document/sheet` | Document root / DocumentSheet |
| `pages/<NameU_or_ID>/shape/<ID>` | Page shape element |
| `theme/0` | DrawingML theme root |
| `windows` | Windows state |
| `doc_props/core\|app\|custom` | OPC document properties |

---

### Capability 2: SKILL Bidirectional Interface (Processing & SKILL Interface)

Structured SKILL modules provide complete read/write and session-control capabilities for AI agents:

#### 1. Symbol Editor (`visio-symbol-editor`, executor `symbol_editor`)

Manipulate component geometry, connection pins, and shape properties:

| Action | Description |
|---|---|
| `update_transform` | Update bounding box properties (Width, Height, etc.) with values or formulas |
| `set_shape_cell` | Update generic shape/style cells such as LineWeight, LineColor, or FillPattern |
| `recalculate_formula_cache` | Recalculate formula cache for a master or page instance scope |
| `add_connection_pin` | Add connection pins with X/Y coordinates and direction vectors |
| `delete_connection_pin` | Remove connection pins by ID |
| `draw_rectangle` | Draw and fill a rectangular geometry path |
| `draw_line` | Draw a line segment geometry path |
| `draw_circle` | Draw and fill a self-adaptive circle with formula-linked center and radius |
| `draw_ellipse` | Draw and fill a closed ellipse from bounding box coordinates |
| `draw_elliptical_arc` | Draw an elliptical arc with arbitrary start and sweep angles |
| `modify_geometry` | Dynamically modify vertex coordinates of existing geometry paths |
| `update_text` | Update shape text content |
| `update_shape_user_cell` | Modify or create shape-level custom variables |
| `delete_shape_user_cell` | Delete shape-level custom variables |
| `set_section_cell` | Update or create a cell in a named section row |
| `delete_section_row` | Delete a row from a named section |

**Formula cache recalculation behavior:**
- Writing to a master shape triggers recalculation of the master and its Master PageSheet.
- Writing to a page instance recalculates the instance subtree only; master and other shapes are untouched.
- Instance local overrides take priority over master definitions; inherited formulas are evaluated in the instance effective context.
- Inherited formulas affected by overrides are written as Visio-style cache: `F="Inh"` + computed `V` + inherited `U`.
- Dirty scopes are automatically flushed before `bridge.save()`.

#### 2. Document & Page Settings (`visio-doc-page-settings`, executor `doc_page_settings`)

Extract and modify global configuration and page parameters:

| Action | Description |
|---|---|
| `update_doc_user_cell` | Update or create global DocumentSheet User cells (e.g., scale multiplier `M`) |
| `delete_doc_user_cell` | Delete global custom variables from DocumentSheet |
| `update_page_cell` | Update page properties (PageWidth, PageHeight, PageScale, DrawingScale, DrawingSizeType, DrawingScaleType) |
| `update_page_user_cell` | Update or create page-level custom variables |
| `delete_page_user_cell` | Delete page-level custom variables |

#### 3. Instance Manager (`visio-instance-manager`, executor `instance_manager`)

Manage shape instances at the structural/page level:

| Action | Description |
|---|---|
| `add_instance` | Create a new shape instance of a Master on a page or inside a group container |
| `copy_instance` | Clone an existing shape instance to a new location |
| `delete_instance` | Remove a shape instance and all its descendants |

#### 4. File Inspector (`visio-file-inspector`)

Read-only deep inspection of any Visio XML structure:

| Strategy | Target | Description |
|---|---|---|
| **A** (Visio Masters) | `masters/<Name>/shape/<ID>` | Extract geometry, pins, transforms, text, and formulas |
| **B** (Pages & Document) | `pages/<Name>`, `document/sheet` | Extract page dimensions, global formulas (User.Scale, etc.) |
| **C** (DrawingML Theme) | `theme/0` | Read theme color palettes and accent configurations |
| **D** (Windows State) | `windows` | View window layout, zoom levels, and active workspace |
| **E** (OPC Doc Properties) | `doc_props/core\|app\|custom` | Extract Dublin Core metadata, app properties, and custom properties |

---

### Capability 3: Design Rules & Automation Framework (Design Rules)

| Capability | Description |
|---|---|
| **Generic Design Profiles** | Express design style or template constraints through `DesignProfile` / `DesignRule`. Not limited to circuit diagrams — statistical charts, flowcharts, and layout templates can all be registered as new profiles |
| **Read-only Audit** | `audit_design()` reads a Visio file using Phase 1 & 2 capabilities and outputs a structured `DesignReport` |
| **Suggested Fix Planning** | `plan_design_commands()` groups fixable suggestions by executor without modifying the file |
| **Auto-generated Profile Docs** | `describe_design_profile()` and `render_design_profile_markdown()` produce complete rule documentation from the Profile's structured `spec` |
| **Capability Adapter Layer** | `DesignCapabilityRegistry` unifies reader and command adapters. New read/write capabilities from Phase 1 & 2 can be registered into Phase 3 without rewriting the rule engine |

**Built-in Circuit Schematic Profile** (`CIRCUIT_SCHEMATIC_PROFILE`):
- **Component rules**: Top-level Master structure, center anchors, dimension formulas, grid units, pin positions, pin directions, scalable geometry
- **Connector rules**: Shared connector Master, line weights, connector instance usage, grid and direction conventions
- **Document/page rules**: Recommended `User.Scale`, `User.M`, `User.LW`; page dimensions remain unconstrained

---

## 📖 API Reference

### Core Classes

| Class / Function | Import | Description |
|---|---|---|
| `VisioBridge` | `from visio_bridge import VisioBridge` | Core class for ZIP I/O, XML caching, and relationship resolution |
| `ElementLocator` | `from visio_bridge import ElementLocator` | Unified path-based element navigation |
| `FormulaCacheResult` | `from visio_bridge import FormulaCacheResult` | Result container for formula recalculation |
| `recalculate_formula_cache` | `from visio_bridge import recalculate_formula_cache` | Low-level formula recalculation API |

### SKILL Functions

| Function | Import | Description |
|---|---|---|
| `to_skill(shape)` | `from visio_bridge import to_skill` | Convert a shape element to AI-readable JSON format |
| `apply_skill_commands(bridge, path, cmds, backend="desktop")` | `from visio_bridge import apply_skill_commands` | Execute symbol editor commands with an explicit backend |
| `to_settings_skill(bridge)` | `from visio_bridge import to_settings_skill` | Extract document & page settings as structured JSON |
| `apply_settings_commands(bridge, cmds, backend="desktop")` | `from visio_bridge import apply_settings_commands` | Execute document/page settings commands with an explicit backend |
| `apply_instance_commands(bridge, cmds, backend="desktop")` | `from visio_bridge import apply_instance_commands` | Execute instance management commands with an explicit backend |

### Desktop Backend

| Class / Function | Import | Description |
|---|---|---|
| `VisioDesktopSession` | `from visio_bridge import VisioDesktopSession` | Visio COM automation session manager |
| `VisioSessionManager` | `from visio_bridge import VisioSessionManager` | Runs Visio Desktop session-control actions |
| `VisioDocumentSessionInfo` | `from visio_bridge import VisioDocumentSessionInfo` | Open document session metadata |
| `VisioSessionActionResult` | `from visio_bridge import VisioSessionActionResult` | Open/close/refresh action result |
| `list_visio_documents()` | `from visio_bridge import list_visio_documents` | List documents currently open in Visio Desktop |
| `find_visio_document(path)` | `from visio_bridge import find_visio_document` | Find an already-open Visio document by path |
| `open_visio_file(path)` | `from visio_bridge import open_visio_file` | Open a file in Visio or activate it if already open |
| `close_visio_file(path)` | `from visio_bridge import close_visio_file` | Close an open Visio document, refusing unsaved UI changes by default |
| `refresh_visio_file(path)` | `from visio_bridge import refresh_visio_file` | Close and reopen a file so Visio reflects the latest disk contents |
| `ParallelsTransport` | `from visio_bridge import ParallelsTransport` | macOS → Windows VM transport via Parallels |
| `LocalWindowsTransport` | `from visio_bridge import LocalWindowsTransport` | Native Windows transport |
| `create_default_transport()` | `from visio_bridge import create_default_transport` | Create the transport from explicit configuration |

### Design Framework

| Class / Function | Import | Description |
|---|---|---|
| `audit_design(bridge, profile)` | `from visio_bridge import audit_design` | Run a read-only design audit |
| `plan_design_commands(report)` | `from visio_bridge import plan_design_commands` | Plan fix commands grouped by executor |
| `render_design_profile_markdown(profile)` | `from visio_bridge import render_design_profile_markdown` | Generate profile documentation as Markdown |
| `CIRCUIT_SCHEMATIC_PROFILE` | `from visio_bridge import CIRCUIT_SCHEMATIC_PROFILE` | Built-in unified-style circuit schematic profile |

---

## 🗺️ Roadmap

### Phase 4: Human-AI Collaboration Protocol (Planned)

Establish a protocol where human developers provide high-level semantic constraints via prompts, and AI agents understand and deliver results as SKILL JSON command lists.

---

## ❓ FAQ

<details>
<summary><strong>Why use XML instead of Visio COM API?</strong></summary>

Visio Bridge's core is built on direct XML parsing because:
1. **Cross-platform** — Works on macOS and Linux without requiring Visio installation
2. **Deterministic** — No UI side effects, hidden dialogs, or race conditions
3. **AI-friendly** — Structured XML access is easier for AI agents to reason about
4. **Lightweight** — Zero dependencies; no COM interop overhead

When higher fidelity is needed (e.g., formula evaluation or rendering), the optional Desktop Backend provides COM automation. XML writes require both `"backend": "xml"` in config and `backend="xml"` in the call.
</details>

<details>
<summary><strong>Which Visio file formats are supported?</strong></summary>

Visio Bridge supports all modern Open XML-based Visio formats:
- **`.vsdx`** — Visio Drawing (editable documents)
- **`.vstx`** — Visio Template (reusable templates)
- **`.vssx`** — Visio Stencil (shape library files)

Legacy binary formats (`.vsd`, `.vst`, `.vss`) are **not** supported.
</details>

<details>
<summary><strong>How do I use the Visio Desktop backend?</strong></summary>

Configure `"backend": "desktop"` and pass `backend="desktop"` explicitly.
Visio Bridge does not infer or switch write modes at runtime.

**Windows Native**

1. Install Microsoft Visio Desktop on Windows.
2. Ensure the current Windows user can launch Visio.
3. Ensure `python` is available in that Windows user environment.
4. Install `pywin32`: `python -m pip install pywin32`.

**macOS + Parallels**

1. Install [Parallels Desktop](https://www.parallels.com/) with a Windows VM
2. Install Python 3.12 and `pywin32` inside the Windows VM
3. Install Visio Desktop inside the Windows VM
4. Set `"desktop_transport_mode": "parallels"` and `"vm_name": "<your VM>"` in `.visio_bridge.json`

```python
# Windows Native or macOS + Parallels
apply_skill_commands(bridge, path, commands, backend="desktop")
```
</details>

<details>
<summary><strong>How do I add a custom Design Profile?</strong></summary>

Create a new profile using the `DesignProfile` and `DesignRule` models:

```python
from visio_bridge import DesignProfile, DesignRule, RuleSeverity

my_profile = DesignProfile(
    name="My Custom Profile",
    description="Custom design rules for my template",
    rules=[
        DesignRule(
            id="my-rule-001",
            name="Page Size Check",
            severity=RuleSeverity.WARNING,
            # ... define check function and fix suggestion
        ),
    ],
)

# Run audit with custom profile
report = audit_design(bridge, my_profile)
```

Register new read/write capabilities via `DesignCapabilityRegistry` to extend what rules can check and fix.
</details>

---

## 📚 Examples

For detailed code examples covering all modules, see:

- 📖 [Examples (English)](docs/examples.md)
- 📖 [示例文档 (中文)](docs/examples_cn.md)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2024 Visio Bridge Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

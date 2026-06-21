---
name: visio-design-rules
description: Audit Visio files against design profiles and plan structured fixes. Use for 审计, 检查规范, 自动修复, design check, compliance, audit, violations, style profile, circuit schematic profile, or planning bulk fixes through doc_page_settings, symbol_editor, and instance_manager.
---

# Visio Design Rules

Use this skill to run read-only design audits and convert reported fixes into
executor command groups. Do not edit raw XML.

## Audit

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, audit_design, CIRCUIT_SCHEMATIC_PROFILE

bridge = VisioBridge("input.vstx")
report = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
```

`audit_design()` is read-only.

## Describe A Profile

Use generated profile documentation instead of hand-writing rule descriptions:

```python
from visio_bridge import CIRCUIT_SCHEMATIC_PROFILE, render_design_profile_markdown

print(render_design_profile_markdown(CIRCUIT_SCHEMATIC_PROFILE))
```

## Plan Fixes

```python
from visio_bridge import plan_design_commands

groups = plan_design_commands(report)
print(json.dumps(groups, indent=2, ensure_ascii=False))
```

Command groups are keyed by executor:

| Executor key | Apply with |
|---|---|
| `doc_page_settings` | `apply_settings_commands(bridge, commands)` |
| `symbol_editor` | `apply_skill_commands(bridge, group["target"], commands)` |
| `instance_manager` | `apply_instance_commands(bridge, commands)` |

Keep these underscore executor keys; they are the code-level API contract.

## Apply Policy

1. Run an audit first.
2. Review severity, target, message, and suggested fixes.
3. Apply only groups that match the user's requested scope.
4. Save to a new output path unless overwriting was explicitly confirmed.
5. Re-run `audit_design()` and report remaining violations.

Example application loop:

```python
from visio_bridge import apply_skill_commands, apply_settings_commands, apply_instance_commands

for group in groups.get("symbol_editor", []):
    apply_skill_commands(bridge, group["target"], group["commands"])

settings_cmds = [cmd for group in groups.get("doc_page_settings", []) for cmd in group["commands"]]
if settings_cmds:
    apply_settings_commands(bridge, settings_cmds)

instance_cmds = [cmd for group in groups.get("instance_manager", []) for cmd in group["commands"]]
if instance_cmds:
    apply_instance_commands(bridge, instance_cmds)

bridge.save("input_fixed.vstx")
```

`symbol_editor` fixes may include lower-level actions such as `set_shape_cell`
and `set_section_cell`; these are supported by both XML and Desktop backends.

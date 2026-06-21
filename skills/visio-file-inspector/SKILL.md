---
name: visio-file-inspector
description: Read-only Visio file inspection for .vsdx, .vstx, and .vssx files. Use when asked to 读取, 查看, 诊断, 列出, inspect, read, diagnose, list, summarize, or locate document structure, masters, pages, shapes, themes, windows, or document properties without modifying the file.
---

# Visio File Inspector

Use this skill to inspect Visio files without writing anything. Never call
`apply_*` functions or `bridge.save()` while using this skill.

## Setup

When running from the repository root, make the package importable from its
parent directory:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, ElementLocator, to_skill, to_settings_skill
```

## Workflow

1. Open the file with `VisioBridge(path)`.
2. If the requested target is not exact, print `bridge.parts_manifest()` first.
3. Resolve concrete targets with `ElementLocator(bridge).find(path)`.
4. Use the structured reader that matches the part type.
5. Report a concise human summary plus raw JSON for structured data.

## Locator Paths

| Path | Meaning |
|---|---|
| `masters/<NameU_or_ID>` | Master root |
| `masters/<NameU_or_ID>/shape/<ID>` | Shape inside a master |
| `masters/<NameU_or_ID>/shape/<ID>/cell/<CellName>` | Shape cell |
| `masters/<NameU_or_ID>/shape/<ID>/section/<SectionName>` | Shape section |
| `masters/<NameU_or_ID>/shape/<ID>/section/<SectionName>/row/<N_or_IX>` | Section row |
| `pages/<NameU_or_ID>` | Page root |
| `pages/<NameU_or_ID>/shape/<ID>` | Shape on a page |
| `document` | `visio/document.xml` root |
| `document/sheet` | DocumentSheet |
| `theme/0` or `theme/<name>` | DrawingML theme root |
| `windows` | Visio window state |
| `doc_props/core` | Core document properties |
| `doc_props/app` | App document properties |
| `doc_props/custom` | Custom document properties |

If `find(path)` returns `None`, stop and show the relevant manifest entries
instead of guessing a path.

## Readers

Use `to_skill(shape)` for shape geometry, transforms, text, connection pins,
sections, and child shapes:

```python
bridge = VisioBridge("circuit.vstx")
locator = ElementLocator(bridge)
shape = locator.find("masters/Cap/shape/5")
if shape is None:
    print(json.dumps(bridge.parts_manifest(), indent=2, ensure_ascii=False))
else:
    print(json.dumps(to_skill(shape), indent=2, ensure_ascii=False))
```

Use `to_settings_skill(bridge)` for document user cells and page settings:

```python
settings = to_settings_skill(bridge)
print(json.dumps(settings, indent=2, ensure_ascii=False))
```

Use raw `xml.etree.ElementTree` reads only for non-SKILL parts such as themes,
windows, and document properties. Do not modify those elements.

## Output

Provide:

1. A short summary of what was inspected and the important values found.
2. A fenced `json` block with the raw manifest, `to_skill()`, or
   `to_settings_skill()` data when available.

Do not invent missing values. Report absent fields as absent.

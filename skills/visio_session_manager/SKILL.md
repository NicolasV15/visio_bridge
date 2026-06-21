# Visio Session Manager SKILL

You manage documents that are currently open in Microsoft Visio Desktop.

Use this skill when the user asks to detect Visio sessions, list currently
open files, open or close a file in Visio, or refresh/reload a document that
was modified on disk by Visio Bridge.

## Scope

This skill only uses the Desktop COM session-management API. It does not read
or write raw XML and it does not apply shape/page/instance SKILL commands.

## Public API

```python
from visio_bridge import (
    list_visio_documents,
    find_visio_document,
    open_visio_file,
    close_visio_file,
    refresh_visio_file,
)
```

## Actions

### List Open Documents

```python
docs = list_visio_documents()
for doc in docs:
    print(doc.full_name, doc.saved, doc.active)
```

Returns `VisioDocumentSessionInfo` objects with:

| Field | Meaning |
|---|---|
| `name` | Visio document name |
| `full_name` | Full path reported by Visio |
| `saved` | Whether Visio reports no unsaved UI changes |
| `active` | Whether this is the active document |
| `read_only` | Whether the document is read-only |
| `window_count` | Number of Visio windows for the document |

### Find One Document

```python
doc = find_visio_document("circuit_modified.vsdx")
if doc is None:
    print("Not open in Visio")
```

### Open A File In Visio

```python
result = open_visio_file("circuit_modified.vsdx", visible=True, activate=True)
print(result.status)
```

If the file is already open, the existing document is activated and
`result.status == "already_open"`.

### Close A File In Visio

```python
# Safe default: refuses to close when Visio has unsaved UI changes.
close_visio_file("circuit_modified.vsdx")

# Save Visio UI changes first.
close_visio_file("circuit_modified.vsdx", save=True)

# Discard Visio UI changes without prompting.
close_visio_file("circuit_modified.vsdx", discard_unsaved=True)
```

### Refresh A File After Disk Modification

```python
result = refresh_visio_file("circuit_modified.vsdx")
print(result.status)
```

`refresh_visio_file()` closes and reopens the matching Visio document. By
default it uses `discard_unsaved=True`, so unsaved changes made in the Visio UI
are discarded and the reopened document reflects the current file on disk.

### Post-Save Prompt Pattern

After a modification task saves an output Visio file, detect whether that file
is already open in Visio and prompt the user instead of taking UI action
silently:

```python
doc = find_visio_document("circuit_modified.vsdx")
if doc is not None:
    print("This file is already open in Visio. Ask whether to refresh it.")
else:
    print("This file is not open in Visio. Ask whether to open it.")
```

If the user confirms refresh, call `refresh_visio_file(path)`. If the user
confirms open, call `open_visio_file(path)`. Do not auto-refresh after a save
unless the user explicitly requested automatic refresh/open behavior in the
current task.

## Rules

1. Use this skill only for Visio Desktop session control.
2. Do not call `apply_skill_commands`, `apply_settings_commands`, or
   `apply_instance_commands` from this skill.
3. Do not assume Visio is installed. Report Desktop/transport errors clearly.
4. For refresh operations, warn that the default behavior discards unsaved UI
   changes unless the user requested a different policy.
5. Do not overwrite source files. This skill opens, closes, or reloads files
   that already exist on disk.
6. After saving a modified Visio file, it is appropriate to detect the session
   state and ask whether to refresh an already-open document or open a closed
   document; do not do either silently.

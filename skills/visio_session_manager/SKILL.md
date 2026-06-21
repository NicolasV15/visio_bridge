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

## Environment Checklist

Before using this skill on macOS + Parallels, verify the Desktop session
environment, not just the Visio file:

- The configured Parallels VM is running.
- The Windows guest has a real Python interpreter callable as `python`.
- The Windows guest has `pywin32` installed so the runner can import
  `pythoncom` and `win32com.client`.
- Parallels shared folders expose the macOS home directory as `\\Mac\Home`.

Recommended checks:

```bash
prlctl list --all
prlctl exec "<VM name>" --current-user cmd /c python --version
prlctl exec "<VM name>" --current-user cmd /c python -c "import pythoncom, win32com.client; print('ok')"
prlctl exec "<VM name>" --current-user cmd /c python -c "import os; print(os.path.exists(r'\\\\Mac\\Home\\Documents\\path\\to\\file.vstx'))"
```

If `python --version` fails, install Python inside the Windows guest:

```bash
prlctl exec "<VM name>" --current-user cmd /c winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
```

If `import pythoncom` fails, install `pywin32` inside the Windows guest:

```bash
prlctl exec "<VM name>" --current-user cmd /c python -m pip install pywin32
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

On macOS + Parallels, these helpers open host files by mapping paths below the
macOS home directory to `\\Mac\Home\...` inside the Windows guest. If Visio
reports "file not found", verify the mapped UNC path from the guest before
assuming the document or the API call is invalid.

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
7. If the session runner fails with `exit 255`, check whether `python` is
   actually callable inside the Windows guest before debugging Visio itself.
8. If the runner raises `ModuleNotFoundError: No module named 'pythoncom'`,
   install `pywin32` in the guest.
9. If Visio raises "file not found", verify `\\Mac\Home\...` accessibility from
   the Windows guest before changing the open/refresh flow.

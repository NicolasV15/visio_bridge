---
name: visio-session-manager
description: Manage Microsoft Visio Desktop sessions through the Visio Bridge Desktop COM transport. Use for 会话, 打开, 关闭, 刷新, reload, session, list open Visio documents, open in Visio, close in Visio, refresh after disk modification, or Parallels Desktop troubleshooting.
---

# Visio Session Manager

Use this skill only for Microsoft Visio Desktop session control. It does not
read or write raw XML and does not apply shape, page, or instance commands.

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

List open documents:

```python
docs = list_visio_documents()
for doc in docs:
    print(doc.full_name, doc.saved, doc.active)
```

Find one document:

```python
doc = find_visio_document("input_modified.vsdx")
print(doc.full_name if doc else "not open")
```

Open or activate a file:

```python
result = open_visio_file("input_modified.vsdx", visible=True, activate=True)
print(result.status)
```

Close a file:

```python
close_visio_file("input_modified.vsdx")
```

The safe default refuses to close a document with unsaved Visio UI changes. Use
`save=True` to save UI changes or `discard_unsaved=True` only when the user
explicitly approves discarding them.

Refresh a file after disk modification:

```python
result = refresh_visio_file("input_modified.vsdx")
print(result.status)
```

`refresh_visio_file()` closes and reopens the file. By default it discards
unsaved Visio UI changes, so warn the user unless they already requested that
behavior.

## Post-Save Pattern

After a Visio Bridge modification saves an output file, detect session state
and ask before taking UI action:

```python
doc = find_visio_document("input_modified.vsdx")
if doc is not None:
    print("Ask whether to refresh the already-open document.")
else:
    print("Ask whether to open the saved document in Visio.")
```

Do not refresh or open silently unless the user explicitly requested it in the
current task.

## Runtime Environments

### Windows Native

In Windows Native mode, Visio Bridge controls the locally installed Microsoft
Visio process through Windows COM / `Visio.Application`.

Prerequisites:

- Microsoft Visio Desktop is installed on Windows.
- The current Windows user can launch Visio.
- Windows Python is callable as `python`.
- `pywin32` is installed in that Python environment.

Recommended checks from Windows PowerShell or Command Prompt:

```bat
python --version
python -c "import pythoncom, win32com.client; print('pywin32 ok')"
python -c "import win32com.client; app = win32com.client.Dispatch('Visio.Application'); print(app.Version); app.Quit()"
```

If `python --version` fails, install Python and ensure it is on the current
user's `PATH`. If `pythoncom` or `win32com.client` is missing, install
`pywin32` with `python -m pip install pywin32`.

### macOS + Parallels

In macOS + Parallels mode, the macOS side invokes a Parallels transport. The
transport runs a Python/COM runner inside the Windows guest, which then controls
Visio through `Visio.Application`.

Prerequisites:

- The configured Parallels VM is running.
- The Windows guest has a real Python interpreter callable as `python`.
- The Windows guest has `pywin32` installed.
- Parallels shared folders expose the macOS home directory as `\\Mac\Home`.

Recommended checks from macOS:

```bash
prlctl list --all
prlctl exec "<VM name>" --current-user cmd /c python --version
prlctl exec "<VM name>" --current-user cmd /c python -c "import pythoncom, win32com.client; print('ok')"
prlctl exec "<VM name>" --current-user cmd /c python -c "import os; print(os.path.exists(r'\\\\Mac\\Home\\Documents\\path\\to\\file.vstx'))"
```

- If `python --version` fails, install a real Python in the Windows guest.
- If `pythoncom` is missing, install `pywin32` in the Windows guest.
- If Visio reports file not found, verify the mapped `\\Mac\Home\...` path in
  the guest.

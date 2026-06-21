# Visio Bridge — 示例文档

[English](examples.md) | [← 返回 README](../README_CN.md)

---

## 目录

- [示例 1：使用 `visio-file-inspector` 只读诊断文件结构](#示例-1使用-visio-file-inspector-只读诊断文件结构)
- [示例 2：使用 `visio-symbol-editor` 编辑元器件符号](#示例-2使用-visio-symbol-editor-编辑元器件符号)
- [示例 2b：重算页面实例的公式缓存](#示例-2b重算页面实例的公式缓存)
- [示例 3：使用 `visio-doc-page-settings` 编辑文档与页面配置](#示例-3使用-visio-doc-page-settings-编辑文档与页面配置)
- [示例 3b：显式使用 Visio 桌面端后端](#示例-3b显式使用-visio-桌面端后端)
- [示例 3c：XML 保存后刷新已打开的 Visio 文档](#示例-3cxml-保存后刷新已打开的-visio-文档)
- [示例 4：使用 `design` 框架审计统一风格电路图](#示例-4使用-design-框架审计统一风格电路图)
- [示例 5：使用 `visio-instance-manager` 管理形状实例](#示例-5使用-visio-instance-manager-管理形状实例)

---

## 示例 1：使用 `visio-file-inspector` 只读诊断文件结构

使用资源清单和定位引擎探索任意 Visio 文件的内部结构，不会修改文件。

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from visio_bridge import VisioBridge, ElementLocator
import xml.etree.ElementTree as ET

bridge = VisioBridge("circuit.vstx")
locator = ElementLocator(bridge)

# 1. 打印整包资源清单地图
print(bridge.parts_manifest())

# 2. 定位并读取核心自定义元数据
custom_props = locator.find("doc_props/custom")
if custom_props is not None:
    for prop in custom_props:
        print("属性名:", prop.get("name"), "值:", prop[0].text)
```

---

## 示例 2：使用 `visio-symbol-editor` 编辑元器件符号

将形状数据提取为 AI 可读格式，并应用结构化修改命令。

```python
from visio_bridge import VisioBridge, ElementLocator, to_skill, apply_skill_commands

bridge = VisioBridge("circuit.vstx")
locator = ElementLocator(bridge)
shape_path = "masters/NMOS4/shape/5"
shape_element = locator.find(shape_path)

# 转换为 AI 易读的元器件数据
skill_data = to_skill(shape_element)

# 使用显式配置的后端执行修改。
commands = [
    {"action": "update_transform", "property": "Width", "formula": "0.75 in"},
    {"action": "add_connection_pin", "id": "99", "x": "Width*0.5", "y": "Height*0.2", "dir_x": "0", "dir_y": "-1"}
]
apply_skill_commands(bridge, shape_path, commands, backend="desktop")
bridge.save("circuit_modified.vstx")
```

---

## 示例 2b：重算页面实例的公式缓存

演示实例级公式重算与继承缓存同步。

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

# 默认会为当前 instance subtree 中受 Width override 影响的继承公式写入 F="Inh" cache，
# 例如 LocPinX、Connection.X、子形状 BeginX/PinX/Width 等 effective cache。
bridge.save("circuit_instance_width_modified.vsdx")
```

---

## 示例 3：使用 `visio-doc-page-settings` 编辑文档与页面配置

提取并修改全局文档变量和页面级属性。

```python
from visio_bridge import VisioBridge, to_settings_skill, apply_settings_commands

bridge = VisioBridge("circuit.vstx")

# 提取当前文档和页面设置
settings = to_settings_skill(bridge)
print("全局及页面设置：", settings)

# 使用显式配置的后端执行配置命令。
commands = [
    {"action": "update_doc_user_cell", "name": "AntiGravityScale", "value": "1.5", "unit": "IN"},
    {"action": "update_page_cell", "page": "Page-1", "property": "PageWidth", "formula": "12 in"}
]
apply_settings_commands(bridge, commands, backend="desktop")
bridge.save("circuit_settings_modified.vstx")
```

---

## 示例 3b：显式使用 Visio 桌面端后端

阶段二入口必须显式传入与 `.visio_bridge.json` 匹配的 backend。

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

# 如需使用 XML ZIP 后端，.visio_bridge.json 也必须设置 "backend": "xml"：
apply_settings_commands(
    modified,
    [{"action": "update_doc_user_cell", "name": "M", "value": "1"}],
    backend="xml",
)
```

---

## 示例 3c：XML 保存后刷新已打开的 Visio 文档

如果通过 XML 后端修改文件，而同一个文件已经在 Visio 桌面端打开，保存后需要显式刷新 Visio 窗口。

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
    # 默认行为会丢弃 Visio UI 中未保存的编辑，然后关闭并重新打开文档，
    # 使 Visio 显示磁盘上的最新文件内容。
    refresh_visio_file(path)
```

---

## 示例 4：使用 `design` 框架审计统一风格电路图

使用内置 Profile 运行只读设计审计，并规划建议修复命令。

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

# 1. 查看 Profile 的完整规则说明：不依赖具体文件
print(render_design_profile_markdown(CIRCUIT_SCHEMATIC_PROFILE))

# 2. 只读审计：不会修改文件
report = audit_design(bridge, CIRCUIT_SCHEMATIC_PROFILE)
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

# 3. 规划可选修复命令：按前两阶段执行器分组
command_groups = plan_design_commands(report)
print(json.dumps(command_groups, indent=2, ensure_ascii=False))
```

---

## 示例 5：使用 `visio-instance-manager` 管理形状实例

在页面或组容器中添加、复制和删除形状实例。

```python
from visio_bridge import VisioBridge, apply_instance_commands

bridge = VisioBridge("circuit.vsdx")

commands = [
    # 在 Page-1 上添加一个 "Cap" master 的新实例
    {
        "action": "add_instance",
        "parent": "pages/Page-1",
        "master": "Cap",
        "x": "2.0 in",
        "y": "3.0 in",
        "width": "0.5 in",
        "height": "0.5 in",
    },
    # 将已有形状复制到新位置
    {
        "action": "copy_instance",
        "shape_path": "pages/Page-1/shape/168",
        "x": "4.0 in",
        "y": "3.0 in",
    },
    # 删除一个形状实例
    {
        "action": "delete_instance",
        "shape_path": "pages/Page-1/shape/200",
    },
]

results = apply_instance_commands(bridge, commands, backend="desktop")
print("结果:", results)
bridge.save("circuit_instances_modified.vsdx")
```

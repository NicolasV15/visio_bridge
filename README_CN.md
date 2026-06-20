# Visio Bridge

**一个用于解析、定位、提取与修改现代 Visio 文件（`.vsdx` / `.vstx` / `.vssx`）的 Python 工具库 —— 专为 AI Agent 自动化、元器件配置与只读诊断分析而设计。**

[English](README.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Dependencies](https://img.shields.io/badge/dependencies-zero_(stdlib_only)-brightgreen)

---

## ✨ 功能亮点

- **多格式支持** —— 开箱即用地读写 `.vsdx`（绘图）、`.vstx`（模板）和 `.vssx`（模具库）文件。
- **零依赖** —— 纯 Python 标准库实现，核心功能无需任何第三方包。
- **OPC 关系映射** —— 自动沿 OPC 关系链解析 Master、Page、Theme、Windows 和 DocProps。`parts_manifest()` 提供完整拓扑地图，无需手动解析。
- **统一定位引擎** —— `ElementLocator.find(path)` 支持精准和模糊的多级路径导航，覆盖 Master、Page、文档设置、主题、窗口与元数据。
- **AI 原生 SKILL 接口** —— 五组结构化 SKILL 模块让 AI Agent 通过 JSON 命令列表读取、编辑和管理 Visio 文件，无需接触原始 XML。
- **公式缓存引擎** —— 自动 ShapeSheet 公式重算，支持 master/instance 作用域、继承链解析与 Visio 兼容的 `F="Inh"` 缓存同步。
- **双后端架构** —— 通过 XML ZIP（跨平台）或 Visio 桌面端 COM API（Windows / macOS Parallels）写入，支持自动回退。
- **设计规则框架** —— 可插拔的审计 Profile（`DesignProfile`），用于自动化风格合规检查、违规报告与建议修复规划。

---


## 📦 安装

### 从源码安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/NicolasV15/visio_bridge.git

# 从父目录以可编辑模式安装
pip install -e ./visio_bridge
```

> **注意**：核心库**零第三方依赖**——仅使用 Python 标准库模块。

### 可选：Visio 桌面端 COM 后端

用于 Visio 桌面端 COM 自动化（Windows / macOS Parallels）：

```bash
pip install -e "./visio_bridge[desktop]"
```

此选项会安装 `pywin32` 以支持 COM 互操作。修改入口（`apply_skill_commands`、`apply_settings_commands`、`apply_instance_commands`）默认 `backend="auto"`，优先使用 Visio 桌面端 COM，COM 不可用时自动回退到 XML ZIP 写入。使用 `backend="xml"` 强制走 XML 路径，使用 `backend="desktop"` 强制 COM 且不允许回退。

**Windows 前置条件：**
- 安装 Python 3.12，并确保当前登录用户的 `PATH` 中 `python` 可用
- 安装 `pywin32`：`python -m pip install pywin32`
- 已安装并可启动 Visio 桌面版，`Visio.Application` COM ProgID 可用

**macOS（Parallels）前置条件：**
- 安装 [Parallels Desktop](https://www.parallels.com/) 并配置 Windows VM
- 在 Windows VM 中安装 Python 3.12 和 `pywin32`
- 在 Windows VM 中安装 Visio 桌面版
- *注意：若未在 `.visio_bridge.json` 中指定虚拟机名称，传输通道会在运行时动态探测并连接至当前运行中或已注册的虚拟机。*

**Linux 前置条件：**
- 安装 Python 3.10+
- 自动默认使用 `backend="xml"`（无需安装/配置 Microsoft Visio 桌面版）。

### 配置虚拟机与后端首选项

您可以通过运行配置设置实用程序来定制默认的虚拟机名称、首选后端和自动化窗口的可见性设置：

```bash
# 运行设置工具
visio-bridge-setup

# 或者直接运行 Python 模块
python -m visio_bridge.src.core.setup_cli
```

这将在当前工作目录下生成一个本地 `.visio_bridge.json` 配置文件，用于动态存储虚拟机名称和后端重写配置。
- Parallels 模式默认启用 `stage_local`——文件在编辑前被暂存到 `%TEMP%`, 避免 UNC 路径和中文目录引发的不稳定性。

## 🔄 双后端架构

Visio Bridge 采用混合双后端架构，以平衡跨平台修改的高效性与完整应用程序的保真度。

### 1. 直接 XML ZIP 后端 (`xml`)
使用标准库直接解压、解析、修改并重新打包 Open XML 格式的 Visio 文件（`.vsdx`/`.vstx`/`.vssx`）。
* **优点**：
  - **跨平台**：原生运行于 macOS、Linux 和 Windows。
  - **极速修改**：毫秒级执行，非常适合大规模批量操作。
  - **零外部依赖**：仅依赖 Python 标准库（无需安装 Microsoft Visio）。
  - **极其稳定**：没有 GUI 副作用，不会被隐藏的弹窗对话框阻塞，没有授权过期等问题。
* **缺点**：
  - 无法原生自动计算复杂的类似 Excel 的单元格公式或几何关联（修改后的公式虽已写入，但其 dependent 单元格的*缓存值*在 Visio 重新打开文件前不会被更新，除非使用 explicit 的 `recalculate_formula_cache` 缓存计算工具）。
  - 无法直接生成 PDF 或渲染导出形状的预览图。

### 2. Visio 桌面端 COM 后端 (`desktop`)
通过 `pywin32` COM API 控制一个实际在后台（或前台）运行的 Microsoft Visio 进程。在 macOS 下，会通过命令行通道（`prlctl`）控制 Parallels Desktop 的 Windows 虚拟机来完成。
* **优点**：
  - **100% 原生保真**：由 Visio 引擎亲自计算所有的复杂单元格公式、形状联动、模板规则和几何变换。
  - **渲染导出支持**：支持生成形状或页面的预览图，支持导出 PDF。
* **缺点**：
  - **平台限制**：必须是 Windows 宿主机，或 macOS + Parallels Desktop 虚拟机环境。
  - **前置依赖**：必须安装并激活正版的 Microsoft Visio 桌面端。
  - **性能开销较大**：每次运行通常耗时 1 到 3 秒（需要启动/连接 Visio 进程并打开文档）。
  - **交互阻塞风险**：如果 Visio 触发了意外的模态弹窗或激活向导，可能会导致自动化死锁挂起。

### 默认策略与推荐建议
* **默认策略**：默认行为是 `backend="auto"`。
  - 在 Windows 上，若检测到 `pywin32` 和 Visio，会自动选择 `desktop`，否则回退到 `xml`。
  - 在 macOS 上，若检测到 `prlctl` 命令且虚拟机处于运行状态，会自动通过 Parallels 使用 `desktop`，否则回退到 `xml`。
  - 在 Linux 或其他平台上，默认回退使用 `xml`。
* **推荐建议**：为确保公式重新计算与布局引擎的完全原生高保真，**推荐默认使用 `backend="auto"`（或显式指定 `backend="desktop"`）**。只有在必须跨平台部署（如 Linux 环境）且公式缓存更新被独立处理的情况下，再考虑使用 `backend="xml"` 后端。

### 🤖 AI Agent 接入与指南

Visio Bridge 从设计之初就充分考虑了 AI 自动化的需求。我们提供了两个层级的 Agent 引导文档：

#### 1. 仓库级 Agent 指南 ([`AGENTS.md`](AGENTS.md))
如果您正使用 AI 编码助手（如 **Cursor**、**Claude Code** 或 **Gemini CLI**）在当前仓库中进行代码编写或工具开发，**请把 [`AGENTS.md`](AGENTS.md) 喂给您的 AI 助手**。它会指导助手：
* 了解整个仓库的目录结构。
* 如何使用 `to_skill()` 读取与 `apply_*` 执行的闭环工作流。
* 如何选择合适的后端与读取本地 `.visio_bridge.json` 配置。
* 进行 Visio 安全修改的绝对规则（如“先读后写”、“禁止直接操作原始 XML”等）。

#### 2. 模块级 Prompt (`SKILL.md`)
如果您在程序中直接调用 LLM，让其自动化修改形状或页面，每个 SKILL 模块下都提供了专用的 Prompt 模板（`SKILL.md`）定义角色、输入结构和输出 Schema：

| Agent 角色 | 系统提示 | 执行函数 |
|---|---|---|
| 形状几何编辑器 | [`skills/symbol_editor/SKILL.md`](skills/symbol_editor/SKILL.md) | `apply_skill_commands()` |
| 文档与页面设置 | [`skills/doc_page_settings/SKILL.md`](skills/doc_page_settings/SKILL.md) | `apply_settings_commands()` |
| 只读文件诊断器 | [`skills/file_inspector/SKILL.md`](skills/file_inspector/SKILL.md) | *（只读，无需 apply）* |
| 形状实例管理器 | [`skills/instance_manager/SKILL.md`](skills/instance_manager/SKILL.md) | `apply_instance_commands()` |
| 设计规则审计员 | [`skills/design_rules/SKILL.md`](skills/design_rules/SKILL.md) | `plan_design_commands()` |

---

## 🔧 核心能力

### 能力一：基础架构与多格式适配（Core）

| 能力 | 说明 |
|---|---|
| **多格式 ZIP 读写** | 直接解析并重写 `.vsdx`、`.vstx` 和 `.vssx` 文件 |
| **关系映射** | 沿 OPC 关系链动态关联 Master、Page、Theme、Windows 和 DocProps 到底层 XML 路径。`bridge.parts_manifest()` 零解析直接获取全部拓扑 |
| **定位引擎** | `ElementLocator.find(path)` 支持精准和模糊的多级导航 |

支持的定位路径格式：

| 路径 | 目标 |
|---|---|
| `masters/<NameU_or_ID>/shape/<ID>` | Master 形状元素 |
| `document` / `document/sheet` | 文档根 / DocumentSheet |
| `pages/<NameU_or_ID>/shape/<ID>` | 页面形状元素 |
| `theme/0` | DrawingML 主题根 |
| `windows` | 窗口状态 |
| `doc_props/core\|app\|custom` | OPC 文档属性 |

---

### 能力二：SKILL 双向封装与扩展（Processing & SKILL Interface）

四组结构化 SKILL 模块提供完整的 AI Agent 读写能力：

#### 1. 符号编辑器（`symbol_editor`）

操纵元器件几何、连接引脚与形状属性：

| 动作指令 | 说明 |
|---|---|
| `update_transform` | 更新外框属性（Width、Height 等）的值或计算公式 |
| `recalculate_formula_cache` | 对单个 master 或 page instance 执行公式缓存重算 |
| `add_connection_pin` | 添加连接引脚，支持 X/Y 坐标与方向向量 |
| `delete_connection_pin` | 按 ID 删除连接引脚 |
| `draw_rectangle` | 绘制并填充矩形几何路径 |
| `draw_line` | 绘制直线几何路径 |
| `draw_circle` | 绘制并填充自适应圆形，支持圆心坐标与半径的公式关联 |
| `draw_ellipse` | 基于外接矩形边界框绘制并填充封闭椭圆 |
| `draw_elliptical_arc` | 绘制椭圆弧，支持任意起始角度和扫描角度 |
| `modify_geometry` | 动态修改已有几何路径的顶点坐标 |
| `update_text` | 更新形状内部文本内容 |
| `update_shape_user_cell` | 修改或新增形状级自定义局部变量 |
| `delete_shape_user_cell` | 删除指定的形状级自定义变量 |

**公式缓存重算默认行为：**
- 写 master shape 时，默认重算所属 master 及其 Master PageSheet。
- 写 page instance 时，默认重算当前 instance subtree，不修改 master 或页面其它 shape。
- instance 本地 override 优先于 master 定义；继承公式在 instance effective context 中求值。
- 受 override 影响的继承公式默认写为 Visio-style cache：`F="Inh"` + computed `V` + inherited `U`。
- dirty scope 在 `bridge.save()` 前自动 flush。

#### 2. 文档与页面设置（`doc_page_settings`）

提取与修改 Visio 全局配置和页面参数：

| 动作指令 | 说明 |
|---|---|
| `update_doc_user_cell` | 更新或创建全局 DocumentSheet 的 User 属性单元格（如全局尺寸比例 `M`） |
| `delete_doc_user_cell` | 从 DocumentSheet 中物理删除指定的全局自定义变量 |
| `update_page_cell` | 更新指定 PageSheet 页面属性（如 PageWidth、PageHeight、PageScale 等） |
| `update_page_user_cell` | 更新或创建页面级自定义局部变量 |
| `delete_page_user_cell` | 从 PageSheet 中物理删除指定的页面级自定义变量 |

#### 3. 实例管理器（`instance_manager`）

在结构/页面层级管理形状实例：

| 动作指令 | 说明 |
|---|---|
| `add_instance` | 在页面或组容器中创建新的 Master 形状实例 |
| `copy_instance` | 将已有形状实例克隆到新位置 |
| `delete_instance` | 删除形状实例及其所有后代元素 |

#### 4. 文件诊断器（`file_inspector`）

只读深度检查任意 Visio XML 结构：

| 策略 | 目标 | 说明 |
|---|---|---|
| **A**（Visio Masters） | `masters/<Name>/shape/<ID>` | 提取几何、引脚、变换、文本与公式 |
| **B**（Pages & Document） | `pages/<Name>`、`document/sheet` | 提取页面尺寸、全局公式（User.Scale 等） |
| **C**（DrawingML Theme） | `theme/0` | 读取主题调色板与 Accent 颜色配置 |
| **D**（Windows State） | `windows` | 查看窗口排列、缩放级别与活跃工作区 |
| **E**（OPC Doc Properties） | `doc_props/core\|app\|custom` | 提取 Dublin Core 元数据、应用属性与自定义属性 |

---

### 能力三：通用设计规则与自动化设计框架（Design Rules）

| 能力 | 说明 |
|---|---|
| **通用设计 Profile** | 通过 `DesignProfile` / `DesignRule` 表达设计风格或模板约束。不限于电路图——统计图、流程图、版式模板都可以作为新 Profile 接入 |
| **只读审计** | `audit_design()` 使用阶段一和阶段二能力读取 Visio 文件并输出结构化 `DesignReport` |
| **建议修复规划** | `plan_design_commands()` 将可修复建议按执行器分组，不默认修改文件 |
| **自动生成 Profile 文档** | `describe_design_profile()` 与 `render_design_profile_markdown()` 基于 Profile 的结构化 `spec` 输出完整规则说明 |
| **能力适配层** | `DesignCapabilityRegistry` 统一登记读取器与命令适配器。阶段一和阶段二新增的读写能力可以继续注册进阶段三，不需要重写规则引擎 |

**内置统一风格电路图 Profile**（`CIRCUIT_SCHEMATIC_PROFILE`）：
- **元器件规则**：顶层 Master 结构、中心锚点、尺寸公式、网格单位、引脚位置、引脚方向、可缩放几何
- **连线风格规则**：共享连接器 Master、线宽、连接器实例使用方式、网格与方向习惯
- **文档/页面规则**：推荐 `User.Scale`、`User.M`、`User.LW`，页面尺寸保持自由

---

## 📖 API 参考

### 核心类

| 类 / 函数 | 导入方式 | 说明 |
|---|---|---|
| `VisioBridge` | `from visio_bridge import VisioBridge` | 核心主类，负责 ZIP I/O、XML 缓存与关系解析 |
| `ElementLocator` | `from visio_bridge import ElementLocator` | 基于路径的统一元素导航 |
| `FormulaCacheResult` | `from visio_bridge import FormulaCacheResult` | 公式重算结果容器 |
| `recalculate_formula_cache` | `from visio_bridge import recalculate_formula_cache` | 底层公式重算 API |

### SKILL 函数

| 函数 | 导入方式 | 说明 |
|---|---|---|
| `to_skill(shape)` | `from visio_bridge import to_skill` | 将形状元素转换为 AI 可读的 JSON 格式 |
| `apply_skill_commands(bridge, path, cmds)` | `from visio_bridge import apply_skill_commands` | 执行符号编辑器命令 |
| `to_settings_skill(bridge)` | `from visio_bridge import to_settings_skill` | 提取文档与页面设置为结构化 JSON |
| `apply_settings_commands(bridge, cmds)` | `from visio_bridge import apply_settings_commands` | 执行文档/页面设置命令 |
| `apply_instance_commands(bridge, cmds)` | `from visio_bridge import apply_instance_commands` | 执行实例管理命令（添加/复制/删除） |

### 桌面端后端

| 类 / 函数 | 导入方式 | 说明 |
|---|---|---|
| `VisioDesktopSession` | `from visio_bridge import VisioDesktopSession` | Visio COM 自动化会话管理器 |
| `ParallelsTransport` | `from visio_bridge import ParallelsTransport` | macOS → Windows VM 传输层（Parallels） |
| `LocalWindowsTransport` | `from visio_bridge import LocalWindowsTransport` | 原生 Windows 传输层 |
| `create_default_transport()` | `from visio_bridge import create_default_transport` | 自动检测并创建合适的传输层 |

### 设计框架

| 类 / 函数 | 导入方式 | 说明 |
|---|---|---|
| `audit_design(bridge, profile)` | `from visio_bridge import audit_design` | 运行只读设计审计 |
| `plan_design_commands(report)` | `from visio_bridge import plan_design_commands` | 按执行器分组规划修复命令 |
| `render_design_profile_markdown(profile)` | `from visio_bridge import render_design_profile_markdown` | 将 Profile 生成 Markdown 文档 |
| `CIRCUIT_SCHEMATIC_PROFILE` | `from visio_bridge import CIRCUIT_SCHEMATIC_PROFILE` | 内置统一风格电路图 Profile |

---

## 🗺️ 路线图

### 阶段四：人机协同开发协议（后续规划）

确立人类开发者通过高层语义进行 Prompt 约束，AI Agent 仅需理解并输出 SKILL JSON 列表进行交付的协议。

---

## ❓ 常见问题

<details>
<summary><strong>为什么用 XML 而不是 Visio COM API？</strong></summary>

Visio Bridge 的核心基于直接 XML 解析，原因如下：
1. **跨平台** —— 在 macOS 和 Linux 上无需安装 Visio 即可工作
2. **确定性** —— 没有 UI 副作用、隐藏对话框或竞态条件
3. **AI 友好** —— 结构化的 XML 访问更易于 AI Agent 推理
4. **轻量级** —— 零依赖；无 COM 互操作开销

当需要更高保真度（如公式求值或渲染）时，可选的桌面端后端提供 COM 自动化，并支持自动回退到 XML。
</details>

<details>
<summary><strong>支持哪些 Visio 文件格式？</strong></summary>

Visio Bridge 支持所有现代 Open XML 格式的 Visio 文件：
- **`.vsdx`** —— Visio 绘图文件（可编辑文档）
- **`.vstx`** —— Visio 模板文件（可复用模板）
- **`.vssx`** —— Visio 模具文件（形状库）

不支持旧版二进制格式（`.vsd`、`.vst`、`.vss`）。
</details>

<details>
<summary><strong>在 macOS 上如何使用 Visio 桌面端后端？</strong></summary>

1. 安装 [Parallels Desktop](https://www.parallels.com/) 并配置 Windows 虚拟机
2. 在 Windows VM 中安装 Python 3.12 和 `pywin32`
3. 在 Windows VM 中安装 Visio 桌面版
4. 使用 `backend="auto"`（默认值）—— Visio Bridge 会自动检测 `prlctl` 并通过 Parallels 路由命令

```python
# macOS：自动使用 Parallels → Windows → Visio COM
apply_skill_commands(bridge, path, commands)  # backend="auto" 是默认值
```
</details>

<details>
<summary><strong>如何添加自定义 Design Profile？</strong></summary>

使用 `DesignProfile` 和 `DesignRule` 数据模型创建新 Profile：

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
            # ... 定义检查函数和修复建议
        ),
    ],
)

# 使用自定义 Profile 运行审计
report = audit_design(bridge, my_profile)
```

通过 `DesignCapabilityRegistry` 注册新的读写能力，以扩展规则可检查和修复的范围。
</details>

---

## 📚 示例

详细代码示例请查看：

- 📖 [Examples (English)](docs/examples.md)
- 📖 [示例文档 (中文)](docs/examples_cn.md)

---

## 📄 许可证

本项目基于 [MIT 许可证](LICENSE) 发布。

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

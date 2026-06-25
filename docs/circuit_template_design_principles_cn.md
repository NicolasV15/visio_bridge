# 电路模板设计原则总结

本文总结 `circuit 模板开发/circuit_0625_v22.vstx` 当前结果，以及近期对话中逐步形成的电路模板修改原则。本文只描述现状和设计约束，不修改 Visio 模板文件。

## 依据与当前状态

- 检查文件：`circuit 模板开发/circuit_0625_v22.vstx`
- 只读检查方式：`VisioBridge.parts_manifest()`、`to_settings_skill()`、`to_skill()`、`audit_design(..., CIRCUIT_SCHEMATIC_PROFILE)`
- 当前结构：35 个 Master，3 个页面：`Basic`、`CMOS`、`Tobeoptimized`
- 当前文档变量：
  - `TheDoc!User.Scale = 1`
  - `TheDoc!User.M = GUARD(3MM*User.Scale)`
  - `TheDoc!User.LW = 0.00984251968503937 mm`
  - `TheDoc!User.msvNoAutoConnect = 1`
- 当前完成库 Master 数：20 个

## 总体设计原则

这个模板的核心原则是：把电路符号做成可缩放、可审计、可批量修改的结构化 Symbol，而不是只追求视觉上相似的静态图形。

1. 尺度统一：所有核心尺寸围绕 `TheDoc!User.M` 构造，`User.M` 由 `User.Scale` 派生。默认 `Scale=1` 时，`User.M` 表示 3 mm 的基础网格单位。
2. 线宽统一：标准线宽围绕 `TheDoc!User.LW` 构造。所有图形元素的线宽均使用公式动态控制。标准线宽直接使用 `TheDoc!User.LW`，不需要加任何后缀或写成 `*1.0`；较细的线段（如内部方向箭头、加减号等辅助线）则统一乘上 `0.8` 倍率（即 `TheDoc!User.LW*0.8`）。禁止使用硬编码的静态线宽值（例如 `0.01388 in` 或 `0.00694 in`）。
3. 公式优先：器件宽高、内部几何、连接点位置应尽量使用公式表达，避免固定绝对坐标。这样后续调整 `Scale` 时，符号可以整体跟随缩放。
4. 中心锚点：可复用元件的 `LocPinX` 和 `LocPinY` 使用 `Width*0.5`、`Height*0.5`，让放置、旋转和对齐稳定。
5. 相对引脚：连接点使用 `Width` / `Height` 相对坐标，并显式设置 `DirX` / `DirY` 为 `-1`、`0`、`1` 的方向向量。
6. 画布一致：Master PageSheet 的 `PageWidth` / `PageHeight` 应跟随顶层 symbol shape 的 `Width` / `Height`，避免拖入页面时出现符号边界和画布边界不一致。
7. 结构可编辑：复杂器件应避免无意义嵌套 group。需要组合/取消组合时，框架能力命名采用正式的 `group` / `ungroup`；desktop 后端对应 Visio 官方 COM 语义。
8. 原件安全：修改模板时不覆盖源文件，默认另存为新 `.vstx`，并在写入后回读验证。
9. 保护锁定：为了防止用户在 Visio UI 中拖拽变形导致网格对齐失效，所有电路器件（Dynamic connector 除外）的所有 Shape 级别元素均必须启用保护锁定属性：`LockWidth=1`、`LockHeight=1`、`LockAspect=1`、`LockCalcWH=1`。

## 器件修改原则

### 基础无源器件

`Res`、`Inductor`、`Inductor_2`、`Res_IEC` 当前体现了基础无源器件的主要规则：

- 使用竖向布局，而不是左右横向布局。
- 顶层尺寸统一为 `Width = TheDoc!User.M`、`Height = TheDoc!User.M*3`。
- 上下两个端口作为主连接点，连接点位于 `Height*0` 和 `Height`，方向分别指向外部连线进入符号的方向。
- 内部图形由子 shape 组成，但顶层 group 承担统一尺寸、锚点和连接点职责。

这个规则的作用是让电阻、电感和 IEC 电阻在页面上占用一致的竖向网格高度，便于自动布线、对齐和批量替换。

### 电源与节点类符号

`node` 当前已作为完成库成员，尺寸由线宽决定：

- `Width = TheDoc!User.M*0+TheDoc!User.LW*3`
- `Height = TheDoc!User.M*0+TheDoc!User.LW*3`
- 连接点位于中心。

这说明节点不应该随器件网格变大，而应该随标准线宽保持一个小而稳定的视觉点。

`VDD` 和 `GND` 当前存在于模板中，但审计仍提示标准电源符号定义未完全匹配，因此不纳入完成 Symbol 库。

### 电源与受控源符号

`DC-I`、`DC-V`、`CurrentSource` (电流源) 和 `Ctrl-VS` (CVS, 受控电压源) 当前已通过审计并入库：

- 外部引脚与尺度口径：`DC-I` 和 `DC-V` 顶层尺寸为 `TheDoc!User.M × TheDoc!User.M*3`；而 `CurrentSource` 和 `Ctrl-VS` 顶层尺寸为 `TheDoc!User.M*1 × TheDoc!User.M*2`（即宽 1M 高 2M，与 MOS 类器件口径一致）。
- 端口规划：全部采用上下两个连接点（顶部方向朝下，底部方向朝上），子 Shape 上不应出现多余连接点。
- 引脚对齐与防超限：`CurrentSource` 的上下外引线被移入 `Sheet.6` 符号内，其长度限制在 `0.15*Width`，底部与顶部引线精确落在圆的底/顶边缘切线上（切点位于 `Y = 0` 和 `Y = Height`），不得穿透进圆的内部。
- 线宽控制：主外边框或外线条的线宽绑定为 `TheDoc!User.LW`，而内部箭头（`CurrentSource` 的 `ID: 9`）以及加减号辅助线（`Ctrl-VS` 的 `ID: 13~16`）等偏细线条统一绑定为 `TheDoc!User.LW*0.8`，不得使用静态硬编码。
- 线端样式：`CurrentSource` 的内部方向箭头以及 `Ctrl-VS` 的所有元素线端样式统一设置 `LineCap = 0`。
- 加减号靠拢（`Ctrl-VS`）：内部的垂直加减号（主几何）与水平加减号（子 Shape）均向中心进行了紧凑的移动，使其与整体视觉比例协调。

电源与受控源符号的原则是：外部连接规格与主要引脚网格对齐，内部表达内容通过公式关联全局线宽与尺寸变量实现动态缩放。

### MOS 类器件

近期对话中形成的 MOS 规则包括：

- NMOS / PMOS 必须成对出现。
- MOS 类器件应去除不必要嵌套，作为可直接编辑的基本图形。
- 统一顶层比例：`Width = TheDoc!User.M*1`、`Height = TheDoc!User.M*2`。
- 左侧三条线表示栅极引脚、栅极和衬底绝缘区，其比例需要统一。
- 三端和四端版本需要在连接点语义上清晰区分，例如 G/D/S/B。

在 v14 当前文件中，MOS 相关 Master 已经体现了 `1M × 2M` 的尺寸、成对结构、相对连接点和去嵌套后的基本图形要求。虽然审计仍提示 `circuit.symbol.canvas_size`，但这 8 个 MOS 已经由人工确认可以入库；后续只需继续处理 Master 画布同步这类元数据收敛问题。

### 组合与取消组合

对话中已经明确：组合和取消组合能力不应作为临时 `flatten_group` 暴露，而应使用正式接口：

- `ungroup`：取消组合。
- `group`：组合多个 shape。

desktop backend 下，这两个动作应对应 Visio 官方对象模型语义；XML backend 只支持可安全复现的子集，复杂结构应报错而不是静默近似。

## 当前完成口径

本阶段“完整修改”的判定标准分两层：

- 严格审计通过：在 `CIRCUIT_SCHEMATIC_PROFILE` 下审计零违规，并且可以提取顶层 shape。
- 人工确认入库：8 个 MOS 管虽然仍有 `circuit.symbol.canvas_size` 提示，但器件本体已经满足当前 Symbol 库要求，可以入库。

按最新标准，当前可纳入 Symbol 库的 Master 有 20 个：

| 显示名 | NameU | Master ID | 主要用途 |
|---|---|---:|---|
| `Pin_1x` | `Pin.` | 31 | 单端管脚 |
| `Res` | `Res` | 10 | 竖向电阻 |
| `Inductor` | `Inductor` | 11 | 竖向电感 |
| `Inductor_2` | `L` | 40 | 第二种竖向电感 |
| `Res_IEC` | `Res_IEC` | 12 | IEC 电阻 |
| `DC-I` | `DC-I` | 35 | 直流电流源 |
| `DC-V` | `DC-V` | 16 | 直流电压源 |
| `CurrentSource` | `CurrentSource` | 13 | 优化后的双环电流源 |
| `Ctrl-VS` | `CVS` | 16 | 优化后的受控电压源 |
| `动态连接线` | `Dynamic connector` | 6 | 标准连接线 Master |
| `node` | `node` | 28 | 连接节点 |
| `Transformer` | `Transformer` | 63 | 变压器 |
| `NMOS` | `NMOS` | 46 | 三端 NMOS |
| `PMOS` | `PMOS` | 47 | 三端 PMOS |
| `NMOS_B` | `NMOS_B` | 48 | 带衬底端 NMOS |
| `PMOS_B` | `PMOS_B` | 52 | 带衬底端 PMOS |
| `NMOS4` | `NMOS4` | 18 | 四端 NMOS |
| `PMOS4` | `PMOS4` | 49 | 四端 PMOS |
| `Nmos_d` | `Nmos3.d` | 51 | 三端 NMOS 变体 |
| `Pmos_d` | `Pmos3.d` | 50 | 三端 PMOS 变体 |

不在这个列表中的 Master 不代表不可用，而是当前仍有审计提示或结构未完全符合本轮入库口径。

## 后续收敛方向

- 修正 `VDD` / `GND` 的标准电源符号定义。
- 继续同步 MOS 类 Master 的 PageSheet 画布，使其与顶层 symbol bounds 一致；这属于已入库 MOS 的后续元数据收敛项。
- 将 `Cap` 的宽度改为公式表达，避免固定数值触发 `scalable_size` 提示。
- 给 `AC`、`SW.on`、`SW.off`、`TG1`、`TG2`、`A-R`、`V-R` 等补足连接点和可缩放尺寸。
- 收敛页面导线实例，尽量使用共享 `Dynamic connector` Master，并让端点粘附到 shape connection points。

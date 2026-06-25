# Symbol 库说明：circuit_0625_v22

本文记录 `circuit 模板开发/circuit_0625_v22.vstx` 中已经可以纳入当前库的 Symbol。入库标准分为两类：一类是在 `CIRCUIT_SCHEMATIC_PROFILE` 下审计零违规并可通过 `to_skill()` 提取顶层 shape；另一类是人工确认可以入库的 8 个 MOS管。

## 库版本状态

- 模板文件：`circuit 模板开发/circuit_0625_v22.vstx`
- Master 总数：35
- 页面总数：3：`Basic`、`CMOS`、`Tobeoptimized`
- 当前完成库 Master 数：20
- 完成库判定：12 个 Symbol 为审计零违规；8 个 MOS 管为人工确认入库，仍可在后续同步 Master 画布元数据。

## 全局 Symbol 规范

| 规范项 | 要求 |
|---|---|
| 尺度变量 | 符号尺寸优先引用 `TheDoc!User.M`，当前 `User.M = GUARD(3MM*User.Scale)` |
| 线宽变量 | 标准线宽必须引用 `TheDoc!User.LW`，不得写成静态数值或 `*1.0` 后缀；辅助线条（如内部指示箭头、加减号等偏细线条）统一使用 `TheDoc!User.LW*0.8` |
| 锚点 | 可复用元件使用 `LocPinX=Width*0.5`、`LocPinY=Height*0.5` |
| 引脚 | 使用 `Width` / `Height` 相对坐标，显式设置 `DirX` / `DirY` |
| 画布 | Master PageSheet 应跟随顶层 symbol shape 的宽高 |
| 结构 | 避免无意义嵌套 group；组合/取消组合使用 `group` / `ungroup` 语义 |
| 锁定属性 | 所有器件（Dynamic connector 除外）的所有 Shape 级别元素均启用 `LockWidth=1`、`LockHeight=1`、`LockAspect=1`、`LockCalcWH=1` 保护锁定 |

## 已完成 Symbol 清单

| 显示名 | NameU | ID | 顶层路径 | 类型 | 尺寸公式 | 连接点 |
|---|---|---:|---|---|---|---:|
| `Pin_1x` | `Pin.` | 31 | `masters/Pin./shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*2/3` | 1 |
| `Res` | `Res` | 10 | `masters/Res/shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*3` | 2 |
| `Inductor` | `Inductor` | 11 | `masters/Inductor/shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*3` | 2 |
| `Inductor_2` | `L` | 40 | `masters/L/shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*3` | 2 |
| `Res_IEC` | `Res_IEC` | 12 | `masters/Res_IEC/shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*3` | 2 |
| `DC-I` | `DC-I` | 35 | `masters/DC-I/shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*3` | 2 |
| `DC-V` | `DC-V` | 16 | `masters/DC-V/shape/5` | Group | `TheDoc!User.M` × `TheDoc!User.M*3` | 2 |
| `CurrentSource` | `CurrentSource` | 13 | `masters/CurrentSource/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 2 |
| `Ctrl-VS` | `CVS` | 16 | `masters/CVS/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 2 |
| `动态连接线` | `Dynamic connector` | 6 | `masters/Dynamic connector/shape/5` | Shape | `GUARD(EndX-BeginX)` × `GUARD(EndY-BeginY)` | 0 |
| `node` | `node` | 28 | `masters/node/shape/5` | Shape | `TheDoc!User.M*0+TheDoc!User.LW*3` × `TheDoc!User.M*0+TheDoc!User.LW*3` | 1 |
| `Transformer` | `Transformer` | 63 | `masters/Transformer/shape/5` | Group | `TheDoc!User.M*3` × `TheDoc!User.M*3` | 4 |
| `NMOS` | `NMOS` | 46 | `masters/NMOS/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 3 |
| `PMOS` | `PMOS` | 47 | `masters/PMOS/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 3 |
| `NMOS_B` | `NMOS_B` | 48 | `masters/NMOS_B/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 4 |
| `PMOS_B` | `PMOS_B` | 52 | `masters/PMOS_B/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 4 |
| `NMOS4` | `NMOS4` | 18 | `masters/NMOS4/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 4 |
| `PMOS4` | `PMOS4` | 49 | `masters/PMOS4/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 4 |
| `Nmos_d` | `Nmos3.d` | 51 | `masters/Nmos3.d/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 3 |
| `Pmos_d` | `Pmos3.d` | 50 | `masters/Pmos3.d/shape/5` | Group | `TheDoc!User.M*1` × `TheDoc!User.M*2` | 3 |

## Symbol 详细说明

### Pin_1x

| 字段 | 值 |
|---|---|
| Master | `Pin_1x` / `Pin.` / ID `31` |
| 顶层路径 | `masters/Pin./shape/5` |
| 顶层 shape | ID `5`，名称 `pad.s`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*2/3` |
| 锚点 | `LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 2 个 |
| 连接点 | 1 个：`X=Width`，`Y=Height*0.5`，`DirX=-1`，`DirY=0` |

特殊要求：作为单端引脚，连接点放在右侧中点，方向向左，便于作为外部端子或模块端口拖入页面。

### Res

| 字段 | 值 |
|---|---|
| Master | `Res` / `Res` / ID `10` |
| 顶层路径 | `masters/Res/shape/5` |
| 顶层 shape | ID `5`，名称 `R`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 3 个 |
| 连接点 | 2 个：上端 `Y=Height*0, DirY=1`；下端 `Y=Height, DirY=-1` |

特殊要求：电阻采用竖向三倍网格高度，内部电阻图形作为子 shape，顶层 group 只负责标准尺寸、居中锚点和上下端口。

### Inductor

| 字段 | 值 |
|---|---|
| Master | `Inductor` / `Inductor` / ID `11` |
| 顶层路径 | `masters/Inductor/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 3 个 |
| 连接点 | 2 个：`Y=Height*0, DirY=1`；`Y=Height, DirY=-1` |

特殊要求：作为竖向电感，整体外部连接规则与 `Res` 一致。端口 prompt 当前仍保留 `Left terminal` / `Right terminal` 文案，但几何位置已经是上下端口。

### Inductor_2

| 字段 | 值 |
|---|---|
| Master | `Inductor_2` / `L` / ID `40` |
| 顶层路径 | `masters/L/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 3 个 |
| 连接点 | 2 个：`X=Width*0.5`，上端 `Y=0, DirY=1`；下端 `Y=Height, DirY=-1` |

特殊要求：这是第二套电感表达，保持与主 `Inductor` 一样的尺寸和端口口径，便于后续按视觉风格替换。

### Res_IEC

| 字段 | 值 |
|---|---|
| Master | `Res_IEC` / `Res_IEC` / ID `12` |
| 顶层路径 | `masters/Res_IEC/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 3 个 |
| 连接点 | 2 个：上端 `Y=Height*0, DirY=1`；下端 `Y=Height, DirY=-1` |

特殊要求：IEC 电阻保留独立 Master，但外部占位、端口和缩放规则与 `Res` 对齐。

### DC-I

| 字段 | 值 |
|---|---|
| Master | `DC-I` / `DC-I` / ID `35` |
| 顶层路径 | `masters/DC-I/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 4 个 |
| 连接点 | 2 个：`X=Width*0.5`，上端 `Y=0, DirY=1`；下端 `Y=Height, DirY=-1` |

特殊要求：内部带箭头线位于 `masters/DC-I/shape/8`，线宽为 `LineWeight=TheDoc!User.LW*0.8`，当前计算值 `0.007874015748031496 mm`。这是该符号区别于普通外框线的局部视觉规则。

### DC-V

| 字段 | 值 |
|---|---|
| Master | `DC-V` / `DC-V` / ID `16` |
| 顶层路径 | `masters/DC-V/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 6 个 |
| 连接点 | 2 个：`X=Width*0.5`，上端 `Y=0, DirY=1`；下端 `Y=Height, DirY=-1` |

特殊要求：电压源和电流源共享外部尺寸与端口规范，内部图形可以独立表达电压源语义。

### CurrentSource

| 字段 | 值 |
|---|---|
| Master | `CurrentSource` / `CurrentSource` / ID `13` |
| 顶层路径 | `masters/CurrentSource/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*2` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 1个直接子图形 (ID 6 符号组)，该子图形内含 5 个孙级图形（圆环、箭头与两端引线） |
| 连接点 | 2 个：上端 `Y=Height, DirY=-1`；下端 `Y=0, DirY=1` |

特殊要求：引线（ID 10、11）移入 `Sheet.6` 内部，长度限制在 `0.15*Width` 且精确与圆底/顶端切线对齐。内部箭头 `ID 9` 显式设置 `LineCap=0` 且线宽绑定为 `TheDoc!User.LW*0.8`。仅保留顶层 shape 上下 2 个主连接点。

### Ctrl-VS (受控电压源)

| 字段 | 值 |
|---|---|
| Master | `Ctrl-VS` / `CVS` / ID `16` |
| 顶层路径 | `masters/CVS/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M`，`Height=TheDoc!User.M*2` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 5 个直接子图形 (ID 6, 11, 12, 13, 14)，其中 ID 14 (加号) 内含 ID 15 和 16 |
| 连接点 | 2 个：上端 `Y=Height, DirY=-1`；下端 `Y=0, DirY=1` |

特殊要求：所有元素的线端样式均设置为 `LineCap=0`。所有线条宽度公式化控制：外边框及主引线线宽为 `TheDoc!User.LW`，加减号（ID 13~16）偏细线条线宽为 `TheDoc!User.LW*0.8`。加减号几何位置均向中心靠拢。

### Dynamic connector

| 字段 | 值 |
|---|---|
| Master | `动态连接线` / `Dynamic connector` / ID `6` |
| 顶层路径 | `masters/Dynamic connector/shape/5` |
| 顶层 shape | ID `5`，类型 `Shape` |
| 尺寸 | `Width=GUARD(EndX-BeginX)`，`Height=GUARD(EndY-BeginY)` |
| 锚点 | `PinX=GUARD((BeginX+EndX)/2)`，`PinY=GUARD((BeginY+EndY)/2)` |
| 本地锚点 | `LocPinX=GUARD(Width*0.5)`，`LocPinY=GUARD(Height*0.5)` |
| 几何 | 1 个 Geometry section |

特殊要求：这是页面导线应优先使用的共享连接器 Master。尺寸和位置使用 `GUARD(...)` 保护端点公式，避免普通编辑破坏连接器几何。

### node

| 字段 | 值 |
|---|---|
| Master | `node` / `node` / ID `28` |
| 顶层路径 | `masters/node/shape/5` |
| 顶层 shape | ID `5`，类型 `Shape` |
| 尺寸 | `Width=TheDoc!User.M*0+TheDoc!User.LW*3`，`Height=TheDoc!User.M*0+TheDoc!User.LW*3` |
| 锚点 | `LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 连接点 | 1 个：`X=Width*0.5`，`Y=Height*0.5`，`DirX=0`，`DirY=0` |
| 几何 | 1 个 Geometry section |

特殊要求：节点大小跟随线宽而不是网格尺寸，确保连接点在不同缩放下保持小而清晰。

### Transformer

| 字段 | 值 |
|---|---|
| Master | `Transformer` / `Transformer` / ID `63` |
| 顶层路径 | `masters/Transformer/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` |
| 尺寸 | `Width=TheDoc!User.M*3`，`Height=TheDoc!User.M*3` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` |
| 子形状 | 2 个 |
| 连接点 | 4 个：左上 `Width*(1/6),0`；左下 `Width*(1/6),Height`；右上 `Width*(5/6),0`；右下 `Width*(5/6),Height` |

特殊要求：变压器采用 `3M × 3M` 方形画布，四端口按 `1/6` 和 `5/6` 水平位置分布，上端 `DirY=1`，下端 `DirY=-1`，便于和上下方向导线连接。

### NMOS / PMOS 三端管

| 字段 | NMOS | PMOS |
|---|---|---|
| Master | `NMOS` / ID `46` | `PMOS` / ID `47` |
| 顶层路径 | `masters/NMOS/shape/5` | `masters/PMOS/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` | ID `5`，类型 `Group` |
| 尺寸 | `TheDoc!User.M*1` × `TheDoc!User.M*2` | `TheDoc!User.M*1` × `TheDoc!User.M*2` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` | 同 NMOS |
| 子形状 | 9 个 | 9 个 |
| 连接点 | S：`Width*1, Height*0, DirY=1`；D：`Width*1, Height*1, DirY=-1`；G：`Width*0, Height*0.5, DirX=1` | D：`Width*1, Height*0, DirY=1`；S：`Width*1, Height*1, DirY=-1`；G：`Width*0, Height*0.5, DirX=1` |

特殊要求：三端 MOS 统一为 `1M × 2M`，左侧中点为栅极 G，右侧上下为源漏端。NMOS 与 PMOS 的 S/D 上下语义相反，必须通过 prompt 保持区分。

### NMOS_B / PMOS_B 带衬底端管

| 字段 | NMOS_B | PMOS_B |
|---|---|---|
| Master | `NMOS_B` / ID `48` | `PMOS_B` / ID `52` |
| 顶层路径 | `masters/NMOS_B/shape/5` | `masters/PMOS_B/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` | ID `5`，类型 `Group` |
| 尺寸 | `TheDoc!User.M*1` × `TheDoc!User.M*2` | `TheDoc!User.M*1` × `TheDoc!User.M*2` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` | 同 NMOS_B |
| 子形状 | 11 个 | 10 个 |
| 连接点 | S、D、G、B 四端；B 位于 `Width*1, Height*0.5, DirX=-1` | D、S、G、B 四端；B 位于 `Width*1, Height*0.5, DirX=-1` |

特殊要求：带衬底端版本在右侧中点增加 B 端，方向向左。它们已经去除不必要嵌套，按基本图形入库。

### NMOS4 / PMOS4 四端管

| 字段 | NMOS4 | PMOS4 |
|---|---|---|
| Master | `NMOS4` / ID `18` | `PMOS4` / ID `49` |
| 顶层路径 | `masters/NMOS4/shape/5` | `masters/PMOS4/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` | ID `5`，类型 `Group` |
| 尺寸 | `TheDoc!User.M*1` × `TheDoc!User.M*2` | `TheDoc!User.M*1` × `TheDoc!User.M*2` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` | 同 NMOS4 |
| 子形状 | 10 个 | 10 个 |
| 连接点 | S、D、G、B 四端；G 在左侧中点，B 在右侧中点 | D、S、G、B 四端；G 在左侧中点，B 在右侧中点 |

特殊要求：四端 MOS 是正式四端口版本，端口语义必须保留 prompt；G/B 横向，S/D 竖向。

### Nmos_d / Pmos_d 三端变体

| 字段 | Nmos_d | Pmos_d |
|---|---|---|
| Master | `Nmos_d` / `Nmos3.d` / ID `51` | `Pmos_d` / `Pmos3.d` / ID `50` |
| 顶层路径 | `masters/Nmos3.d/shape/5` | `masters/Pmos3.d/shape/5` |
| 顶层 shape | ID `5`，类型 `Group` | ID `5`，类型 `Group` |
| 尺寸 | `TheDoc!User.M*1` × `TheDoc!User.M*2` | `TheDoc!User.M*1` × `TheDoc!User.M*2` |
| 锚点 | `PinX=Width*0.5`，`PinY=Height*0.5`，`LocPinX=Width*0.5`，`LocPinY=Height*0.5` | 同 Nmos_d |
| 子形状 | 7 个 | 8 个 |
| 连接点 | S、D、G 三端 | D、S、G 三端 |

特殊要求：这组是三端 MOS 变体，尺寸和连接点口径与 `NMOS` / `PMOS` 对齐。命名仍保留历史 `NameU`：`Nmos3.d` / `Pmos3.d`。

> 注意：上述 8 个 MOS 管已人工确认入库；当前审计仍会报告 `circuit.symbol.canvas_size`，这是后续同步 Master PageSheet 画布的元数据任务，不影响本轮 Symbol 库纳入。

## 待完成或未入库 Master

以下 Master 当前存在于 v14，但未达到本轮入库口径。它们可以继续使用或作为下一轮修改对象，但不应在本文档中宣称为已完成 Symbol 库成员。

| 显示名 | NameU | ID | 当前主要提示 |
|---|---|---:|---|
| `VDD` | `VDD` | 1 | `circuit.power_symbol.vdd` |
| `GND` | `GND` | 2 | `circuit.power_symbol.gnd` |
| `Pin_1.5x` | `pad.s` | 30 | `circuit.component.top_shape` |
| `I/O` | `I/O` | 43 | `circuit.component.top_shape` |
| `Cap` | `Cap` | 9 | `circuit.component.scalable_size` |
| `AC` | `AC` | 36 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |
| `SW.on` | `SW.on` | 32 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |
| `SW.off` | `SW.off` | 33 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |
| `TG1` | `TG1` | 57 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |
| `TG2` | `TG2` | 58 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |
| `pnp` | `pnp` | 55 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size` |
| `npn` | `npn` | 56 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size` |
| `A-R` | `A-R` | 59 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |
| `V-R` | `V-R` | 60 | `circuit.symbol.canvas_size`、`circuit.component.scalable_size`、`circuit.component.pins` |

## 维护要求

- 新增或修改 Symbol 后，先用 `to_skill()` 回读顶层 shape，再运行 `audit_design()`。
- 对同一 Master 的多个改动应批量提交到一次 `apply_skill_commands()`，避免中间状态污染。
- 修改源 `.vstx` 前必须另存新文件；确认无误后再考虑替换原模板。
- 如果某个 Symbol 只剩 `circuit.symbol.canvas_size`，优先检查 Master PageSheet 的 `PageWidth` / `PageHeight` 是否跟随顶层 shape。
- 页面导线应逐步收敛到共享 `Dynamic connector` Master，并让端点粘附到 connection points。

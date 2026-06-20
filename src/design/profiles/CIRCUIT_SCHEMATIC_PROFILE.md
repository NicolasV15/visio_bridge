# Circuit Schematic Style V1

<!-- AUTO-GENERATED FROM PROFILE; DO NOT EDIT BY HAND -->

Profile ID: `circuit_diagram.v1`

Generic circuit-diagram constraints for reusable components, connector style, and grid-aware document settings.

## Metadata
- `domain`: circuit_diagram
- `freedom`: geometry shape is flexible; scalability and connection conventions are audited

## Capability Dependencies
- `masters`
- `pages`
- `settings`
- `styles`

## Rule Overview
| Rule ID | Title | Category | Requirement | Severity | Capabilities |
|---|---|---|---|---|---|
| `circuit.document.required_user_cells` | Required circuit document variables | `document` | `recommended` | `warning` | `settings` |
| `circuit.document.autoconnect` | Disable Visio autoconnect | `document` | `recommended` | `warning` | `settings` |
| `circuit.page.grid_context` | Page grid context | `page` | `recommended` | `warning` | `pages`, `settings` |
| `circuit.power_symbol.vdd` | VDD standard power symbol | `power_symbol` | `recommended` | `warning` | `masters` |
| `circuit.power_symbol.gnd` | GND standard power symbol | `power_symbol` | `recommended` | `warning` | `masters` |
| `circuit.component.top_shape` | Component top shape | `component` | `recommended` | `warning` | `masters` |
| `circuit.symbol.canvas_size` | Symbol canvas size | `component` | `recommended` | `warning` | `masters` |
| `circuit.component.center_anchor` | Component center anchor | `component` | `recommended` | `warning` | `masters` |
| `circuit.component.scalable_size` | Component scalable size | `component` | `recommended` | `warning` | `masters` |
| `circuit.component.pins` | Component pin conventions | `component` | `recommended` | `warning` | `masters` |
| `circuit.component.scalable_geometry` | Component scalable geometry | `component` | `recommended` | `warning` | `masters` |
| `circuit.connector.style_sheet` | Standard wire style sheet | `connector` | `recommended` | `warning` | `styles` |
| `circuit.connector.dynamic_connector_style` | Dynamic connector style | `connector` | `recommended` | `warning` | `masters`, `styles` |
| `circuit.connector.master` | Shared connector master | `connector` | `recommended` | `warning` | `masters` |
| `circuit.connector.instances` | Connector instance usage | `connector` | `recommended` | `warning` | `pages` |

## Document Settings
### User.Scale
- `value`: `1`
- `requirement`: `recommended`
- `rule_id`: `circuit.document.required_user_cells`
### User.M
- `value`: `0.1181102362204724`
- `formula`: `GUARD(3MM*User.Scale)`
- `unit`: `MM`
- `requirement`: `recommended`
- `rule_id`: `circuit.document.required_user_cells`
### User.LW
- `value`: `0.01388888888888889`
- `unit`: `PT`
- `requirement`: `recommended`
- `rule_id`: `circuit.document.required_user_cells`
### User.msvNoAutoConnect
- `value`: `1`
- `requirement`: `recommended`
- `rule_id`: `circuit.document.autoconnect`

## Power Symbols
### VDD
- `master`: `VDD`
- `top_shape`: `shape/5`
- `type`: `Group`
- `transform`: {Width=`TheDoc!User.M`, Height=`TheDoc!User.M`, PinX=`Width*0.5`, PinY=`Height*0.5`, LocPinX=`Width*0.5`, LocPinY=`Height*0.5`}
- `shape_cells`: {LineWeight=`TheDoc!User.LW`, LineColor=`#000000`, FillPattern=`0`}
- `canvas`: {PageWidth=`Sheet.5!Width`, PageHeight=`Sheet.5!Height`, meaning=`Master PageSheet canvas follows this symbol's top shape Width/Height.`}
- `connection`: {X=`Width*0.5`, Y=`0`, DirX=`0`, DirY=`-1`, Prompt=`VDD terminal`}
- `rule_id`: `circuit.power_symbol.vdd`
### GND
- `master`: `GND`
- `top_shape`: `shape/5`
- `type`: `Group`
- `transform`: {Width=`TheDoc!User.M`, Height=`TheDoc!User.M`, PinX=`Width*0.5`, PinY=`Height*0.5`, LocPinX=`Width*0.5`, LocPinY=`Height*0.5`}
- `shape_cells`: {LineWeight=`TheDoc!User.LW`, LineColor=`#000000`, FillPattern=`0`}
- `canvas`: {PageWidth=`Sheet.5!Width`, PageHeight=`Sheet.5!Height`, meaning=`Master PageSheet canvas follows this symbol's top shape Width/Height.`}
- `connection`: {X=`Width*0.5`, Y=`Height`, DirX=`0`, DirY=`1`, Prompt=`GND terminal`}
- `rule_id`: `circuit.power_symbol.gnd`

## Generic Symbol Canvas Rules
### Master canvas matches symbol bounds
- `applies_to`: `all non-connector symbol masters`
- `page_width_formula`: `Sheet.<top_shape_id>!Width`
- `page_height_formula`: `Sheet.<top_shape_id>!Height`
- `cached_values`: `PageWidth/PageHeight cached values should match the top shape Width/Height values.`
- `rule_id`: `circuit.symbol.canvas_size`

## Wire Style
- `name`: `Circuit_Wire_Standard`
- `id`: `10`
- `cells`: {LineWeight={value=`0.01388888888888889`, unit=`PT`}, LineColor={value=`0`}, LinePattern={value=`1`}, Rounding={value=`0`}, BeginArrow={value=`0`}, EndArrow={value=`0`}, LineCap={value=`0`}}
- `rule_id`: `circuit.connector.style_sheet`

## Dynamic Connector
- `master`: `Dynamic connector`
- `top_shape`: `shape/5`
- `line_style`: `10`
- `line_style_name`: `Circuit_Wire_Standard`
- `endpoint_glue`: `BeginX/BeginY/EndX/EndY should use PAR(PNT(...Connections...)) where endpoints are attached.`
- `rule_id`: `circuit.connector.dynamic_connector_style`

## Generic Rule Notes
### Component top shape
- `rule_id`: `circuit.component.top_shape`
- `setting`: `Non-connector masters conventionally expose a reusable top shape, preferably shape/5.`
### Symbol canvas size
- `rule_id`: `circuit.symbol.canvas_size`
- `setting`: `Master PageSheet.PageWidth/PageHeight must follow the symbol top shape Width/Height.`
### Component center anchor
- `rule_id`: `circuit.component.center_anchor`
- `setting`: `LocPinX=Width*0.5 and LocPinY=Height*0.5.`
### Component scalable size
- `rule_id`: `circuit.component.scalable_size`
- `setting`: `Width/Height should preferably reference User.M or another scalable formula.`
### Component pin conventions
- `rule_id`: `circuit.component.pins`
- `setting`: `Pins should use Width/Height-relative coordinates and explicit -1/0/1 direction vectors.`
### Component scalable geometry
- `rule_id`: `circuit.component.scalable_geometry`
- `setting`: `Geometry should prefer Width/Height formulas over absolute numeric points.`
### Connector instances
- `rule_id`: `circuit.connector.instances`
- `setting`: `Page wires should use the shared Dynamic connector master and glue endpoints to connection points.`

## Fixable Rules
### Document user cells
- `rule_id`: `circuit.document.required_user_cells`
- `executor`: `doc_page_settings`
### Autoconnect user cell
- `rule_id`: `circuit.document.autoconnect`
- `executor`: `doc_page_settings`
### Standard power symbols
- `rule_id`: `circuit.power_symbol.vdd / circuit.power_symbol.gnd`
- `executor`: `symbol_editor`
### Component center anchor
- `rule_id`: `circuit.component.center_anchor`
- `executor`: `symbol_editor`

# 酒店报价、路线回退与时间轴配置

**日期**: 2026-05-22
**作者**: Codex + finn
**状态**: 待实施

## 背景

本轮反馈暴露了三个相互关联但归属不同的问题：

1. Result 页酒店卡片显示“价格待确认”，并缺少此前可用的酒店跳转链接。
2. 时间轴把近距离段落也强行按公交查询；当高德公交返回无 `transits` 的响应时，页面直接显示了原始响应对象文本。
3. 时间轴遗漏用户在草稿页新增的正餐，并把当天出发时间固定推算到常见的 `07:30`。

## 调查结论

### AIGoHotel

2026-05-22 的真实 MCP 调用验证了 AIGoHotel 仍能提供酒店报价和跳转链接：

- `searchHotels` 返回 `hotelId`、`bookingUrl`、`price.hasPrice`、`price.lowestPrice`、`price.currency`。
- `getHotelDetail` 返回 `bookingUrl` 与 `roomRatePlans`。

当前项目集成层仍按旧字段形态工作：

- 请求使用扁平 `checkIn` / `stayNights` / `starRatings` / `distanceInMeter`。
- 真实 MCP schema 需要 `checkInParam` 与 `filterOptions` 嵌套对象。
- 解析器只接受数字型 `price` 与 `detailUrl` / `url` / `link`，没有读取 `price.lowestPrice` 与 `bookingUrl`。

因此当前缺价和缺链接应优先修集成层，而不是先替换 AIGoHotel。

### 路线

`trip/4` 的近距离路线段中，公交 MCP 响应含 `distance` 但 `transits` 为空。当前解析器把无方案响应退化为原始字典字符串，因此页面上出现接口对象文本。

### 时间轴

`trip/4` 的定稿数据里同时保存了默认午餐与用户新增正餐：

- 默认午餐 `type=lunch`
- 用户新增正餐 `type=main`

Result 时间轴当前在前端按 `breakfast` / `lunch` / `dinner` 重建餐食位置，所以 `main` 类型餐食被漏掉。

## 目标

- 恢复 AIGoHotel 搜索结果中的最低价和酒店详情跳转链接。
- 为后续报价补全保留酒店 `hotelId`，必要时可对最终选中酒店调用详情工具。
- 路线规划按距离和实际可用方案选择更合适的交通方式，不把“公共交通”当成每一段不可回退的硬约束。
- 对无方案路线返回清晰的降级详情，不暴露原始 MCP 响应。
- Result 时间轴覆盖用户新增餐食。
- 支持一个全程默认出发时间，并允许草稿页按天覆盖。

## 非目标

- 不在本轮替换 AIGoHotel 供应商。
- 不做酒店下单或房型选择界面。
- 不把每段路线变成用户手动选择交通方式的完整编辑器。
- 不做分分钟排班系统；时间轴仍是行程展示与草稿轻编辑能力。

## 设计

### 1. AIGoHotel 集成修复

#### 请求层

`SearchHotels` 调用改为当前 MCP schema：

- `checkInParam.checkInDate`
- `checkInParam.stayNights`
- `checkInParam.adultCount`
- `filterOptions.starRatings`
- `filterOptions.distanceInMeter`

保留兼容逻辑时应集中在 AIGoHotel service 边界，不在调用节点散落两套参数拼装。

#### 解析层

酒店解析增加当前真实字段支持：

- `hotelId` -> `hotel_id`
- `bookingUrl` -> `detail_url`
- `price.lowestPrice` -> `price`，前提是 `price.hasPrice` 为真
- `price.currency` -> `currency`
- 继续兼容已有数字 `price` / `totalPrice` / `originalPrice`

价格对象返回“售罄”或无价时不伪造金额，继续让前端显示“价格待确认”或后续可扩展为更具体的状态文案。

#### 详情层

`GetHotelDetail` 保留为选中酒店报价补全入口，service 需要支持：

- `hotelId`
- `dateParam.checkInDate`
- `dateParam.checkOutDate`
- `occupancyParam`

本轮可先通过 SearchHotels 恢复最低价与链接；如果最终选中酒店仍无链接或需要房型价，再在详情补全阶段调用详情工具。

### 2. 多模式路线策略

路线计算以“用户交通偏好”为主策略，不把它当单段硬锁：

1. 对短距离段优先尝试步行。
2. 中等近距离可尝试步行或骑行。
3. 较远路段按用户偏好优先公交或驾车。
4. 首选工具无可用方案时按可解释顺序降级到其他模式。
5. 所有工具都失败时使用距离估算 fallback。

路线段输出必须始终是结构化 `RouteSegment`：

- `distance`
- `duration`
- `mode`
- 用户可读 `detail`

无公交方案时不再把 `{"origin": ..., "transits": []}` 这类响应写进 `detail`。

### 3. 时间轴与餐食

#### 用户新增餐食

Result 时间轴应使用已保存的 `day.timeline_order` 或等价的顺序来源来展示餐食，不再只硬编码识别早餐/午餐/晚餐。

兼容路径：

- 旧 TripPlan 没有 `timeline_order` 时，继续按当前规则生成可展示时间轴。
- 新草稿定稿后保留 `timeline_order` 到 Result 所需模型，用户新增 `main` / `snack` / `dessert` / `cafe` / `late_night` 餐食都能出现。

#### 出发时间

出发时间分两层：

- 全程默认出发时间：随 TripRequest 一起进入草稿。
- 单日覆盖：Draft 每一天可以覆盖 `day_start_time`。

优先级：

1. 当天覆盖时间
2. 全程默认时间
3. 系统默认时间

Result 时间轴按最终保存的当天有效开始时间渲染，不再依赖前端固定的 `8:00` 加 padding 产生起始时间。

### 4. 草稿体验

Draft 页在单日卡片上提供简洁的出发时间控件：

- 展示当前有效时间。
- 修改后走现有日级保存/重算路径。
- 不要求用户为每一段交通设模式。

## 数据模型

候选模型新增或透传：

- Hotel `hotel_id`
- TripRequest `default_day_start_time`
- DayDetail / DayPlan `day_start_time`
- DayPlan `timeline_order` 或前端需要的等价顺序数据

字段命名应在后端 schema 与前端 types 中保持一致。

## 错误处理

- AIGoHotel 搜索返回无价：酒店仍可展示，价格保持明确降级。
- AIGoHotel 详情补全失败：不阻断行程生成。
- 单段路线任一工具失败：尝试下一候选模式；最终 fallback 输出可读估算。
- 时间格式非法：后端拒绝或回退默认值，不把非法时间写入最终结果。

## 验证

- 后端测试覆盖：
  - AIGoHotel 当前字段形态的价格、链接、hotelId 解析。
  - SearchHotels 当前 schema 参数结构。
  - 无公交方案时路线会回退且不泄露原始响应。
  - 定稿保留时间轴顺序和单日开始时间。
- 前端验证覆盖：
  - Result 酒店卡片恢复价格与链接。
  - Result 时间轴显示用户新增正餐。
  - Draft 能设置单日出发时间。
  - 全程默认时间能影响未覆盖日。

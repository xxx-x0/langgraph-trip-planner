# 结果页：标签栏不再固定 + 景点补充开放时间/电话/门票

- 日期：2026-06-02
- 状态：设计已确认，待写实现计划
- 范围：结果页（`Result.vue` 及 `components/result/`、`AttractionCard.vue`）+ 后端景点数据串接

## 背景与问题

用户在最终结果页提出两个问题：

1. **标签栏一直跟随滚动**：四个标签（📋 行程概览 / 💰 预算明细 / 📍 景点地图 / 📅 每日行程）在下滑时钉在顶部，挤占视口、可见内容被压小。
2. **景点信息太少**：每个景点应给出基本信息，如开放时间、是否需门票/预约等。

## 高德数据可得性（关键前提，决定能做什么）

基于现有代码核实（非猜测）：

| 信息 | 可得性 | 证据 |
|---|---|---|
| 开放时间 | ✅ 可靠 | `maps_search_detail` 返回 `biz_ext.opentime_today/opentime_week`；餐饮节点已在用（`food.py:215`）。**景点聚类节点本来就已对每个景点调了 `maps_search_detail`（`cluster.py:57`），但只抠坐标、把开放时间丢弃了** |
| 电话 | ✅ 可靠 | 同一响应 `biz_ext.tel`（`food.py:218`），同样景点侧被丢弃 |
| 门票价格 | ⚠️ 不可靠 | 高德对景点无真正门票字段，现用 `biz_ext.cost`（人均）近似（`attractions_cache_service.py:155`），景点大多为空 |
| 是否需预约 | ❌ 无 | 高德无此字段，只能 LLM 推测/网搜，易瞎编 |

**结论**：开放时间 + 电话基本"免费"（数据已在抓、只是被丢）；门票时有时无；"需预约"高德给不了可靠数据，本次不做。

## 目标

- 标签栏改为**完全不固定**：跟内容一起滚走；切换标签时自动平滑回到顶部。
- 景点卡片补充 **开放时间 + 电话**，并保留现有**门票价格**展示；数据"有则显示、无则隐藏"，绝不编造。
- 数据随行程一起持久化（写入行程历史），而非仅前端临时拉取。

## 非目标

- 不做"是否需预约"（无可靠数据）。
- 不臆造门票价格（维持现状：>0 才显示）。
- 不改发现页 `SelectableAttractionCard`、不在时间轴展示开放时间、不做订票链接（数据备好，日后可加）。

## 设计

### 问题 1 —— 标签栏不固定

- **`Result.vue:560-567`**：删除 `.tab-bar` 的 `position: sticky;`、`top: 64px;`、`z-index: var(--z-sticky);` 三行，使其回到正常文档流随内容滚走。其余样式（背景、边框、padding、移动端 `overflow-x`）保持不变。
- **`Result.vue` `<script setup>`**：新增 `watch(activeTab, ...)`，切换标签时 `window.scrollTo({ top: 0, behavior: ... })` 回到顶部，保证切到新标签从头看；通过 `window.matchMedia('(prefers-reduced-motion: reduce)')` 决定 `behavior` 为 `'auto'` 还是 `'smooth'`。
- 现有 `a-back-top`（`Result.vue:138`）保留，作为长内容快速回顶。

### 问题 2 —— 景点补充 开放时间 / 电话 / 门票

#### 2a. 模型加字段

- 后端 `backend/app/models/schemas.py` 的 `Attraction`：
  - 新增 `open_hours: Optional[str] = Field(default=None, description="开放时间")`
  - 新增 `tel: Optional[str] = Field(default=None, description="联系电话")`
  - `ticket_price` 已存在，不动。
- 前端 `frontend/src/types/index.ts` 的 `Attraction`（第 8-18 行）：
  - 新增 `open_hours?: string`
  - 新增 `tel?: string`

#### 2b. 从高德收割（方案 A，零新增 API 调用）

- **`cluster.py` 主流程**（`maps_search_detail` 循环，约 `55-68` 行）：当前只用正则从详情响应里抠坐标。改为同时解析：
  - `biz_ext.opentime_today` 或 `biz_ext.opentime_week` → `open_hours`
  - `biz_ext.tel`（或顶层 `tel`）→ `tel`

  提取逻辑直接对齐 `food.py:201-220`。把这两个字段一并塞进 `valid_attractions` 里那个 `{name, longitude, latitude}` dict，使其随 `clusters_data` 向下游流动。
- **发现页流程 `attractions_cache_service.py`**：已在用 `_extract_biz_ext_value` 抠 `rating`/`cost`（`132-155` 行）。顺手补抠 `opentime_today/opentime_week` 与 `tel`，使发现页选中的景点也带上这两个字段。

#### 2c. 串到最终景点对象

- **主路径（确定性，当前结果页走的就是这条）**：`backend/app/agents/langgraph_agent/finalize/pipeline.py:85` `_build_day_context` 内构造 `Attraction(...)` 时补：
  - `open_hours=c.get("open_hours")`
  - `tel=c.get("tel")`

  之后经 `rule_assemble_day_timeline`（`assemble/timeline.py`）**原样穿过**（该函数只重排序、不重建景点对象）→ `DayDetail.attractions` → 最终 `DayPlan.attractions`。
- **保险（LLM 路径）**：`generate.py` 的单日生成在 `DayPlan(**data)`（约 `1089` 行）之后，新增一个**确定性回填**：按景点 `name`（必要时辅以 `poi_id`）从当日聚类/候选数据里把 `open_hours/tel` 合并回每个 `Attraction`，使得即便 LLM 在输出里丢掉这两个字段也能补回。归一化段（`1082-1087`）不动。
- **降级兜底构造点**（`generate.py:1340/1350`、`parsing.py:244/253`）：留空（`None`）。降级态本就拿不到详情数据，不强求。

#### 2d. 卡片展示（`frontend/src/components/AttractionCard.vue`，非编辑态）

- 位置：放在景点名（`attraction-name`）下方、地址（`attraction-address`）上方，新增两条紧凑信息行，**仅在字段有值时渲染整行**（无值时整行不出现，不留空行、不写"暂无"）：
  - 🕐 开放时间：`{{ attraction.open_hours }}`
  - 📞 电话：**移动端**渲染为 `<a :href="\`tel:${attraction.tel}\`">` 可点击拨打；**桌面端**渲染为普通文字（不做链接）。移动端判定用 `window.matchMedia('(pointer: coarse)')` 或等价手段。
- 现有展示保持：评分（★）、游览时长（⏱）、地址、描述、门票价格标签（`price-tag`，>0 才显示）、类别标签。
- 沿用现有 Bauhaus `meta-item` 风格，保证视觉一致。

### 诚实边界

- **覆盖率非 100%**：无 `poi_id`（走了 `maps_geo` 兜底）或高德本身无数据的景点，不会显示开放时间/电话 —— 不编造、不填占位。
- `open_hours` 原样展示高德返回的字符串（格式可能为 `"09:00-17:00"` 或 `"周一至周日 08:30-18:00"` 等），不二次解析。
- 门票价格维持现状（仅 `>0` 显示），不臆造。
- "是否需预约"不实现。

### B 扩展位（本次不实现，结构先留好）

2c 的回填以 `name + poi_id` 为键。若上线后发现覆盖率不足（较多景点无开放时间），再追加"定稿后针对**缺 `open_hours` 且有 `poi_id`** 的最终景点补调一次 `maps_search_detail`"的步骤，复用 `food.py` 中现成的 QPS 限流器 + 熔断器 + `poi_id` 缓存。本次设计保证该步骤可无重构地插入。

## 测试策略

- **后端单测**：
  - 构造带 `biz_ext.opentime_today` / `tel` 的聚类 dict，跑装配 → 断言最终 `Attraction.open_hours` / `tel` 有值（在现有 `assemble` / `pipeline` 测试附近扩展）。
  - LLM 路径：构造 LLM 输出丢失 open_hours/tel 的情形，断言按名回填后字段恢复。
  - 无详情数据的景点 → 断言 `open_hours is None`、`tel is None`（不编造）。
- **前端**：人工核对卡片在「有 / 无」开放时间、电话时分别正确显示与整行隐藏；移动端点击电话可拨号。

## 改动文件清单

后端：
- `backend/app/models/schemas.py`（Attraction 加 2 字段）
- `backend/app/agents/langgraph_agent/nodes/cluster.py`（详情循环收割 open_hours/tel）
- `backend/app/services/attractions_cache_service.py`（发现页收割 open_hours/tel）
- `backend/app/agents/langgraph_agent/finalize/pipeline.py`（`_build_day_context` 透传）
- `backend/app/agents/langgraph_agent/nodes/generate.py`（LLM 路径按名回填）

前端：
- `frontend/src/types/index.ts`（Attraction 加 2 字段）
- `frontend/src/views/Result.vue`（标签栏去 sticky + 切换回顶）
- `frontend/src/components/AttractionCard.vue`（展示开放时间/电话）

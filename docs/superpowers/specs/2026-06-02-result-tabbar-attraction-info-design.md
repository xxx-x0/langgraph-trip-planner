# 结果页：标签栏不固定 + 景点信息增强

- 日期：2026-06-02
- 状态：设计已确认（v2，已按真实数据流修订），待写 Phase 1 实现计划
- 范围：结果页前端 + 后端"发现→草稿→定稿"链路上的景点数据串接

## 背景与问题

用户在最终结果页提出两个问题：

1. **标签栏一直跟随滚动**：四个标签（📋/💰/📍/📅）下滑时钉在顶部，挤占视口、可见内容被压小。
2. **景点信息太少**：每个景点应给出基本信息（开放时间、门票等）。

## v2 修订说明（重要）

初版 spec 假设"开放时间在 `cluster.py:57` 已被抓取、只是丢弃，补上几乎免费"。**经核实，这针对的是 `cluster_attractions_node`，而前端结果页走的是另一条链路**：

```
DiscoverView → /api/trip/discover/stream (发现, 用 attractions_cache_service)
            → /api/trip/draft/from-selections/stream (cluster_from_selections_node → save_draft)
            → /api/trip/draft/{id}/finalize (finalize_draft → _build_day_context → rule_assemble)
```

在这条链路上发现的**真正根因**：

- `cluster_from_selections_node`（`cluster.py:391-416`）把用户已选景点**砍成只剩 `{name, longitude, latitude}`**，丢弃 address / rating / ticket_price / category / description / poi_id / visit_minutes / image_url。
- `_build_day_context`（`finalize/pipeline.py:80-91`）用残料造 `Attraction`，`address=""`、`description=""`、`visit_duration=120`(硬编码)、`ticket_price=0`。
- `finalize_draft`（`pipeline.py:122-162`）确定性装配，不再补全。

**所以"信息太少"主因是数据在聚类步被丢弃**，而非"开放时间没抓"。用户在发现页选景点时，缓存其实已带 address/rating/ticket_price/category/description（`discovery.py:22-32`）。

## 高德/缓存数据可得性（核实结论）

| 信息 | 可得性 | 来源 |
|---|---|---|
| 地址/评分/门票/类别/简介/游览时长/封面图 | ✅ 已在手 | 发现页已选数据（`DiscoveredAttraction`），只是被 `cluster_from_selections` 丢弃 |
| 开放时间 | ✅ 可得（需持久化） | `attractions_cache_service._fetch_detail`（`:455`）**已在调 `maps_search_detail`**，但未抓 `biz_ext.opentime_today/week`；缓存是 SQLite 持久化（`AttractionCache` ORM），需加列 |
| 电话 | ✅ 可得（需持久化） | 同上，`biz_ext.tel` |
| 特色标签(tag) | ⚠️ 不确定 | AMap detail 偶有 `tag`，覆盖率未知，列为可选 |
| 门票价格(精确) | ⚠️ 不可靠 | `biz_ext.cost`(人均)，景点常空，维持"有则显示" |
| 是否需预约 | ❌ 无 | 高德无此字段，不做 |

## 目标 / 非目标

**目标**
- 标签栏改为完全不固定；切换标签平滑回顶。
- 景点卡片信息变丰富：保留用户已选的 address/rating/ticket_price/category/description，带上真实 visit_duration 与 image_url；并（Phase 2）补开放时间/电话。
- 数据随行程持久化。

**非目标**
- 不做"是否需预约"。不臆造门票。不改时间轴展示。不做订票链接。

## 分阶段

### Phase 1 — 修根因（零 DB 改动、零新增 API 调用）

让 `cluster_from_selections_node` 不再丢字段，`_build_day_context` 完整映射到 `Attraction`。卡片前端对 address/rating/ticket_price/category/visit_duration **已有渲染**，数据一通即自动变丰富。再加标签栏(前端)改动。

**改动点**

1. **`backend/app/agents/langgraph_agent/nodes/cluster.py` `cluster_from_selections_node`（`391-416`）**：
   两个分支（`day_assignments` 分支与 `valid_attractions` 分支）都改用统一的映射，把每个已选景点完整转成 cluster dict（保留 name/longitude/latitude/address/category/rating/ticket_price/description/poi_id/visit_minutes/image_url）。提取一个纯函数 `_selection_to_cluster_dict(attr: dict) -> dict` 供两分支复用。
   - 注意 `valid_attractions` 分支仍需 longitude/latitude 有效才纳入聚类；坐标缺失的保持现有兜底。下游 `_haversine_distance` / `_cluster_attractions_by_proximity` / `_order_cluster_by_tsp` / `_format_cluster_info` 只读 name/经纬度，多余键无害；`clusters_data` 经 JSON 持久化到草稿，额外字段可正常序列化。

2. **`backend/app/agents/langgraph_agent/finalize/pipeline.py` `_build_day_context`（`80-91`）**：
   构造 `Attraction` 时映射全部字段：
   - `address=c.get("address", "")`
   - `description=c.get("description", "")`
   - `category=c.get("category") or "景点"`
   - `rating=c.get("rating")`
   - `ticket_price=_parse_ticket_price(c.get("ticket_price"))`（str→int）
   - `visit_duration=c.get("visit_minutes") or 120`
   - `image_url=c.get("image_url")`
   - `poi_id=c.get("poi_id") or ""`
   - location 维持现有逻辑

3. **`_parse_ticket_price(val) -> int` 纯函数**（放 `finalize/pipeline.py` 或 `utils/parsing.py`）：
   `DiscoveredAttraction.ticket_price` 是字符串（如 `"60"`/`"免费"`/`None`）；`Attraction.ticket_price` 是 int。规则：抽取数字 → int；`"免费"`/无数字/None → 0。

4. **`frontend/src/views/Result.vue`**：
   - 删除 `.tab-bar` 的 `position: sticky; top: 64px; z-index: var(--z-sticky);`（`560-567`）。
   - `<script setup>` 加 `watch(activeTab, ...)`：切换时 `window.scrollTo({ top: 0, behavior })`，`behavior` 由 `prefers-reduced-motion` 决定（reduce→`'auto'`，否则 `'smooth'`）。
   - 保留 `a-back-top`。

**前端卡片无需改动**（`AttractionCard.vue` 已渲染 address/rating/ticket_price/category/visit_duration/description）。

### Phase 2 — 开放时间 / 电话（独立计划，后续）

1. `attractions_cache_service.py`：`_extract_detail_from_result` / 详情增强补抓 `biz_ext.opentime_today|opentime_week → open_hours`、`biz_ext.tel → tel`。
2. `AttractionCache` ORM 表加列 `open_hours`、`tel`（SQLite 加列迁移）；`CachedAttraction` 数据类、`_row_to_cached` / `_dict_to_cached` / 行构建 dict 同步加字段。
3. `discovery.py:_cached_attraction_to_discovery_item` 带上 open_hours/tel。
4. `DiscoveredAttraction`（schemas.py）加 `open_hours`/`tel`；`Attraction` 加 `open_hours`/`tel`。
5. `_selection_to_cluster_dict` + `_build_day_context` 透传这两字段。
6. 前端 `Attraction` 类型加 `open_hours?`/`tel?`；`AttractionCard.vue` 非编辑态新增两行（仅有值时渲染）：🕐 开放时间；📞 电话（移动端 `tel:` 链接，桌面端纯文字，移动端判定 `window.matchMedia('(pointer: coarse)')`）。
7. （可选）特色标签 tag：再加一列 + 一行展示，覆盖率不确定。

## 诚实边界

- 不编造：字段无值则整行不显示、不写"暂无"。
- 缓存加列后，**旧缓存行的 open_hours/tel 为 NULL**，随缓存刷新（TTL）逐步补齐；不回填历史草稿。
- 门票价格维持"有则显示"，不臆造。

## 测试策略

**Phase 1**
- `_parse_ticket_price`：`"60"→60`、`"免费"→0`、`None→0`、`"￥80起"→80`。
- `_selection_to_cluster_dict`：富字段 dict → 保留全部目标键；缺失字段安全降级。
- `_build_day_context`：喂带富字段的 clusters_data → 断言 `Attraction` 的 address/description/category/rating/ticket_price(int)/visit_duration/image_url 正确；缺字段时安全默认。
- 前端：`npm run build`(类型检查) + 人工核对标签栏不再固定、切换回顶、卡片信息变丰富。

**Phase 2**（其计划内详列）：缓存抓取 open_hours/tel、串接透传、卡片有/无值显示与隐藏、移动端拨号。

## 改动文件清单（Phase 1）

后端：
- `backend/app/agents/langgraph_agent/nodes/cluster.py`（`cluster_from_selections_node` + `_selection_to_cluster_dict`）
- `backend/app/agents/langgraph_agent/finalize/pipeline.py`（`_build_day_context` 全字段映射 + `_parse_ticket_price`）

前端：
- `frontend/src/views/Result.vue`（标签栏去 sticky + 切换回顶）

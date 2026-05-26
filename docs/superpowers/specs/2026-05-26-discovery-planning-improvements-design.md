# 发现页与规划流程改进 设计文档

- 日期：2026-05-26
- 范围：景点选择页、AI 一键选景、日程分配、加载页、酒店显示与预算

## 1. 背景与问题

用户在使用发现页 → 日程分配 → 结果页全流程时，反馈了 5 个问题：

1. 发现页景点数量在短行程（≤ 3 天）下始终为 20，硬上限 40，覆盖度不足
2. 缺少跳过"逐个手动勾选"的快捷入口
3. 日程分配只做了地理聚类，没考虑单天时长是否合理
4. `PlanProgress` 加载页 8 步进度大多已无内容显示，体验割裂
5. 酒店相关：
   - 5A：酒店名"维景大酒店(Winjing Hotel)"过长，括号英文应去掉
   - 5B：预算 Tab 的"酒店"项显示 0 元，但酒店明细已带价格 —— 真 bug

## 2. 设计原则

- **保留发现页主流程不变**，新增"AI 帮我选"作为快捷入口，不强制替换手动勾选
- **后端接口保持向后兼容**，新端点单独加，不破坏 `/api/discover/stream`、`/api/plan` 等现有路由
- **SSE 协议不动**，只把消费方从 DiscoverView 搬到 Result
- **YAGNI**：不重写聚类算法，用最小后处理满足"距离 + 时长"双约束

## 3. 模块 1 — 景点池扩容 + 分页加载

### 3.1 后端

- **修改** `backend/app/agents/langgraph_agent/nodes/discovery.py:44`
  - 旧：`max_count = min(40, max(20, request.travel_days * 6))`
  - 新：`max_count = 30`（固定首屏数量，与天数解耦）
- **抽取可重入函数** `_search_and_extract_attractions(destination, exclude_names, batch_size)`
  - 复用 Bing 搜索 + LLM 提取景点名 + geocoding 三步
  - 支持传入 `exclude_names: List[str]` 避免重复
- **新增端点** `POST /api/discover/load_more`
  - 入参：`{trip_id: str, destination: str, exclude_ids: List[str], batch_size: int = 20}`
  - 出参：`{attractions: List[Attraction]}`（含 location，已 geocode）
  - 实现：调 `_search_and_extract_attractions`，过滤 `exclude_ids` 对应的景点

### 3.2 前端 `DiscoverView.vue`

- 景点列表底部新增"加载更多 +20"按钮
- loading 状态期间禁用按钮，文案改为"加载中…"
- 累计 > 100 时按钮置灰 + 文案"已达上限"
- 新加载的景点追加到现有 `attractions` 数组末尾，触发现有 `attractionCategories` 重新计算

### 3.3 验收

- 3 天行程进入发现页：首屏 30 个景点
- 点"加载更多"：增加约 20 个，与现有去重
- 连续点击直至 ≥ 100 时按钮禁用

## 4. 模块 2 — AI 帮我选（从攻略提取）

### 4.1 后端

**新节点** `extract_from_strategy_node`（位于 `nodes/discovery.py` 或新建 `nodes/strategy.py`）

逻辑：
1. Bing 搜索：`{destination} {days}日游 经典攻略`
2. 取 top 5 结果摘要，拼接后送 LLM
3. LLM 用结构化输出（不支持时降级 JSON-in-prompt）提取攻略中出现的景点名列表
4. 与当前 `attractions` 做模糊匹配：
   - 去除"景区/公园/博物馆"等后缀对齐
   - 命中则收集对应 `attraction_id`
5. 返回 `recommended_ids: List[str]`

**新增端点** `POST /api/discover/ai_select`
- 入参：`{trip_id: str, destination: str, days: int, attractions: List[Attraction], preferences?: dict}`
  - `attractions` 是前端当前展示的景点池（含 id、name），用于模糊匹配
- 出参：`{recommended_ids: List[str], source_strategy_title?: str}`

### 4.2 前端

- 在搜索栏右侧加 **"✨ AI 帮我选"** 按钮
- 点击后：
  - loading 文案"正在分析攻略…"
  - 成功：将 `recommended_ids` 对应卡片自动勾选，弹 toast"已根据攻略选好 N 个景点"，滚动到底部 CTA
  - 失败：toast 报错"AI 推荐失败，请手动选择"，按钮恢复
- 若返回数量为 0：toast"未找到适合的攻略，请手动选择"

### 4.3 验收

- 点 AI 按钮 → 5 秒内得到推荐勾选
- 推荐数量在 `days × 3` ~ `days × 6` 之间为正常

## 5. 模块 3 — 日程分配 时长均衡后处理

### 5.1 后端工具

**新函数** `balance_day_duration(day_assignments, attractions_by_id) -> day_assignments`
（位于 `backend/app/agents/langgraph_agent/utils/route.py` 或新建 `utils/balance.py`）

逻辑：
1. 默认 `visit_duration = 120` 分钟（若景点 `estimated_visit_duration` 缺失）
2. 每天计算：`total_minutes = Σ visit_duration + 90 (餐饮) + 通勤估算`
   - 通勤估算：相邻景点平均按 20 分钟，可调
3. 若某天 `total_minutes > 480`：
   - 找该天距离簇中心最远的景点 → 挪到 `total_minutes` 最小的另一天
4. 若某天景点数 < 2：
   - 从最满天抽一个该天最近的景点过来
5. 最多迭代 5 次，达到稳定状态或无可优化即退出

### 5.2 调用位置

- `cluster_attractions` 节点之后，立即调一次
- `POST /api/discover/preview_day_assignment` 接口内部，返回前再调一次（兜底）

### 5.3 前端

- 现有红色"超 480 分钟"预警保留
- `Day Card` 标题旁加 ℹ️ tooltip："已根据距离和时长自动均衡，可手动拖拽调整"

### 5.4 验收

- 选 10 个分布广的景点 → 3 天行程：单天不超 480，每天 ≥ 2 个景点
- 拖拽手动调整后，提示但不强制再均衡

## 6. 模块 4 — 删除加载页 + 结果页骨架屏

### 6.1 前端流程改动

**DiscoverView.vue**
- `createDraftFromSelectionsStream()` 启动后**立即** `router.push('/result?streaming=true&trip_id=...')`
- 不再渲染 `PlanProgress` 全屏组件
- 把 SSE 订阅逻辑搬走

**Result.vue**
- 接收 `streaming=true` 查询参数 → 进入骨架模式
- 订阅 SSE 流（移自 `DiscoverView`）
- 各组件骨架渲染规则：
  - `ResultHero`：渐变骨架 + 微动效"AI 正在为你定制行程…"
  - `TabOverview` / `TabItinerary` / `TabBudget` / `TabMap` / `TabWeather`：内部骨架卡片
- 数据填充时机：
  - `macro_planner` 完成 → 填充 ResultHero 标题、城市、天数
  - `reduce_assemble` 完成 → 渲染每日行程 Tab
  - `global_synthesizer` 完成 → 渲染预算、贴士 Tab
- 错误处理：
  - SSE 中断或抛错 → 显示 `ErrorState` 卡片 + "重试"按钮，重试调用同一 SSE 端点

### 6.2 保留 PlanProgress.vue

- 不删该组件
- 首页"一次性生成"流程若仍引用，保持不变
- 从 `DiscoverView.vue` 的 import 中摘除

### 6.3 后端

- SSE 协议**不动**
- 端点 `/api/trip_lg/plan_from_selections_stream`（或现名）保持原样

### 6.4 验收

- 在发现页确认日程 → 点"下一步"立即看到结果页骨架
- 数据陆续填入，无白屏切换
- 中途网络中断 → 显示错误卡片，重试可恢复

## 7. 模块 5 — 酒店两个修复

### 7.1 5A 名字去括号英文（前端）

**新工具** `frontend/src/utils/format.ts`（或加入已有 utils）：

```ts
export function cleanHotelName(name: string): string {
  return name.replace(/[(（][^)）]*[)）]/g, '').trim()
}
```

**调用点**（按 `grep -r "hotel\..*name\|hotel\?\.name" frontend/src` 结果替换）：
- `TabItinerary.vue` 中所有酒店名显示
- `TabOverview.vue` 中酒店摘要
- 日程卡片（DayCard / ItineraryDayItem）酒店行
- Hero 中如果有酒店名也加上

### 7.2 5B 预算 0 元 bug

**根因**：`backend/app/agents/langgraph_agent/nodes/search.py` 的 `_parse_aigohotel_hotels()` 把 AIGoHotel 返回的 `price`（float）写进了 Hotel 模型的 `price` 字段，但 `generate.py:1460` 计算预算时读的是 `estimated_cost`。

**修复**：在 `_parse_aigohotel_hotels()` 构造 Hotel item 时补：

```python
item["estimated_cost"] = int(item.get("price") or 0)
```

**兜底**（极端情况下 price 也是 0）：
- 按 `star_rating` 估算：`estimated_cost = star_rating * 200` （3 星 = 600，4 星 = 800，5 星 = 1000）
- 若连 `star_rating` 都没有：默认 500

### 7.3 验收

- 5A：进入结果页 → 所有酒店名不再出现英文括号
- 5B：跑一个真实行程 → 预算 Tab 的"酒店"项 > 0 且与日程卡片中酒店金额加总一致

## 8. 实施顺序建议

按风险从低到高、收益从高到低排：

1. **模块 5B**（预算 bug 修复）— 1 个文件改一行 + 兜底
2. **模块 5A**（酒店名清理）— 前端工具函数 + 批量替换
3. **模块 1**（景点池扩容 + 加载更多）
4. **模块 3**（日程时长均衡）
5. **模块 2**（AI 帮我选）— 新功能，依赖额外 Bing 调用
6. **模块 4**（骨架屏改造）— 跨多组件，最复杂

模块 5A、5B 可独立先合入，不阻塞其他。

## 9. 风险与备注

- **AI 帮我选的 Bing 调用稳定性**：MCP 服务已有重连机制，但攻略页面文本可能很长，需关注 token 成本。可考虑只取摘要的前 500 字
- **加载更多去重**：景点名称可能因别名（"故宫" vs "故宫博物院"）漏判重复，模糊匹配阈值需调试
- **骨架屏数据时机**：SSE 事件粒度若与组件渲染粒度对不上，可能出现"部分骨架先消失部分后消失"的视觉不一致；接受这种渐进体验
- **时长均衡的边界**：当总景点数 ÷ 天数 ≥ 5 时，单天可能无论如何都超 480，需要 UI 提示但不强制再均衡

## 10. 不在范围内

- 不重写 `cluster_attractions` 的 KMeans 逻辑
- 不修改 SSE 协议
- 不引入新的搜索源（继续用 Bing + AMap）
- 不做酒店名翻译 / 重命名（只裁切英文括号）
- 不删除 `PlanProgress.vue` 组件本身

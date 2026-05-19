# 骨架/详细分离 + 路线懒计算（每日装配器）设计

- **日期**：2026-05-20
- **作者**：Finn
- **状态**：设计中
- **关联代码**：`backend/app/agents/langgraph_agent/`、`backend/app/api/routes/trip_lg.py`、`frontend/src/views/DiscoverView.vue`

## 1. 背景与问题

当前 `planning_app`（Discover 勾选→规划）在 `macro_planner` 之后会扇出 `day_plan_subgraph` 并行生成每一天，子图内部由 LLM 一次性生成完整时间轴：景点顺序 + 强制三餐（早午晚）+ route_segments。这套强编排带来三类问题：

1. **强制三餐不合理**。旅行中用户可能跳过某一餐、有自己想吃的、不接受推荐；旅行节奏里还可能有小吃/甜品/咖啡/夜宵这类目前模型完全无法表达的事项。
2. **路线 + 三餐被 LLM 一次性产出，用户一改就废**。用户删一家餐厅、换一家、调一下顺序，整张时间轴和路线段都不再匹配，要么手动忽略要么整页重生。
3. **生成耗时长**。`day_plan_subgraph` 内每天一次 LLM 调用、一次 amap 路线规划、可能 retry 3 次，N 天并行也要等最慢的一天。用户首屏要等几十秒看到的还是一个"可能马上就要被改"的死规划。

## 2. 目标 / 非目标

### 目标

- 把"一次性完整规划"拆成"骨架（地理 + 候选池）"+"按需详细（用户驱动装配）"两阶段
- LLM 退出"时间轴编排"职责，只负责"写当日叙述文案"和（可选的）"AI 重新安排"
- 时间轴由后端规则装配，路线段由 amap 计算，用户改动 → 秒级重算
- 餐饮模型从"早午晚三餐固定槽位"扩展为"多类别候选池 + 用户自由组合"
- 草稿状态服务端持久化，断线/刷新可恢复

### 非目标

- 不改 Discover 阶段（发现 + 勾选 + 天气）
- 不动 `plan_trip_stream`、`start_interactive_plan` 等已废弃入口（保留为死代码）
- 不改用户偏好学习模型本身，只调整触发时机（从生成阶段后移到 finalize）
- 不引入 Celery 或外部任务队列；TTL 清理用 startup hook + 后台 task

## 3. 关键决策摘要

| # | 决策 |
|---|---|
| 1 | 骨架粒度 = 景点坐标 + 多类别餐饮候选池 + 酒店候选池 + macro_plan |
| 2 | 草稿持久化 = `trip_drafts` 表（在 `trips.db`） |
| 3 | 详细生成触发 = 首屏默认展开第 1 天，其余按需 |
| 4 | 时间轴 = 后端规则装配，LLM 只写当日叙述文案 |
| 5 | 餐饮模型 = `main / snack / dessert / cafe / late_night` 多类别候选池，默认仅嵌 1 个 main |
| 6 | "AI 重新安排" = 可选按钮，单次 LLM 看候选池给推荐组合 |
| 7 | 路线 = 用户每次改动重算 amap，无 LLM，秒级 |
| 8 | 入口范围 = 只重构 `planning_app`；旧 `plan_trip_stream` / interactive 保留不动 |
| 9 | 定稿 = 用户显式触发 `/finalize` 才转 `trip_history`；该阶段才跑 `global_synthesizer` + `extract_preferences` |
| 10 | 草稿 TTL = 30 天未活动清理 |

## 4. 数据流总览

```
[Discover 阶段]                       [骨架阶段]                              [详细阶段]

发现+勾选景点 ──→ skeleton_graph:
                  cluster_from_selections
                  ├─ search_dining_pool   → dining_pool
                  ├─ search_hotels_by_day → hotels_by_day
                  └─ macro_planner        → macro_plan
                  ↓
                  save_draft (写 trip_drafts)
                  ↓
SSE 返回 draft_id ──────────────────────┐
                                          │
                            前端：GET /draft/{id} → 渲染骨架 + 地图
                                          │
                                          ↓
                            首次进入：自动调 assemble(day=0)
                            其他天：用户点"展开装配"再调
                                          │
                                          ↓
                            后端 assemble：
                            ├─ rule_assemble_timeline (规则)
                            ├─ compute_route_segments (amap)
                            └─ write_day_narrative_llm (LLM 写文案)
                                          │
                                          ↓
                            前端：渲染 day_detail
                                          │
                            用户拖拽 / 加餐 / 删餐 / 换餐：
                                          ↓
                            recompute / add-dining / remove-dining / reorder
                            (规则装配 + amap，无 LLM)
                                          │
                            用户点"AI 重新安排" → ai-rearrange (LLM)
                            用户点"重写叙述" → narrative (LLM)
                                          │
                            用户点"定稿":
                                          ↓
                            finalize：global_synthesizer + extract_preferences
                                       → trip_history insert + draft.status='finalized'
                                          │
                                          ↓
                            跳转 /trip/{trip_id}（只读 Result 页）
```

## 5. 数据模型

### 5.1 数据库表（追加到 `trips.db`）

```sql
CREATE TABLE trip_drafts (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL DEFAULT 'default',
  status TEXT NOT NULL DEFAULT 'skeleton',     -- skeleton / assembling / finalized / expired

  request_json TEXT NOT NULL,                  -- 原始 TripRequest
  selected_attractions_json TEXT NOT NULL,     -- List[DiscoveredAttraction]

  macro_plan_json TEXT NOT NULL,               -- MacroPlan
  clusters_data_json TEXT NOT NULL,            -- 按日聚类排序的景点（含坐标）
  hotels_by_day_json TEXT NOT NULL,            -- 每日酒店候选池
  dining_pool_json TEXT NOT NULL,              -- 每日多类别餐饮候选池
  weather_info_json TEXT NOT NULL,             -- 已抓到的天气

  days_detail_json TEXT NOT NULL DEFAULT '[]', -- List[Optional[DayDetail]] 与天数等长

  trip_tagline TEXT DEFAULT '',                -- finalize 后填充
  overall_suggestions TEXT DEFAULT '',
  weather_summary TEXT DEFAULT '',

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finalized_at TIMESTAMP
);

CREATE INDEX idx_drafts_user ON trip_drafts(user_id, status);
CREATE INDEX idx_drafts_updated ON trip_drafts(updated_at);
```

ORM：在 `app/models/db_models.py` 新增 `TripDraft` SQLAlchemy 模型。服务封装到新文件 `app/services/trip_draft_service.py`，提供 CRUD + 按字段 patch（`patch_day_detail(draft_id, day_index, day_detail)`）+ TTL 清理。

### 5.2 Pydantic Schema（追加到 `schemas.py`）

```python
class DiningCategory(str, Enum):
    MAIN = "main"
    SNACK = "snack"
    DESSERT = "dessert"
    CAFE = "cafe"
    LATE_NIGHT = "late_night"

class DiningCandidate(BaseModel):
    name: str
    address: Optional[str] = None
    location: Optional[Location] = None
    category: DiningCategory
    cuisine: Optional[str] = None
    rating: Optional[float] = None
    avg_cost: Optional[int] = None
    distance: Optional[str] = None
    open_hours: Optional[str] = None
    tel: Optional[str] = None
    poi_id: Optional[str] = None
    source: str = "nearby"                  # nearby / popular / user_custom

class DiningPoolDay(BaseModel):
    main: List[DiningCandidate] = []
    snack: List[DiningCandidate] = []
    dessert: List[DiningCandidate] = []
    cafe: List[DiningCandidate] = []
    late_night: List[DiningCandidate] = []

# 修改 Meal 模型：新增 category 字段（向后兼容 type）
class Meal(BaseModel):
    type: str                               # 兼容旧值 breakfast/lunch/dinner/snack
    category: Optional[DiningCategory] = None  # 新版本主用此字段
    name: str
    # ... 其余字段保持原样

class DraftDayContext(BaseModel):
    """骨架阶段每日上下文"""
    day_index: int
    date: str
    attraction_names: List[str]
    attractions: List[Attraction]           # 已 geocode 完整对象
    hotel: Optional[Hotel]                  # macro_planner 选定的当日酒店
    dining_pool: DiningPoolDay
    weather: Optional[WeatherInfo] = None

class DayDetail(BaseModel):
    """详细阶段产物"""
    day_index: int
    date: str
    description: str = ""                   # LLM 写的叙述
    attractions: List[Attraction]
    hotel: Optional[Hotel] = None
    meals: List[Meal] = []                  # 用户实际勾选的
    route_segments: List[RouteSegment] = []
    timeline_order: List[Dict[str, Any]] = []  # [{kind:"attraction|meal|hotel", ref_id, ref_name}]
    day_budget: Optional[Budget] = None     # 当日预算（每次 recompute 刷新）
    is_assembled: bool = False

class TripDraftPayload(BaseModel):
    """骨架阶段返回给前端的完整草稿"""
    draft_id: str
    status: str
    request: TripRequest
    city: str
    macro_plan: MacroPlan
    days: List[DraftDayContext]
    days_detail: List[Optional[DayDetail]]
    weather_info: List[WeatherInfo]
    created_at: str
    updated_at: str
```

### 5.3 餐饮候选池生成规则（`search_dining_pool_node`）

每日按 5 类并发跑 amap POI 搜索，地理中心 = 当日景点中心：

| 类别 | amap 关键字 | top N |
|---|---|---|
| `main` | "餐厅 美食" | 6 |
| `snack` | "小吃 街边小吃" | 4 |
| `dessert` | "甜品 蛋糕 茶饮" | 4 |
| `cafe` | "咖啡馆" | 4 |
| `late_night` | "夜宵 烧烤 大排档" | 4 |

5 个搜索 `asyncio.gather`，单类失败不阻塞其他类，失败类返回 `[]`。结果按 `rating desc, distance asc` 排序。

**地理中心**：当日所有 `attractions` 的经纬度算术平均值。若当日景点全部 geocode 失败，退化为城市级搜索（不带 location，amap `text_search`）。

## 6. API 端点

所有端点挂 `/api/trip/draft/*`，集中在新文件 `app/api/routes/trip_draft.py`。

| 方法 | 路径 | 形态 | 说明 |
|---|---|---|---|
| POST | `/api/trip/draft/from-selections/stream` | SSE | 从 Discover 勾选生成骨架；写 `trip_drafts`；返回 `draft_id` |
| GET | `/api/trip/draft/{id}` | JSON | 读完整草稿（刷新/恢复） |
| POST | `/api/trip/draft/{id}/day/{n}/assemble` | JSON | 首次展开某天：rule_assemble + amap + LLM 叙述（≈ 5-15s）。**幂等**：若该天已 `is_assembled=true` 且未带 `force=true` 参数，直接返回当前 `day_detail`，不重新跑 LLM |
| POST | `/api/trip/draft/{id}/day/{n}/recompute` | JSON | 用户改动后重算（拖拽 / 加餐 / 删餐 / 换餐都走这个）：rule_assemble + amap，无 LLM（< 1s） |
| POST | `/api/trip/draft/{id}/day/{n}/ai-rearrange` | JSON | LLM 看候选池给推荐组合 + amap |
| POST | `/api/trip/draft/{id}/day/{n}/narrative` | JSON | 单次 LLM 写当日叙述 |
| POST | `/api/trip/draft/{id}/finalize` | SSE | 跑 global_synthesizer + extract_preferences + 写 trip_history |
| DELETE | `/api/trip/draft/{id}` | JSON | 物理删除 |

### 6.1 `/recompute` 请求模型（所有用户编辑都走这个）

```jsonc
{
  "attractions_order": ["景点A", "景点B"],
  "meals": [
    { "category": "main", "name": "...", "location": {...}, "insert_after": "景点A" }
  ]
}
```

后端把 `meals` 完全视为"用户当前的勾选状态"——没有则空，有则照搬。`insert_after` 是景点名（或 `"hotel_start"` / `"hotel_end"`），决定插入位置。返回值统一是更新后的 `DayDetail`。

**字段缺失语义**（重要）：

- 请求体**不传 `attractions_order`**：保留当前 `day_detail.attractions` 的顺序不动
- 请求体**不传 `meals`**：保留当前 `day_detail.meals` 不动
- 请求体**传 `meals: []`**（空数组）：**清空所有餐饮**

这意味着所有改动端点都要求前端发送"完整意图状态"而非"差异 patch"。这样后端无需理解"加 / 删 / 换"语义，统一一套规则装配代码。

### 6.2 错误码

- `404` draft 不存在
- `409` draft 已 `finalized` 不可改 / day_index 越界
- `422` 入参不合法（如 category 不在枚举里）
- `503` MCP/LLM 不可用（部分端点降级，见 §8）

## 7. 后端 graph / node 重构清单

```
backend/app/agents/langgraph_agent/
├── graph.py
│   - create_planning_graph()  改为只跑骨架阶段，结束写 draft
│   + create_skeleton_graph()  新名字（保留 create_planning_graph alias 以免破坏 import）
├── nodes/
│   ├── cluster.py            （不变）
│   ├── food.py
│   │   - search_food_node    保留但骨架图不再引用
│   │   + search_dining_pool_node   新，按 5 类并发，返回每日 DiningPoolDay
│   ├── search.py             （不变）
│   ├── generate.py
│   │   - day_plan_subgraph 系列      保留但骨架图不再引用
│   │   - reduce_assemble_node        保留但骨架图不再引用
│   │   - global_synthesizer_node     移到 finalize 流程调用
│   │   - macro_planner_node          保持不变
│   ├── route.py
│   │   - plan_route_node             继续保持空操作
│   └── preferences.py        （不变，仅 finalize 时调）
├── assemble/                 新目录
│   ├── timeline.py
│   │   + rule_assemble_day_timeline(day_ctx, user_overrides) -> DayDetail
│   ├── route.py
│   │   + compute_day_route(day_detail, city, transportation) -> List[RouteSegment]
│   └── narrative.py
│       + write_day_narrative_llm(day_detail, weather, free_text) -> str
└── finalize/                 新目录
    └── pipeline.py
        + finalize_draft(draft_id, user_id) -> TripPlan
```

### 7.1 骨架图新拓扑

```
START → load_user_preferences → cluster_from_selections → ┬─ search_dining_pool   ┐
                                                          ├─ search_hotels_by_day ├─→ macro_planner → save_draft → END
                                                          └─ (weather 已有/复用)  ┘
```

`load_user_preferences` 沿用现有节点，让 `macro_planner` 仍能根据用户历史偏好做酒店/景点选择。`extract_preferences` / `save_preferences` 不在骨架图里跑，移到 finalize 流程。

### 7.2 规则装配（`rule_assemble_day_timeline`）

```python
def rule_assemble_day_timeline(day_ctx, overrides=None):
    overrides = overrides or {}

    # 1. 景点顺序：用户给了用用户的；否则用 day_ctx.attractions（已聚类排序）
    attractions = apply_order(day_ctx.attractions, overrides.get("attractions_order"))

    # 2. 餐饮：用户给了完全用用户的；否则默认嵌一个 main top1 在景点中点之后
    if "meals" in overrides:
        meals = build_meals_from_overrides(overrides["meals"])
    elif day_ctx.dining_pool.main:
        main_top1 = day_ctx.dining_pool.main[0]
        mid = max(len(attractions) // 2 - 1, 0)
        meals = [meal_from_candidate(main_top1, insert_after=attractions[mid].name)]
    else:
        meals = []

    # 3. timeline_order 按规则穿插 meal 到对应 insert_after 之后
    timeline = build_timeline(attractions, meals, hotel=day_ctx.hotel)

    return DayDetail(
        day_index=day_ctx.day_index,
        date=day_ctx.date,
        attractions=attractions,
        meals=meals,
        hotel=day_ctx.hotel,
        timeline_order=timeline,
        is_assembled=True,
    )
```

`compute_day_route` 从 `timeline_order` 提取 waypoints → 调 `utils.route.compute_route_segments`（已有）→ 填回 `route_segments`。

### 7.2.1 预算计算

旧流程在 `reduce_assemble_node` 里汇总全程预算（门票 + 餐饮 + 酒店 + 估算交通费）。新流程分两层：

- **每日预算**：`rule_assemble_day_timeline` 顺手把当日预算算好填进 `DayDetail`（新增 `day_budget: Budget` 字段，仅含当天）。每次 `recompute` 自然刷新
- **全程预算**：finalize 阶段累加所有 `day_detail.day_budget` 得到 `TripPlan.budget`
- **骨架阶段**：不提供 budget。前端 budget tab 在 draft 阶段基于"已 assemble 的天"实时计算 preview，标注"已展开 X/N 天"；finalize 后才算总数

### 7.3 LLM 叙述（`write_day_narrative_llm`）

prompt 输入：城市、日期、已确定的景点 / 酒店 / 餐厅名单、天气、`free_text_input`。

输出：2-3 段 markdown 文案，含穿衣 / 注意事项 / 体验亮点。**禁止输出时间轴、景点顺序、餐厅推荐**——这些都不在它的职责。

### 7.4 finalize 流程

```python
async def finalize_draft(draft_id, user_id):
    draft = await trip_draft_service.get(draft_id)
    if draft.status == "finalized":
        raise HTTPException(409)

    # 1. 拼 TripPlan：days 来自 draft.days_detail（缺失的天用 fallback 装配）
    days = []
    for n, detail in enumerate(draft.days_detail):
        if detail and detail.is_assembled:
            days.append(detail.to_day_plan())
        else:
            # 用户没展开的天，自动装配一次默认时间轴（不调 LLM 叙述）
            assembled = rule_assemble_day_timeline(draft.days[n])
            assembled.route_segments = await compute_day_route(assembled, ...)
            days.append(assembled.to_day_plan())

    trip_plan = TripPlan(city=..., days=days, weather_info=..., budget=compute_budget(days), ...)

    # 2. global_synthesizer 填 tagline / overall_suggestions / weather_summary
    trip_plan = await global_synthesizer_node({"trip_plan": trip_plan, ...})

    # 3. extract_preferences + save_preferences
    await extract_preferences_node({"trip_plan": trip_plan, "user_id": user_id})

    # 4. 写 trip_history
    trip_id = await trip_history_service.create(trip_plan, user_id)

    # 5. 标记 draft finalized
    await trip_draft_service.mark_finalized(draft_id, trip_id)

    return trip_plan, trip_id
```

### 7.5 草稿 TTL 清理

`app/api/main.py` 的 startup hook 注册 background task：每 24h 跑一次 `await trip_draft_service.delete_expired(days=30)`，物理删除 `status != 'finalized' AND updated_at < now - 30 days` 的记录。

## 8. 错误处理与降级

| 故障 | 降级 |
|---|---|
| dining_pool 某一类 amap 搜索失败 | 该类返回 `[]`，前端展示"无候选，可自定义" |
| dining_pool 全部失败 | 骨架仍可保存；assemble 默认不嵌 main；前端展示"今日无餐饮推荐" |
| `search_hotels_by_day` 失败 | 沿用现有 fallback：当日酒店 = 上一天酒店 / 空 |
| `macro_planner` LLM 失败 | 沿用现有默认骨架（每天景点名占位）；draft 仍可保存 |
| assemble 时 amap 路线失败 | `route_segments = []`；前端展示"路线信息暂不可用"；不阻塞 timeline 渲染 |
| `narrative` LLM 失败 | `description` 留空；前端展示"今日叙述生成失败，[重试]" |
| `ai-rearrange` LLM 失败 | 不修改当前 `day_detail`，返回 422；前端提示"AI 暂不可用，请手动调整" |
| finalize 时 global_synthesizer 失败 | 用 `_generate_weather_summary_fallback` + 模板兜底建议；trip_history 仍写入 |
| draft 已 finalized 但用户仍尝试改 | 409；前端跳 `/trip/{id}` 只读视图 |
| draft 30 天未活动 | 后台 task 删除；前端访问失效 draft_id 返回 404，提示重新规划 |

**原则**：所有降级让用户看到具体哪部分失败 + 可重试。新流程不再需要 `_create_fallback_plan` 这种"端到端兜底"——草稿本身就是渐进式的，任何单点失败都不会让整体作废。

## 9. 前端 UX

### 9.1 路由变化

- 新增 `/draft/:id` → `DraftView.vue`
- 保留 `/`、`/discover`、`/result`、`/trip/:id`、`/my-trips`

### 9.2 DiscoverView 改动

`planFromSelectionsStream` 改为调 `/api/trip/draft/from-selections/stream`，SSE complete 事件包含 `draft_id`，立即 `router.push('/draft/' + draft_id)`。

### 9.3 DraftView 主结构

```
┌─ Hero（城市 + 日期 + tagline 占位）
├─ Tab Bar：概览 / 行程 / 地图 / 天气 / 预算
│
│  Tab "行程"（核心）：
│  ├─ Day 1 卡片 [默认展开]
│  │   ├─ 头部：日期 + 天气徽章 + [AI 重新安排] + [重写叙述]
│  │   ├─ 叙述区：description (markdown)，骨架加载态
│  │   ├─ Timeline：
│  │   │   ├─ 🏨 Hotel 出发
│  │   │   ├─ 📍 景点 A（可拖拽）  → [+ 加用餐]
│  │   │   ├─ 📍 景点 B（可拖拽）  → [+ 加用餐]
│  │   │   ├─ 🍴 正餐（默认 top1 / 可换 / 可删）
│  │   │   ├─ 📍 景点 C
│  │   │   └─ 🏨 返回酒店
│  │   └─ 路线段：A → 正餐 0.5km 步行 6min …
│  ├─ Day 2 卡片 [折叠，"展开装配 →"]
│  └─ ...
│
└─ 底部 sticky bar：[定稿并保存]
```

### 9.4 关键交互

- **首次进入**：自动 `assemble(day=0)`
- **点击折叠卡片**："展开装配" → `assemble(day=n)`
- **拖拽景点 / + 加用餐 / 删餐 / 换餐**：本地立即更新视觉状态，500ms debounce → POST `recompute`（统一端点，前端按当前完整状态发送 `attractions_order` + `meals`）
- **+ 加用餐 弹层**：5 个 tab（main/snack/dessert/cafe/late_night）+ 候选列表 + 自定义输入；确认后把新 meal 加入本地状态并触发上述 `recompute`
- **AI 重新安排**：弹确认 → POST `ai-rearrange`
- **重写叙述**：POST `narrative`
- **定稿**：底部按钮 → SSE `finalize` → 拿到 `trip_id` → `router.replace('/trip/' + trip_id)`

### 9.5 状态管理

单文件局部 `ref/reactive` 持 `draft: TripDraftPayload`。每次 API 返回新 `day_detail` 时 splice 到 `draft.days_detail[n]`。离开页面不本地持久化（服务端 draft 即真相，刷新时 `GET /draft/{id}` 恢复）。

## 10. 测试策略

### 10.1 单元测试

```
backend/tests/
├── agents/
│   ├── test_search_dining_pool.py       # 5 类并发、失败隔离
│   ├── test_rule_assemble_timeline.py   # 规则装配多场景
│   │   - 无 override：默认嵌 main top1，位置在中点后
│   │   - 用户改顺序：景点新顺序，meal 跟随 insert_after
│   │   - 用户加 snack：snack 嵌到指定位置
│   │   - 用户删 main：meals 为空
│   │   - dining_pool.main 为空：默认不嵌
│   └── test_finalize_pipeline.py        # finalize 后 trip_history 入库、preferences 更新
├── services/
│   └── test_trip_draft_service.py       # CRUD + 字段 patch + TTL 清理
└── api/
    └── test_draft_endpoints.py
        - from-selections/stream 返回 draft_id
        - GET /draft/{id} 恢复字段一致
        - assemble 第 n 天后 days_detail[n] 不为 null
        - recompute 在 override 下产物正确
        - finalize 后 status='finalized'，再调 assemble 返回 409
        - 404 / 409 / 422 路径
```

### 10.2 集成测试

`tests/integration/test_draft_e2e.py`：mock amap / mock LLM → from-selections → assemble × N → recompute → ai-rearrange → finalize → 验证 trip_history 入库 → 删 draft → 重复访问 404。

### 10.3 现有测试影响

- `tests/agents/test_trip_planner.py`（测旧 `plan_trip` 一次性路径）：保留不动
- `tests/agents/test_connections.py`：保留不动
- `tests/agents/test_search_attractions_*`：保留不动（Discover 未改）

### 10.4 手测脚本

`backend/scripts/manual_draft_demo.py`：跑完整 draft 流程，每步 JSON dump 到 `/tmp/draft_*.json`，便于人工对比新旧产物。

## 11. 实施顺序（粗）

1. **数据层**：`TripDraft` ORM + `trip_draft_service` + alembic 风格的建表脚本（在 `database.py` startup hook 里 `CREATE TABLE IF NOT EXISTS`，沿用项目现有方式）
2. **schema**：`DiningCategory` / `DiningCandidate` / `DiningPoolDay` / `DraftDayContext` / `DayDetail` / `TripDraftPayload` + `Meal.category` 字段
3. **后端**：`search_dining_pool_node` + 改 `create_planning_graph` 为骨架图 + `save_draft` 节点
4. **后端**：`assemble/` 三个模块 + `finalize/pipeline.py`
5. **后端**：`routes/trip_draft.py` 所有端点
6. **前端**：`services/api.ts` 新增 draft 系列方法 + `DraftView.vue` + `DiscoverView` 跳转改造
7. **测试**：按 §10 顺序补单元 → 集成 → 手测
8. **TTL**：startup hook 注册清理任务

每步可独立合并到 main，前端步骤可在后端可用时陆续接入。

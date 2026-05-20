# 景点缓存方案 (方案 B) 设计文档

**日期**: 2026-05-14
**作者**: 与 Claude Code 协作
**状态**: 设计已确认，待用户审阅

## 背景与动机

当前景点搜索流程依赖 DuckDuckGo / Bing 网页搜索 + LLM 提取 + 高德 geocode 三段式管线，存在三个问题：

1. **数据低质** — 攻略博客的杂乱文本要靠 LLM 二次提取，容易丢失或错误识别
2. **慢且不稳定** — DDG 时常被限流，Bing MCP 也有失败率，代码中大量 fallback 分支即是例证
3. **重复劳动** — 相同城市的搜索结果每次都从头跑一遍

本方案用"高德 POI 类型搜索 + 持久化缓存"替代网页搜索路径。一次拉取并入库后，同城市后续请求毫秒级命中。

## 范围

覆盖**两处**景点搜索入口（共享同一缓存表）：

- 主流程 `web_search_attractions_node`（提取约 `travel_days * 3` 个景点）
- 发现流程 `extract_attractions_expanded_node`（提取 20–40 个景点）

## 关键决策一览

| 决策项 | 选择 |
|---|---|
| 范围 | 两处都改，共享缓存表 |
| 网页搜索去留 | **完全移除** Bing/DDG 在景点搜索路径上的使用 |
| 缓存粒度 | 按 `city` 缓存全量 POI；查询时按 `categories` 在应用层过滤 |
| 数据新鲜度 | 永不过期 + 手动刷新 API |
| DB 位置 | 合入现有 `trips.db`（共享 SQLAlchemy 引擎）|
| 代码组织 | 抽 service 层（`attractions_cache_service.py`），节点只调 service |

## 架构

```
┌──────────────────────────────────────────────────────────┐
│       LangGraph 节点层 (search.py / discovery.py)         │
│  search_attractions_node    search_attractions_discovery │
└───────────────────┬──────────────────────────────────────┘
                    │ 调用
                    ▼
┌──────────────────────────────────────────────────────────┐
│      attractions_cache_service.py  (新增)                 │
│  get_attractions(city, min_count, categories)            │
│  find_by_name(city, name)   refresh_city(city)           │
│  _fetch_from_amap(city)     _persist(city, pois)         │
│  _query_db(...)             _normalize_category(...)     │
└────────┬──────────────────────────────┬──────────────────┘
         │ ORM                          │ MCP
         ▼                              ▼
   ┌──────────────┐               ┌──────────────┐
   │ trips.db     │               │ AMap MCP     │
   │ attractions_ │               │ maps_text_   │
   │ cache 表     │               │ search       │
   └──────────────┘               └──────────────┘

┌──────────────────────────────────────────────────────────┐
│      routes/admin.py  (新增, 无认证)                       │
│  POST /api/admin/attractions/refresh?city=xxx            │
│  POST /api/admin/attractions/clear?city=xxx              │
│  GET  /api/admin/attractions/stats                       │
└──────────────────────────────────────────────────────────┘
```

**核心不变量**: service 永远返回**结构化** `CachedAttraction` 列表（不是 LLM 解析的字符串），下游节点彻底不再做 JSON 解析。

## 数据模型

在 `backend/app/models/db_models.py` 新增 ORM 表：

```python
class AttractionCache(Base):
    __tablename__ = "attractions_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 缓存定位
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    poi_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # POI 核心字段（直接来自高德）
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 分类
    amap_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 富信息
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    ticket_price: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("city", "name", name="uq_attractions_city_name"),
        Index("idx_attractions_city", "city"),
        Index("idx_attractions_city_category", "city", "category"),
    )
```

### 设计要点

1. **唯一约束 `(city, name)` 而非 `poi_id`** — 高德偶有 POI 缺 id 的情况，但 name 在城市内基本唯一；upsert 按此约束冲突即覆盖。
2. **`category` 标准化** — 高德 `amap_type` 是分号分隔的层级字符串（如 `"风景名胜;风景名胜;公园广场"`），写入时同时存原始值 + 映射后的中文类别（自然风光 / 历史文化 / 现代都市 / 休闲娱乐 / 购物 / 美食街区 / 亲子 / 宗教 / 其他，对齐 `EXTRACT_ATTRACTIONS_DISCOVERY_PROMPT` 中的枚举）。
3. **坐标用两个 float 字段** — 而不是字符串 `"lng,lat"`，方便后续按地理范围查询。
4. **不加 popularity_score / hit_count** — 保持 MVP 最简；如未来要做本地热门榜再加。
5. **`description` 字段** — 留给 admin 或未来手动编辑，高德 POI 一般为 NULL。

### 自动建表

`database.py` 的 `init_db()` 跑 `Base.metadata.create_all`，新表会自动建好。**不引入 Alembic 迁移**（项目目前也未使用）。

## Service 层 API

新文件 `backend/app/services/attractions_cache_service.py`：

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class CachedAttraction:
    """Service 返回给节点的标准化 POI（与 ORM 解耦）"""
    name: str
    address: Optional[str]
    longitude: Optional[float]
    latitude: Optional[float]
    category: Optional[str]
    rating: Optional[float]
    ticket_price: Optional[str]
    image_url: Optional[str]
    poi_id: Optional[str]
    amap_type: Optional[str]


class AttractionsCacheService:
    async def get_attractions(
        self,
        city: str,
        min_count: int = 20,
        categories: Optional[list[str]] = None,
    ) -> list[CachedAttraction]: ...

    async def find_by_name(
        self, city: str, name: str
    ) -> Optional[CachedAttraction]: ...

    async def refresh_city(self, city: str) -> int: ...
    async def clear_city(self, city: str) -> int: ...
    async def get_stats(self) -> dict[str, int]: ...

    # 内部
    async def _fetch_from_amap(self, city: str, target_count: int = 80) -> list[dict]: ...
    async def _persist(self, city: str, pois: list[dict]) -> int: ...
    async def _query_db(
        self, city: str, categories: Optional[list[str]]
    ) -> list[CachedAttraction]: ...


_service: Optional[AttractionsCacheService] = None

def get_attractions_cache_service() -> AttractionsCacheService:
    global _service
    if _service is None:
        _service = AttractionsCacheService()
    return _service
```

### `get_attractions` 决策表

| DB 命中数 | 行为 |
|---|---|
| `>= min_count` | 直接返回；若传 `categories`，过滤后仍 ≥ min_count 则返回过滤结果，否则返回全部并 log warning |
| `< min_count` 但 > 0 | 跑一次 `_fetch_from_amap` 补全（upsert 去重），**再次 `_query_db`** 拿合并后的结果返回（保证调用方拿到的总是 DB 中已存的状态）|
| `0`（冷启动）| 跑 `_fetch_from_amap`，`_persist` 写入，再 `_query_db` 返回 |

### `_fetch_from_amap` 抓取策略

- 高德 `maps_text_search` 无分页参数，需多组关键词组合拉取
- 关键词列表：`["景点", "公园", "博物馆", "古迹", "广场", "寺庙", "购物中心", "美食街"]`
- 每个关键词调一次，按 name 合并去重
- 累计达到 `target_count`（默认 80）即停止
- 80 = 覆盖 discovery 上限 40 + 留余量用于按偏好过滤

### `find_by_name`

用户在 `free_text_input` 写"想去 XX"时调用：

1. DB 同城精确 name 匹配；不命中尝试去后缀（"风景名胜区/景区/旅游区/度假区/步行街/商业街"）模糊匹配
2. 仍未命中 → 单独调 `maps_text_search` 单点查询
3. 找到后**写入缓存**，再返回 `CachedAttraction`
4. AMap 也找不到 → 返回 `None`

### `_persist` upsert

使用 SQLite 的 `INSERT ... ON CONFLICT(city, name) DO UPDATE`（aiosqlite 支持）。冲突时覆盖：`poi_id`/`address`/`longitude`/`latitude`/`amap_type`/`category`/`rating`/`ticket_price`/`image_url`；保留：`created_at`、`description`（用户手动写的内容不被覆盖）。

### 类别映射

私有函数 `_normalize_category(amap_type: str) -> str`：

```python
AMAP_CATEGORY_MAP = {
    "风景名胜": "自然风光",
    "公园广场": "自然风光",
    "博物馆": "历史文化",
    "文物古迹": "历史文化",
    "宗教": "宗教",
    "购物": "购物",
    "餐饮": "美食街区",
    # ...
}
# 未命中 → "其他"
```

## 节点改造

### 主流程图变更（`graph.py::create_trip_planner_graph`）

**改前**:
```
START ──┬──> web_search_attractions ──> extract_attractions ──> geocode_attractions ──┐
        ├──> search_weather ────────────────────────────────────────────────────────────┤── gather_search
        └──> search_hotel ──────────────────────────────────────────────────────────────┘
```

**改后**:
```
START ──┬──> search_attractions ────┐
        ├──> search_weather ────────┤── gather_search
        └──> search_hotel ──────────┘
```

减少了 `extract_attractions` 与 `geocode_attractions` 两个节点。

### 新节点 `search_attractions_node`

`backend/app/agents/langgraph_agent/nodes/search.py` 中替换旧的 `web_search_attractions_node`：

```python
async def search_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    request = state["request"]
    service = get_attractions_cache_service()

    # 1. 偏好 → category 列表
    categories = _preferences_to_categories(request.preferences or [])

    # 2. 从 cache + amap 拿池子
    min_count = max(request.travel_days * 3, 15)
    pool = await service.get_attractions(
        city=request.city, min_count=min_count, categories=categories
    )

    # 3. 处理用户必访景点（free_text）
    analysis = await analyze_free_text(request.free_text_input or "")
    must_visit_names = analysis.get("attractions", [])
    must_visit_pois = []
    pool_names = {p.name for p in pool}
    for name in must_visit_names:
        if name in pool_names:
            continue
        found = await service.find_by_name(request.city, name)
        if found:
            must_visit_pois.append(found)

    # 4. 拼成下游期望的 attractions_info 字符串（兼容 cluster/route 节点）
    combined = must_visit_pois + pool
    attractions_info = _format_pois_as_attractions_info(combined)
    selected_pois = [{"name": p.name, "description": p.category or ""} for p in combined]

    return {
        "selected_pois": selected_pois,
        "attractions_info": attractions_info,
    }
```

**桥接函数 `_format_pois_as_attractions_info`**: 放在 `nodes/search.py` 内作为私有 helper（不对外暴露）。把 `CachedAttraction` 列表序列化成 `_extract_poi_names()` 能解析的形态（保留 `pois: [...]` 字典结构）。这样下游 `cluster_attractions` / `plan_route` 节点**不需要改**。

### 发现流程节点

`backend/app/agents/langgraph_agent/nodes/discovery.py`：

**改前**: `extract_attractions_expanded` + `geocode_dispatch` + `geocode_batch`（循环）

**改后**: 单节点 `search_attractions_discovery_node` 调 `service.get_attractions(city, min_count=40)`。

**保留 SSE 分批输出**: 节点内部把 service 返回的列表切成 `batch_size=10` 的批次，循环更新 `discovered_attractions`（`Annotated[list, operator.add]` 自动累加）。前端 SSE 接收行为保持不变。

图结构变化:
```
改前: extract_attractions_expanded → geocode_dispatch → geocode_batch(loop) → gather_discovery
改后: search_attractions_discovery (内部分批 yield)                       → gather_discovery
```

### 删除的代码

- `nodes/search.py`: `web_search_attractions_node`、`extract_attractions_node`、`geocode_attractions_node`、`_DDG_AVAILABLE` / `_BING_AVAILABLE` 守卫、`known_landmarks` 列表
- `nodes/discovery.py`: `extract_attractions_expanded_node`、`geocode_dispatch_node`、`geocode_batch_node`
- `state.py`: `raw_search_results` 字段、`_geocode_batches` 字段
- `requirements.txt`: `duckduckgo-search` 依赖

### 保留的代码

- `analyze_free_text()` — 解析自由文本里的偏好和必访景点
- `_extract_must_visit_attractions()` — 备用降级
- `services/bing_mcp_service.py` — 不删（防其他用途；本次不再被景点搜索引用）
- 所有下游 cluster / route / generate 节点 — 不动

## Admin 路由

新文件 `backend/app/api/routes/admin.py`：

```python
from fastapi import APIRouter, HTTPException
from ...services.attractions_cache_service import get_attractions_cache_service

router = APIRouter(prefix="/api/admin/attractions", tags=["admin"])

@router.post("/refresh")
async def refresh_city(city: str):
    if not city.strip():
        raise HTTPException(400, "city is required")
    count = await get_attractions_cache_service().refresh_city(city)
    return {"city": city, "refreshed": count}

@router.post("/clear")
async def clear_city(city: str):
    count = await get_attractions_cache_service().clear_city(city)
    return {"city": city, "cleared": count}

@router.get("/stats")
async def stats():
    return await get_attractions_cache_service().get_stats()
```

在 `api/main.py` 注册 `app.include_router(admin.router)`。**无认证**（与项目现状一致）。

## 错误处理

| 失败点 | 处理 |
|---|---|
| DB 读取失败 | log warning，service 视为 cache miss，走 AMap 路径；不抛 |
| DB 写入失败 | log warning；**不影响返回值**（节点照常拿到 AMap 结果）；下次重试写入 |
| AMap 单关键词失败 | 跳过，继续其他关键词；累计 5 个失败才抛 |
| AMap 全失败 + DB 为空 | service 抛 `NonRetryableError`；节点捕获写入 `errors`，下游用 `_create_fallback_plan` 降级 |
| AMap 返回坐标越界 | `_persist` 前过滤（73 < lon < 136, 3 < lat < 54，与 `_validate_plan_coordinates` 一致）；越界丢弃，其他正常入库 |
| `find_by_name` 单点查不到 | 返回 None；调用方决定是否在 must_visit 列表里跳过 |

**关键不变量**: service 自身的失败**不让节点崩**，最坏情况返回空列表 + errors，下游 fallback 接管。

## 测试策略

沿用项目现有 `pytest` + `unittest.mock` (`AsyncMock`/`MagicMock`) 风格。新增以下测试文件，具体测试条目以"覆盖关键行为"为准，不追求穷举：

### `tests/services/test_attractions_cache_service.py`（新增）

覆盖：
- Cache hit / miss / partial hit 三种主路径
- `categories` 过滤命中/不足时的两种行为
- Upsert 冲突时字段覆盖规则
- 坐标越界条目被丢弃但其他正常入库
- `find_by_name` 三种结果（DB 命中 / AMap 命中 / 都没有）
- `refresh_city` 替换全部
- AMap 部分/全部失败的差异化处理
- 类别映射函数（数据驱动 parametrize）

**Mock 策略**: DB 用内存 SQLite (`sqlite+aiosqlite:///:memory:`)，每个 fixture 重建；AMap MCP 用 `AsyncMock` patch `get_langchain_amap_service`。

### `tests/agents/test_search_attractions_node.py`（新增）

覆盖：
- 节点正常返回 `selected_pois` + `attractions_info`
- `free_text` 中必访景点出现在结果首部
- `preferences` 正确翻译为 `categories` 参数
- service 抛 `NonRetryableError` 时节点写入 errors 不崩

### `tests/agents/test_search_attractions_discovery_node.py`（新增）

覆盖：
- 返回的 `discovered_attractions` 数量与 service 一致
- service 被调用时 `min_count=40`

### `tests/api/test_admin_attractions.py`（新增）

覆盖三个路由的成功路径 + `refresh` 空 city 返回 400。

### 现有测试更新

`tests/agents/test_trip_planner.py` 里凡 mock DDG/Bing 的地方改为 mock `get_attractions_cache_service()`。预期断言（行程结构、字段完整性）不变。

### 不测试的部分

- 高德 MCP 真实调用（始终 mock）
- 真实 SQLite 文件（用内存 DB）
- 前端 SSE 接收行为（端到端范畴，超出本次范围）

## 风险与未知

1. **高德 `maps_text_search` 工具是否支持 `types` 参数** — MCP 封装层未必直通；备用方案是只用 `keywords` 多次拉取（本设计已假设此情况）。
2. **关键词列表能拉到多少个 POI** — 80 是预估上限；如果一二线大城市能轻松到 80，三四线小城市可能只有 30。这不影响正确性（min_count 触发再拉），但首次冷启动延迟会按城市变化。
3. **现有 `cluster_attractions` / `plan_route` 节点对 `attractions_info` 字符串格式的容忍度** — 桥接函数 `_format_pois_as_attractions_info` 需要在实现阶段对照 `_extract_poi_names` 来设计输出格式，可能需要小幅调整。

## 实施步骤大纲

详细 plan 由后续 `writing-plans` 步骤产出。粗略顺序：

1. ORM 模型 + `init_db` 验证
2. Service 层（含类别映射、AMap 拉取、upsert、`find_by_name`）
3. Service 层单测
4. 主流程节点替换 + 桥接函数 + 节点测试
5. 发现流程节点替换 + 测试
6. Admin 路由 + 测试
7. 删除旧代码 + 更新 requirements.txt
8. 现有 `test_trip_planner.py` 适配
9. 手动端到端验证（启动后端，跑一次主流程 + 一次发现流程）

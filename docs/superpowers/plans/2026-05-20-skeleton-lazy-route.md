# 骨架/详细分离 + 路线懒计算 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `planning_app` 一次性 LLM 编排拆成"骨架（候选池）→ 用户驱动装配 → 路线懒计算"两阶段，让用户的每次改动只触发一次轻量重算而不让 LLM 输出作废。

**Architecture:** 新增服务端 `trip_drafts` 表持久化半成品；骨架阶段只跑聚类 / 候选池 / macro_planner；详细阶段改为 REST 端点 + 规则装配时间轴 + amap 路线 + 单独 LLM 写文案；用户显式 finalize 才转 `trip_history`。

**Tech Stack:** FastAPI + SQLAlchemy 2.x async + aiosqlite + LangGraph + Pydantic v2 + Vue 3 + Ant Design Vue + 高德 MCP

**Spec:** `docs/superpowers/specs/2026-05-20-skeleton-lazy-route-design.md`

---

## 文件结构地图

```
backend/
├── app/
│   ├── models/
│   │   ├── schemas.py             ← 扩展：DiningCategory 等 + Meal.category
│   │   └── db_models.py           ← 扩展：TripDraft ORM
│   ├── services/
│   │   └── trip_draft_service.py  ← 新增：CRUD + patch + TTL
│   ├── agents/langgraph_agent/
│   │   ├── graph.py               ← 改造：create_planning_graph 缩为骨架图
│   │   ├── nodes/
│   │   │   ├── food.py            ← 扩展：search_dining_pool_node
│   │   │   └── draft.py           ← 新增：save_draft_node
│   │   ├── assemble/              ← 新目录
│   │   │   ├── __init__.py
│   │   │   ├── timeline.py        ← rule_assemble_day_timeline
│   │   │   ├── route.py           ← compute_day_route
│   │   │   ├── budget.py          ← compute_day_budget
│   │   │   └── narrative.py       ← write_day_narrative_llm
│   │   └── finalize/              ← 新目录
│   │       ├── __init__.py
│   │       └── pipeline.py        ← finalize_draft
│   └── api/
│       ├── main.py                ← 注册 trip_draft 路由 + 启动 TTL 任务
│       └── routes/
│           └── trip_draft.py      ← 新增：所有 /api/trip/draft/* 端点
└── tests/
    ├── services/
    │   └── test_trip_draft_service.py
    ├── agents/
    │   ├── test_search_dining_pool.py
    │   ├── test_rule_assemble_timeline.py
    │   ├── test_compute_day_budget.py
    │   └── test_finalize_pipeline.py
    └── api/
        └── test_draft_endpoints.py

frontend/
└── src/
    ├── services/api.ts            ← 扩展：draft 系列方法
    ├── main.ts                    ← 注册 /draft/:id 路由
    ├── views/
    │   ├── DiscoverView.vue       ← 改造：调新端点 + 跳 /draft/:id
    │   └── DraftView.vue          ← 新增：装配器主页
    └── components/draft/          ← 新目录
        ├── DraftHero.vue
        ├── DayCard.vue
        ├── DayTimeline.vue
        └── AddDiningPopover.vue
```

---

## Phase 1：数据模型与持久化

### Task 1：扩展 Pydantic schemas（餐饮类别 + 草稿载荷模型）

**Files:**
- Modify: `backend/app/models/schemas.py`

- [ ] **Step 1：在 `schemas.py` 顶部新增 `Enum` 导入**

`schemas.py` 第 3 行附近添加：
```python
from enum import Enum
```

- [ ] **Step 2：在 `Meal` 模型定义前新增 DiningCategory 和候选池模型**

在 `class Meal(BaseModel):` 上方添加：
```python
class DiningCategory(str, Enum):
    """用餐类别（多类别候选池）"""
    MAIN = "main"           # 正餐
    SNACK = "snack"         # 小吃
    DESSERT = "dessert"     # 甜品
    CAFE = "cafe"           # 咖啡
    LATE_NIGHT = "late_night"  # 夜宵


class DiningCandidate(BaseModel):
    """候选池中的单个餐饮项"""
    name: str = Field(..., description="餐厅名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Location] = Field(default=None, description="坐标")
    category: DiningCategory = Field(..., description="餐饮类别")
    cuisine: Optional[str] = Field(default=None, description="菜系")
    rating: Optional[float] = Field(default=None, description="评分")
    avg_cost: Optional[int] = Field(default=None, description="人均消费")
    distance: Optional[str] = Field(default=None, description="距景点中心距离")
    open_hours: Optional[str] = Field(default=None, description="营业时间")
    tel: Optional[str] = Field(default=None, description="联系电话")
    poi_id: Optional[str] = Field(default=None, description="POI ID")
    source: str = Field(default="nearby", description="来源: nearby/popular/user_custom")


class DiningPoolDay(BaseModel):
    """每日多类别餐饮候选池"""
    main: List[DiningCandidate] = Field(default_factory=list)
    snack: List[DiningCandidate] = Field(default_factory=list)
    dessert: List[DiningCandidate] = Field(default_factory=list)
    cafe: List[DiningCandidate] = Field(default_factory=list)
    late_night: List[DiningCandidate] = Field(default_factory=list)
```

- [ ] **Step 3：扩展 `Meal` 模型新增 `category` 字段（保留 `type` 向后兼容）**

把现有的 `Meal` 模型 `type` 字段下面（约第 114 行后）添加：
```python
    category: Optional[DiningCategory] = Field(
        default=None,
        description="餐饮类别（新版本主用此字段，type 保留向后兼容）"
    )
```

- [ ] **Step 4：在文件末尾新增草稿载荷模型**

在 `class ErrorResponse(BaseModel):` 定义之前追加：
```python
class DraftDayContext(BaseModel):
    """骨架阶段每日上下文"""
    day_index: int = Field(..., description="第几天(从0开始)")
    date: str = Field(..., description="日期 YYYY-MM-DD")
    attraction_names: List[str] = Field(default_factory=list)
    attractions: List[Attraction] = Field(default_factory=list)
    hotel: Optional[Hotel] = Field(default=None)
    dining_pool: DiningPoolDay = Field(default_factory=DiningPoolDay)
    weather: Optional[WeatherInfo] = Field(default=None)


class DayDetail(BaseModel):
    """详细阶段产物（每日装配后的完整时间轴）"""
    day_index: int
    date: str
    description: str = Field(default="", description="LLM 写的当日叙述")
    attractions: List[Attraction] = Field(default_factory=list)
    hotel: Optional[Hotel] = Field(default=None)
    meals: List[Meal] = Field(default_factory=list)
    route_segments: List[RouteSegment] = Field(default_factory=list)
    timeline_order: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[{kind:'attraction|meal|hotel', ref_name:'...'}]"
    )
    day_budget: Optional[Budget] = Field(default=None, description="当日预算")
    is_assembled: bool = Field(default=False)


class TripDraftPayload(BaseModel):
    """草稿完整载荷（GET /draft/{id} 返回）"""
    draft_id: str
    status: str = Field(..., description="skeleton/assembling/finalized/expired")
    request: TripRequest
    city: str
    macro_plan: MacroPlan
    days: List[DraftDayContext]
    days_detail: List[Optional[DayDetail]]
    weather_info: List[WeatherInfo] = Field(default_factory=list)
    created_at: str
    updated_at: str


class DayEditRequest(BaseModel):
    """所有用户编辑端点共享的请求模型 (/recompute /assemble force)"""
    attractions_order: Optional[List[str]] = Field(
        default=None,
        description="按用户拖拽后的景点名顺序；不传则保留当前 day_detail.attractions 顺序"
    )
    meals: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="用户当前勾选的餐饮（完整状态，不是 patch）"
                    "；不传则保留 day_detail.meals；传 [] 则清空"
    )


class AIRearrangeRequest(BaseModel):
    """AI 重新安排请求"""
    hint: Optional[str] = Field(default=None, description="给 LLM 的额外提示")


class FinalizeResponse(BaseModel):
    """SSE 流的 complete 事件载荷"""
    type: str = Field(default="complete")
    trip_id: int
    trip_plan: TripPlan
```

- [ ] **Step 5：写一个 schema 合法性测试**

新建 `backend/tests/models/__init__.py`（空文件）和 `backend/tests/models/test_draft_schemas.py`：
```python
from app.models.schemas import (
    DiningCategory, DiningCandidate, DiningPoolDay,
    DayDetail, TripDraftPayload, DayEditRequest, Meal,
    Location, MacroPlan, DaySkeleton, TripRequest, Attraction,
)


def test_dining_category_enum_values():
    assert DiningCategory.MAIN == "main"
    assert DiningCategory.LATE_NIGHT == "late_night"
    assert {c.value for c in DiningCategory} == {
        "main", "snack", "dessert", "cafe", "late_night"
    }


def test_dining_pool_day_default_empty():
    pool = DiningPoolDay()
    assert pool.main == []
    assert pool.late_night == []


def test_dining_candidate_requires_category():
    cand = DiningCandidate(name="某餐厅", category=DiningCategory.MAIN)
    assert cand.category == DiningCategory.MAIN
    assert cand.source == "nearby"


def test_day_detail_defaults():
    dd = DayDetail(day_index=0, date="2026-06-01")
    assert dd.is_assembled is False
    assert dd.meals == []
    assert dd.day_budget is None


def test_meal_category_backward_compat():
    # 旧入参：只有 type，没有 category
    m1 = Meal(type="breakfast", name="某餐厅")
    assert m1.category is None
    # 新入参：含 category
    m2 = Meal(type="main", name="某餐厅", category=DiningCategory.MAIN)
    assert m2.category == DiningCategory.MAIN


def test_day_edit_request_field_omission_semantics():
    """不传 meals 与传空数组是两种意图"""
    r1 = DayEditRequest()
    assert r1.meals is None  # 保留当前
    r2 = DayEditRequest(meals=[])
    assert r2.meals == []    # 清空
```

- [ ] **Step 6：跑测试**

```bash
cd backend && pytest tests/models/test_draft_schemas.py -v
```
预期：6 个测试全部 PASS。

- [ ] **Step 7：提交**

```bash
git add backend/app/models/schemas.py backend/tests/models/
git commit -m "feat(schemas): 添加 DiningCategory 和草稿载荷模型

新增 DiningCategory/DiningCandidate/DiningPoolDay/DraftDayContext/
DayDetail/TripDraftPayload/DayEditRequest/AIRearrangeRequest 等
模型用于骨架/详细分离架构。Meal 模型新增 category 字段保持向后兼容。"
```

---

### Task 2：新增 `TripDraft` ORM 模型

**Files:**
- Modify: `backend/app/models/db_models.py`

- [ ] **Step 1：在 `db_models.py` 文件末尾追加 `TripDraft` 模型**

```python
class TripDraft(Base):
    """草稿表：保存骨架阶段产物 + 详细阶段渐进装配的每日 DayDetail"""
    __tablename__ = "trip_drafts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # uuid4 hex
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="skeleton")
    # skeleton / assembling / finalized / expired

    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    selected_attractions_json: Mapped[str] = mapped_column(Text, nullable=False)

    macro_plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    clusters_data_json: Mapped[str] = mapped_column(Text, nullable=False)
    hotels_by_day_json: Mapped[str] = mapped_column(Text, nullable=False)
    dining_pool_json: Mapped[str] = mapped_column(Text, nullable=False)
    weather_info_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    days_detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    trip_tagline: Mapped[str] = mapped_column(String(200), default="")
    overall_suggestions: Mapped[str] = mapped_column(Text, default="")
    weather_summary: Mapped[str] = mapped_column(String(200), default="")

    finalized_trip_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_drafts_user_status", "user_id", "status"),
        Index("idx_drafts_updated", "updated_at"),
    )
```

- [ ] **Step 2：写一个集成测试验证表会被 `init_db` 建出来**

新建 `backend/tests/services/__init__.py`（空文件）和 `backend/tests/services/test_trip_draft_orm.py`：
```python
import pytest
from sqlalchemy import inspect

from app.database import engine, init_db
from app.models.db_models import TripDraft


@pytest.mark.asyncio
async def test_trip_draft_table_created_by_init_db():
    await init_db()
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "trip_drafts" in tables


@pytest.mark.asyncio
async def test_trip_draft_columns_match_orm():
    async with engine.connect() as conn:
        columns = await conn.run_sync(lambda c: inspect(c).get_columns("trip_drafts"))
    col_names = {c["name"] for c in columns}
    expected = {
        "id", "user_id", "status",
        "request_json", "selected_attractions_json",
        "macro_plan_json", "clusters_data_json",
        "hotels_by_day_json", "dining_pool_json",
        "weather_info_json", "days_detail_json",
        "trip_tagline", "overall_suggestions", "weather_summary",
        "finalized_trip_id",
        "created_at", "updated_at", "finalized_at",
    }
    assert expected.issubset(col_names), f"缺字段: {expected - col_names}"
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/services/test_trip_draft_orm.py -v
```
预期：2 个测试 PASS。

- [ ] **Step 4：提交**

```bash
git add backend/app/models/db_models.py backend/tests/services/
git commit -m "feat(db): 添加 TripDraft ORM 模型用于草稿持久化"
```

---

### Task 3：`trip_draft_service` CRUD + 部分字段 patch + TTL 清理

**Files:**
- Create: `backend/app/services/trip_draft_service.py`
- Test: `backend/tests/services/test_trip_draft_service.py`

- [ ] **Step 1：写失败测试 — create / get / list_for_user**

`backend/tests/services/test_trip_draft_service.py`：
```python
import json
import pytest
from datetime import datetime, timedelta

from app.database import init_db, async_session
from app.models.db_models import TripDraft
from app.services import trip_draft_service as svc
from app.models.schemas import (
    TripRequest, MacroPlan, DaySkeleton, DayDetail,
)


@pytest.fixture
async def _db():
    await init_db()
    # 清理表，避免上次失败残留
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(TripDraft))
        await session.commit()
    yield


def _sample_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-03",
        travel_days=3, transportation="公共交通", accommodation="经济型酒店",
    )


def _sample_macro_plan():
    return MacroPlan(
        city="北京", total_days=3,
        days=[
            DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["故宫"]),
            DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["颐和园"]),
            DaySkeleton(day_index=2, date="2026-06-03", attraction_names=["天坛"]),
        ],
    )


@pytest.mark.asyncio
async def test_create_draft_returns_id_and_persists(_db):
    draft_id = await svc.create_draft(
        user_id="u1",
        request=_sample_request(),
        selected_attractions=[],
        macro_plan=_sample_macro_plan(),
        clusters_data=[],
        hotels_by_day=[],
        dining_pool=[],
        weather_info=[],
    )
    assert draft_id and isinstance(draft_id, str)
    got = await svc.get_draft(draft_id)
    assert got is not None
    assert got.status == "skeleton"
    assert got.user_id == "u1"
    assert len(json.loads(got.days_detail_json)) == 3  # 与 travel_days 等长，全为 null


@pytest.mark.asyncio
async def test_get_draft_returns_none_for_unknown(_db):
    assert await svc.get_draft("not-exist") is None


@pytest.mark.asyncio
async def test_patch_day_detail_replaces_specific_index(_db):
    draft_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    new_detail = DayDetail(day_index=1, date="2026-06-02", is_assembled=True)
    await svc.patch_day_detail(draft_id, day_index=1, day_detail=new_detail)
    got = await svc.get_draft(draft_id)
    days = json.loads(got.days_detail_json)
    assert days[0] is None
    assert days[1] is not None and days[1]["is_assembled"] is True
    assert days[2] is None


@pytest.mark.asyncio
async def test_mark_finalized_sets_status_and_trip_id(_db):
    draft_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    await svc.mark_finalized(draft_id, trip_id=42)
    got = await svc.get_draft(draft_id)
    assert got.status == "finalized"
    assert got.finalized_trip_id == 42
    assert got.finalized_at is not None


@pytest.mark.asyncio
async def test_delete_draft_removes_record(_db):
    draft_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    deleted = await svc.delete_draft(draft_id)
    assert deleted is True
    assert await svc.get_draft(draft_id) is None
    # 再删一次返回 False
    assert await svc.delete_draft(draft_id) is False


@pytest.mark.asyncio
async def test_delete_expired_only_removes_old_non_finalized(_db):
    # 旧的 skeleton：会删
    old_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    # 手动改 updated_at 到 60 天前
    async with async_session() as session:
        record = await session.get(TripDraft, old_id)
        record.updated_at = datetime.utcnow() - timedelta(days=60)
        await session.commit()
    # 新的 skeleton：不删
    fresh_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    # 旧的 finalized：不删
    finalized_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    await svc.mark_finalized(finalized_id, trip_id=99)
    async with async_session() as session:
        record = await session.get(TripDraft, finalized_id)
        record.updated_at = datetime.utcnow() - timedelta(days=60)
        await session.commit()

    deleted_count = await svc.delete_expired(days=30)
    assert deleted_count == 1
    assert await svc.get_draft(old_id) is None
    assert await svc.get_draft(fresh_id) is not None
    assert await svc.get_draft(finalized_id) is not None
```

- [ ] **Step 2：跑测试，确认全部 FAIL（模块不存在）**

```bash
cd backend && pytest tests/services/test_trip_draft_service.py -v
```
预期：ModuleNotFoundError 或所有测试 FAIL。

- [ ] **Step 3：实现 `trip_draft_service.py`**

`backend/app/services/trip_draft_service.py`：
```python
"""草稿 CRUD 服务"""
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models.db_models import TripDraft
from ..models.schemas import (
    TripRequest, MacroPlan, DayDetail, DiscoveredAttraction,
    DiningPoolDay, WeatherInfo,
)
from ..logger import get_logger

logger = get_logger(__name__)


def _dump_pydantic_list(items: List[Any]) -> str:
    """把 List[BaseModel] 或 List[dict] 序列化为 JSON 文本"""
    out = []
    for it in items:
        if hasattr(it, "model_dump"):
            out.append(it.model_dump(mode="json"))
        elif hasattr(it, "dict"):
            out.append(it.dict())
        else:
            out.append(it)
    return json.dumps(out, ensure_ascii=False, default=str)


async def create_draft(
    *,
    user_id: str,
    request: TripRequest,
    selected_attractions: List[Any],
    macro_plan: MacroPlan,
    clusters_data: List[Any],
    hotels_by_day: List[Any],
    dining_pool: List[DiningPoolDay] | List[dict],
    weather_info: List[WeatherInfo] | List[dict],
) -> str:
    draft_id = uuid.uuid4().hex
    travel_days = request.travel_days
    days_detail_init = [None] * travel_days

    record = TripDraft(
        id=draft_id,
        user_id=user_id,
        status="skeleton",
        request_json=request.model_dump_json(),
        selected_attractions_json=_dump_pydantic_list(selected_attractions),
        macro_plan_json=macro_plan.model_dump_json(),
        clusters_data_json=json.dumps(clusters_data, ensure_ascii=False, default=str),
        hotels_by_day_json=json.dumps(hotels_by_day, ensure_ascii=False, default=str),
        dining_pool_json=_dump_pydantic_list(dining_pool),
        weather_info_json=_dump_pydantic_list(weather_info),
        days_detail_json=json.dumps(days_detail_init),
    )
    async with async_session() as session:
        session.add(record)
        await session.commit()
    logger.info(f"草稿已创建: id={draft_id}, user={user_id}, days={travel_days}")
    return draft_id


async def get_draft(draft_id: str) -> Optional[TripDraft]:
    async with async_session() as session:
        return await session.get(TripDraft, draft_id)


async def patch_day_detail(
    draft_id: str, day_index: int, day_detail: DayDetail
) -> None:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        days = json.loads(record.days_detail_json)
        if day_index < 0 or day_index >= len(days):
            raise IndexError(f"day_index {day_index} out of range (len={len(days)})")
        days[day_index] = day_detail.model_dump(mode="json")
        record.days_detail_json = json.dumps(days, ensure_ascii=False, default=str)
        await session.commit()


async def update_synthesizer_fields(
    draft_id: str, *, trip_tagline: str, overall_suggestions: str, weather_summary: str
) -> None:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        record.trip_tagline = trip_tagline
        record.overall_suggestions = overall_suggestions
        record.weather_summary = weather_summary
        await session.commit()


async def mark_finalized(draft_id: str, *, trip_id: int) -> None:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        record.status = "finalized"
        record.finalized_trip_id = trip_id
        record.finalized_at = datetime.utcnow()
        await session.commit()


async def delete_draft(draft_id: str) -> bool:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            return False
        await session.delete(record)
        await session.commit()
        return True


async def delete_expired(*, days: int = 30) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session() as session:
        stmt = (
            delete(TripDraft)
            .where(TripDraft.updated_at < cutoff)
            .where(TripDraft.status != "finalized")
        )
        result = await session.execute(stmt)
        await session.commit()
        deleted = result.rowcount or 0
        if deleted > 0:
            logger.info(f"TTL 清理: 删除了 {deleted} 个过期草稿")
        return deleted
```

- [ ] **Step 4：跑测试，确认全部 PASS**

```bash
cd backend && pytest tests/services/test_trip_draft_service.py -v
```
预期：6 个测试全部 PASS。

- [ ] **Step 5：提交**

```bash
git add backend/app/services/trip_draft_service.py backend/tests/services/test_trip_draft_service.py
git commit -m "feat(service): 添加 trip_draft_service（CRUD + day_detail patch + TTL 清理）"
```

---

## Phase 2：骨架阶段（多类别餐饮候选池 + 骨架图）

### Task 4：`search_dining_pool_node` —— 按 5 类并发搜索

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/food.py`
- Test: `backend/tests/agents/test_search_dining_pool.py`

- [ ] **Step 1：写失败测试**

`backend/tests/agents/test_search_dining_pool.py`：
```python
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.nodes.food import search_dining_pool_node
from app.models.schemas import DiningCategory, TripRequest


def _make_state(travel_days=2, clusters=None, attractions_info=""):
    return {
        "request": TripRequest(
            city="北京", start_date="2026-06-01", end_date="2026-06-02",
            travel_days=travel_days, transportation="公共交通",
            accommodation="经济型酒店",
        ),
        "clusters_data": clusters or [],
        "attractions_info": attractions_info,
    }


@pytest.mark.asyncio
async def test_returns_one_pool_per_day():
    state = _make_state(
        travel_days=2,
        clusters=[
            [{"name": "故宫", "longitude": 116.397, "latitude": 39.916}],
            [{"name": "颐和园", "longitude": 116.273, "latitude": 39.999}],
        ],
    )

    fake_poi = AsyncMock(return_value=[
        {"name": "某餐厅", "address": "...", "longitude": 116.4, "latitude": 39.9,
         "rating": 4.5, "avg_cost": 80}
    ])
    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=fake_poi):
        result = await search_dining_pool_node(state)

    pools = result["dining_pool"]
    assert len(pools) == 2
    for p in pools:
        assert isinstance(p, dict)
        assert {"main", "snack", "dessert", "cafe", "late_night"}.issubset(p.keys())


@pytest.mark.asyncio
async def test_failure_in_one_category_does_not_break_others():
    """某一类失败应返回 []，不影响其他类别"""
    state = _make_state(
        travel_days=1,
        clusters=[[{"name": "天坛", "longitude": 116.41, "latitude": 39.88}]],
    )

    async def fake_search(category, center, city):
        if category == DiningCategory.LATE_NIGHT:
            raise RuntimeError("amap 暂时挂了")
        return [{"name": f"{category.value}餐厅", "longitude": 116.41,
                 "latitude": 39.88, "rating": 4.0}]

    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=fake_search):
        result = await search_dining_pool_node(state)

    pool = result["dining_pool"][0]
    assert pool["main"] and pool["snack"] and pool["dessert"] and pool["cafe"]
    assert pool["late_night"] == []


@pytest.mark.asyncio
async def test_no_coordinates_falls_back_to_city_search():
    """当日聚类全部无坐标时，应走城市级文本搜索（不带 location）"""
    state = _make_state(
        travel_days=1,
        clusters=[[{"name": "未知景点", "longitude": 0, "latitude": 0}]],
    )

    called_with = []

    async def capture(category, center, city):
        called_with.append((category.value, center, city))
        return []

    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=capture):
        await search_dining_pool_node(state)

    # 无效坐标 (0,0) 应被识别为 "无中心"，center=None
    for _, center, city in called_with:
        assert center is None
        assert city == "北京"
```

- [ ] **Step 2：在 `food.py` 顶部新增导入**

```python
from ....models.schemas import DiningCategory
```

- [ ] **Step 3：在 `food.py` 文件末尾追加新节点实现**

```python
# ============ 多类别餐饮候选池（骨架阶段） ============

_DINING_KEYWORDS = {
    DiningCategory.MAIN: ("餐厅 美食", 6),
    DiningCategory.SNACK: ("小吃 街边小吃", 4),
    DiningCategory.DESSERT: ("甜品 蛋糕 茶饮", 4),
    DiningCategory.CAFE: ("咖啡馆", 4),
    DiningCategory.LATE_NIGHT: ("夜宵 烧烤 大排档", 4),
}


def _day_center(day_cluster: List[Dict[str, Any]]) -> Optional[tuple[float, float]]:
    """计算当日景点经纬度算术平均；无有效坐标返回 None"""
    coords = [
        (c["longitude"], c["latitude"])
        for c in (day_cluster or [])
        if isinstance(c.get("longitude"), (int, float))
        and isinstance(c.get("latitude"), (int, float))
        and 73 < c["longitude"] < 136 and 3 < c["latitude"] < 54
    ]
    if not coords:
        return None
    return (
        sum(x for x, _ in coords) / len(coords),
        sum(y for _, y in coords) / len(coords),
    )


async def _search_dining_category(
    category: DiningCategory,
    center: Optional[tuple[float, float]],
    city: str,
) -> List[Dict[str, Any]]:
    """跑一次 amap POI 搜索；center 为 None 时走城市文本搜索"""
    keyword, _top_n = _DINING_KEYWORDS[category]
    service = get_langchain_amap_service()

    if center is not None:
        tool = await service.get_tool("maps_around_search")
        if tool is None:
            return []
        try:
            raw = await _invoke_tool_with_retry(
                tool,
                {"keywords": keyword, "location": f"{center[0]},{center[1]}", "radius": "1500"},
                max_retries=1, per_attempt_timeout=15.0,
            )
        except Exception as e:
            print(f" ⚠️ dining[{category.value}] around 失败: {str(e)[:80]}")
            return []
    else:
        tool = await service.get_tool("maps_text_search")
        if tool is None:
            return []
        try:
            raw = await _invoke_tool_with_retry(
                tool, {"keywords": keyword, "city": city},
                max_retries=1, per_attempt_timeout=15.0,
            )
        except Exception as e:
            print(f" ⚠️ dining[{category.value}] text 失败: {str(e)[:80]}")
            return []

    return _parse_amap_poi_list(raw)


def _poi_to_dining_candidate(
    p: Dict[str, Any], category: DiningCategory, source: str
) -> Dict[str, Any]:
    """把 _parse_amap_poi_list 的 POI dict 转成 DiningCandidate dict"""
    cand: Dict[str, Any] = {
        "name": p.get("name", ""),
        "category": category.value,
        "source": source,
    }
    if p.get("address"):
        cand["address"] = p["address"]
    if p.get("longitude") and p.get("latitude"):
        cand["location"] = {"longitude": p["longitude"], "latitude": p["latitude"]}
    if p.get("rating") is not None:
        cand["rating"] = round(float(p["rating"]), 2)
    if p.get("avg_cost") is not None:
        cand["avg_cost"] = int(p["avg_cost"])
    if p.get("open_hours"):
        cand["open_hours"] = p["open_hours"]
    if p.get("tel"):
        cand["tel"] = p["tel"]
    if p.get("poi_id"):
        cand["poi_id"] = p["poi_id"]
    cuisine_tag = (p.get("type") or "").split(";")[0].strip()
    if cuisine_tag:
        cand["cuisine"] = cuisine_tag
    return cand


async def search_dining_pool_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """骨架阶段：按 5 类并发搜索每日餐饮候选池，返回 List[DiningPoolDay-shape dict]"""
    print("🍴 执行节点: search_dining_pool_node")
    request = state["request"]
    clusters_data: List[List[Dict[str, Any]]] = state.get("clusters_data", []) or []
    travel_days = request.travel_days

    while len(clusters_data) < travel_days:
        clusters_data.append([])

    pools: List[Dict[str, Any]] = []
    for day_idx in range(travel_days):
        day_cluster = clusters_data[day_idx] if day_idx < len(clusters_data) else []
        center = _day_center(day_cluster)
        source = "nearby" if center is not None else "popular"

        tasks = [
            _search_dining_category(cat, center, request.city)
            for cat in DiningCategory
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        pool: Dict[str, List[Dict[str, Any]]] = {}
        for cat, res in zip(DiningCategory, results):
            if isinstance(res, Exception):
                print(f" ⚠️ dining[{cat.value}] 异常: {res}")
                pool[cat.value] = []
                continue
            _, top_n = _DINING_KEYWORDS[cat]
            ranked = _rank_food_pois(res, None, None, set(), top_n=top_n)
            pool[cat.value] = [
                _poi_to_dining_candidate(p, cat, source) for p in ranked
            ]
        pools.append(pool)
        total = sum(len(v) for v in pool.values())
        print(f" ✅ 第{day_idx + 1}天餐饮候选池: 共 {total} 家")

    return {"dining_pool": pools}
```

- [ ] **Step 4：跑测试**

```bash
cd backend && pytest tests/agents/test_search_dining_pool.py -v
```
预期：3 个测试 PASS。

- [ ] **Step 5：提交**

```bash
git add backend/app/agents/langgraph_agent/nodes/food.py backend/tests/agents/test_search_dining_pool.py
git commit -m "feat(graph): 添加 search_dining_pool_node 按 5 类并发搜索餐饮候选池"
```

---

### Task 5：`save_draft_node` + 骨架图重构

**Files:**
- Create: `backend/app/agents/langgraph_agent/nodes/draft.py`
- Modify: `backend/app/agents/langgraph_agent/state.py`
- Modify: `backend/app/agents/langgraph_agent/nodes/__init__.py`
- Modify: `backend/app/agents/langgraph_agent/graph.py`

- [ ] **Step 1：扩展 `TripPlannerState` 加入 `dining_pool` 和 `draft_id` 字段**

`backend/app/agents/langgraph_agent/state.py`：找到 `TripPlannerState` TypedDict，添加：
```python
    dining_pool: List[Dict[str, Any]]   # 每日 DiningPoolDay-shape dict 列表（骨架阶段产物）
    draft_id: Optional[str]              # save_draft_node 写入的草稿 ID
```

- [ ] **Step 2：实现 `save_draft_node`**

`backend/app/agents/langgraph_agent/nodes/draft.py`：
```python
"""草稿写入节点（骨架图的最后一站）"""
from typing import Dict, Any, List

from ..state import TripPlannerState
from ....services import trip_draft_service
from ....models.schemas import WeatherInfo


async def save_draft_node(state: TripPlannerState) -> Dict[str, Any]:
    print("💾 执行节点: save_draft_node")
    request = state["request"]
    user_id = state.get("user_id", "default")
    macro_plan = state.get("macro_plan")
    if macro_plan is None:
        raise RuntimeError("save_draft_node: macro_plan 缺失，无法保存草稿")

    # 把 weather_info（可能是字符串/列表）规范化为 List[WeatherInfo] dict
    weather_info_raw = state.get("weather_info", "")
    weather_list: List[Dict[str, Any]] = []
    if isinstance(weather_info_raw, list):
        for w in weather_info_raw:
            if isinstance(w, WeatherInfo):
                weather_list.append(w.model_dump(mode="json"))
            elif isinstance(w, dict):
                weather_list.append(w)

    draft_id = await trip_draft_service.create_draft(
        user_id=user_id,
        request=request,
        selected_attractions=state.get("user_selected_attractions", []) or [],
        macro_plan=macro_plan,
        clusters_data=state.get("clusters_data", []) or [],
        hotels_by_day=state.get("hotels_by_day", []) or [],
        dining_pool=state.get("dining_pool", []) or [],
        weather_info=weather_list,
    )
    print(f"✅ 草稿已保存: draft_id={draft_id}")
    return {"draft_id": draft_id}
```

- [ ] **Step 3：在 `nodes/__init__.py` 中导出新节点**

打开 `backend/app/agents/langgraph_agent/nodes/__init__.py`，添加：
```python
from .food import search_dining_pool_node
from .draft import save_draft_node
```

并把这两个名字加到 `__all__` 列表里（如果存在）。

- [ ] **Step 4：改造 `create_planning_graph()` 为骨架图**

`backend/app/agents/langgraph_agent/graph.py`：替换 `create_planning_graph` 函数体为：
```python
def create_planning_graph():
    """骨架图：cluster_from_selections → 候选池/酒店搜索 → macro_planner → save_draft

    详细阶段（day_plan_subgraph、reduce_assemble、global_synthesizer、
    extract_preferences）不再在此图中执行，改由 API 端点和 finalize 流程触发。
    """
    from langgraph.types import RetryPolicy

    workflow = StateGraph(TripPlannerState)

    search_retry = RetryPolicy(
        max_attempts=2,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=lambda e: isinstance(e, RetryableError),
    )

    workflow.add_node("load_user_preferences", load_user_preferences_node)
    workflow.add_node("cluster_from_selections", cluster_from_selections_node)
    workflow.add_node("search_dining_pool", search_dining_pool_node)
    workflow.add_node("search_hotels_by_day", search_hotels_by_day_node, retry=search_retry)
    workflow.add_node("macro_planner", macro_planner_node)
    workflow.add_node("save_draft", save_draft_node)

    workflow.add_edge(START, "load_user_preferences")
    workflow.add_edge("load_user_preferences", "cluster_from_selections")
    workflow.add_edge("cluster_from_selections", "search_dining_pool")
    workflow.add_edge("cluster_from_selections", "search_hotels_by_day")
    workflow.add_edge(["search_dining_pool", "search_hotels_by_day"], "macro_planner")
    workflow.add_edge("macro_planner", "save_draft")
    workflow.add_edge("save_draft", END)

    return workflow.compile()
```

并在文件顶部 import 区域加入：
```python
    search_dining_pool_node,
    save_draft_node,
```
（追加到现有的 `from .nodes import (...)` 语句内）

- [ ] **Step 5：更新 `_build_planning_state` 初始化 `dining_pool` 和 `draft_id`**

在 `LangGraphTripPlanner._build_planning_state` 中，调用 `_build_initial_state` 之后追加：
```python
        state["dining_pool"] = []
        state["draft_id"] = None
        return state
```

同样在 `_build_initial_state` 末尾加入：
```python
            "dining_pool": [],
            "draft_id": None,
```

- [ ] **Step 6：写集成测试验证骨架图能完整跑通并写出 draft_id（用 mock 跳过 amap/LLM）**

`backend/tests/agents/test_skeleton_graph.py`：
```python
from unittest.mock import patch, AsyncMock

import pytest

from app.agents.langgraph_agent.graph import create_planning_graph
from app.database import init_db
from app.services import trip_draft_service
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton


@pytest.mark.asyncio
async def test_skeleton_graph_runs_and_persists_draft():
    await init_db()

    request = TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )

    initial_state = {
        "request": request,
        "user_id": "test_user",
        "user_selected_attractions": [
            {"name": "故宫", "location": {"longitude": 116.397, "latitude": 39.916}},
            {"name": "颐和园", "location": {"longitude": 116.273, "latitude": 39.999}},
        ],
        "user_day_assignments": None,
        "user_preferences": None,
        "attractions_info": "",
        "weather_info": "",
        "hotels_info": "",
        "food_info": "",
        "cluster_info": "",
        "route_info": "",
        "trip_plan": None,
        "errors": [],
        "messages": [],
        "extracted_preferences": None,
        "macro_plan": None,
        "day_plans": [],
        "global_narrative": None,
        "clusters_data": [],
        "hotels_by_day": [],
        "selected_pois": [],
        "selected_hotels": [],
        "aigohotel_raw_results": "",
        "dining_pool": [],
        "draft_id": None,
    }

    with patch(
        "app.agents.langgraph_agent.nodes.draft.trip_draft_service.create_draft",
        new=AsyncMock(return_value="draft_xyz"),
    ), patch(
        "app.agents.langgraph_agent.nodes.food._search_dining_category",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.agents.langgraph_agent.nodes.search.search_hotels_by_day_node",
        new=AsyncMock(return_value={"hotels_by_day": [[], []], "hotels_info": ""}),
    ), patch(
        "app.agents.langgraph_agent.nodes.generate.macro_planner_node",
        new=AsyncMock(return_value={"macro_plan": MacroPlan(
            city="北京", total_days=2,
            days=[
                DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["故宫"]),
                DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["颐和园"]),
            ],
        )}),
    ), patch(
        "app.agents.langgraph_agent.nodes.preferences.load_user_preferences_node",
        new=AsyncMock(return_value={"user_preferences": None}),
    ):
        app = create_planning_graph()
        final = await app.ainvoke(initial_state)

    assert final["draft_id"] == "draft_xyz"
    assert final.get("macro_plan") is not None
```

- [ ] **Step 7：跑测试**

```bash
cd backend && pytest tests/agents/test_skeleton_graph.py -v
```
预期：1 个测试 PASS。

- [ ] **Step 8：提交**

```bash
git add backend/app/agents/langgraph_agent/state.py \
       backend/app/agents/langgraph_agent/nodes/draft.py \
       backend/app/agents/langgraph_agent/nodes/__init__.py \
       backend/app/agents/langgraph_agent/graph.py \
       backend/tests/agents/test_skeleton_graph.py
git commit -m "refactor(graph): 把 create_planning_graph 缩为骨架图，新增 save_draft_node

骨架图：load_user_preferences → cluster_from_selections →
(search_dining_pool || search_hotels_by_day) → macro_planner → save_draft → END

day_plan_subgraph / reduce_assemble / global_synthesizer / extract_preferences
不再在骨架图里跑，改由后续 API 端点和 finalize 流程触发。"
```

---

## Phase 3：装配（规则装配 + 路线 + 预算 + 文案）

### Task 6：`rule_assemble_day_timeline` —— 规则装配时间轴

**Files:**
- Create: `backend/app/agents/langgraph_agent/assemble/__init__.py` (空文件)
- Create: `backend/app/agents/langgraph_agent/assemble/timeline.py`
- Test: `backend/tests/agents/test_rule_assemble_timeline.py`

- [ ] **Step 1：写失败测试**

`backend/tests/agents/test_rule_assemble_timeline.py`：
```python
import pytest

from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from app.models.schemas import (
    Attraction, Hotel, Location, DiningCandidate, DiningCategory,
    DiningPoolDay, DraftDayContext, WeatherInfo,
)


def _attr(name: str) -> Attraction:
    return Attraction(
        name=name, address=f"{name}地址", visit_duration=120,
        description=f"{name}简介",
        location=Location(longitude=116.4, latitude=39.9),
    )


def _candidate(name: str, category: DiningCategory) -> DiningCandidate:
    return DiningCandidate(
        name=name, category=category, source="nearby",
        location=Location(longitude=116.41, latitude=39.91),
        rating=4.5, avg_cost=80,
    )


def _ctx(attractions, dining_pool=None, hotel=None) -> DraftDayContext:
    return DraftDayContext(
        day_index=0, date="2026-06-01",
        attraction_names=[a.name for a in attractions],
        attractions=attractions,
        hotel=hotel,
        dining_pool=dining_pool or DiningPoolDay(),
    )


def test_no_overrides_no_dining_pool_returns_empty_meals():
    ctx = _ctx([_attr("A"), _attr("B")])
    detail = rule_assemble_day_timeline(ctx, overrides=None)
    assert [a.name for a in detail.attractions] == ["A", "B"]
    assert detail.meals == []
    assert detail.is_assembled is True


def test_no_overrides_with_main_pool_inserts_one_main_at_midpoint():
    pool = DiningPoolDay(main=[_candidate("M1", DiningCategory.MAIN)])
    ctx = _ctx([_attr("A"), _attr("B"), _attr("C"), _attr("D")], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, overrides=None)
    assert len(detail.meals) == 1
    m = detail.meals[0]
    assert m.name == "M1"
    assert m.category == DiningCategory.MAIN
    # 中点：4 个景点 → 第 1 个景点之后（index = 4//2 - 1 = 1，即 attractions[1]=B 之后）
    insert_after_indices = [
        i for i, item in enumerate(detail.timeline_order)
        if item.get("ref_name") == "B"
    ]
    meal_indices = [
        i for i, item in enumerate(detail.timeline_order)
        if item.get("kind") == "meal" and item.get("ref_name") == "M1"
    ]
    assert insert_after_indices and meal_indices
    assert meal_indices[0] == insert_after_indices[0] + 1


def test_override_attractions_order_reorders():
    ctx = _ctx([_attr("A"), _attr("B"), _attr("C")])
    detail = rule_assemble_day_timeline(
        ctx, overrides={"attractions_order": ["C", "A", "B"]}
    )
    assert [a.name for a in detail.attractions] == ["C", "A", "B"]


def test_override_meals_empty_clears_default():
    pool = DiningPoolDay(main=[_candidate("M1", DiningCategory.MAIN)])
    ctx = _ctx([_attr("A"), _attr("B")], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, overrides={"meals": []})
    assert detail.meals == []


def test_override_meals_with_user_picks():
    pool = DiningPoolDay(
        main=[_candidate("M1", DiningCategory.MAIN)],
        snack=[_candidate("S1", DiningCategory.SNACK)],
    )
    ctx = _ctx([_attr("A"), _attr("B")], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, overrides={
        "meals": [
            {"name": "M1", "category": "main", "insert_after": "A"},
            {"name": "S1", "category": "snack", "insert_after": "B"},
        ]
    })
    assert [m.name for m in detail.meals] == ["M1", "S1"]
    assert detail.meals[0].category == DiningCategory.MAIN
    assert detail.meals[1].category == DiningCategory.SNACK


def test_unknown_attraction_in_order_is_ignored():
    ctx = _ctx([_attr("A"), _attr("B")])
    detail = rule_assemble_day_timeline(
        ctx, overrides={"attractions_order": ["X", "A", "Y", "B"]}
    )
    assert [a.name for a in detail.attractions] == ["A", "B"]


def test_hotel_appears_at_start_and_end_of_timeline():
    hotel = Hotel(name="H1", address="酒店地址",
                  location=Location(longitude=116.4, latitude=39.9))
    ctx = _ctx([_attr("A")], hotel=hotel)
    detail = rule_assemble_day_timeline(ctx, overrides=None)
    timeline = detail.timeline_order
    assert timeline[0]["kind"] == "hotel"
    assert timeline[-1]["kind"] == "hotel"
```

- [ ] **Step 2：跑测试，确认全部 FAIL**

```bash
cd backend && pytest tests/agents/test_rule_assemble_timeline.py -v
```
预期：ModuleNotFoundError。

- [ ] **Step 3：创建空 `__init__.py`**

```bash
touch backend/app/agents/langgraph_agent/assemble/__init__.py
```

- [ ] **Step 4：实现 `timeline.py`**

`backend/app/agents/langgraph_agent/assemble/timeline.py`：
```python
"""规则装配每日时间轴

设计原则：
- 景点：默认沿用聚类已排序；用户给了 attractions_order 就按用户的来（忽略不存在的名字）
- 餐饮：用户给了完全用用户的；否则默认嵌一个 main top1 在景点中点之后
- timeline_order：[{kind, ref_name}]，hotel 在头尾，meal 按 insert_after 嵌入
"""
from typing import Dict, Any, List, Optional

from ...models.schemas import (
    Attraction, Meal, Location, DayDetail, DraftDayContext,
    DiningCategory, DiningCandidate,
)


def _candidate_to_meal(c: DiningCandidate) -> Meal:
    """DiningCandidate → Meal（兼容老 type 字段）"""
    type_map = {
        DiningCategory.MAIN: "lunch",          # 默认正餐当作午餐
        DiningCategory.SNACK: "snack",
        DiningCategory.DESSERT: "dessert",
        DiningCategory.CAFE: "cafe",
        DiningCategory.LATE_NIGHT: "late_night",
    }
    return Meal(
        type=type_map.get(c.category, c.category.value),
        category=c.category,
        name=c.name,
        address=c.address,
        location=c.location,
        cuisine=c.cuisine,
        rating=c.rating,
        avg_cost=c.avg_cost,
        distance=c.distance,
        open_hours=c.open_hours,
        tel=c.tel,
        poi_id=c.poi_id,
        source=c.source,
        estimated_cost=c.avg_cost or _default_cost(c.category),
    )


def _default_cost(category: DiningCategory) -> int:
    return {
        DiningCategory.MAIN: 80,
        DiningCategory.SNACK: 30,
        DiningCategory.DESSERT: 40,
        DiningCategory.CAFE: 35,
        DiningCategory.LATE_NIGHT: 60,
    }.get(category, 50)


def _meal_from_override_dict(d: Dict[str, Any]) -> tuple[Meal, str]:
    """把前端传的 meal dict 解析成 (Meal, insert_after)；insert_after 默认 ''"""
    cat_value = d.get("category") or d.get("type") or "main"
    try:
        category = DiningCategory(cat_value)
    except ValueError:
        category = DiningCategory.MAIN

    loc_dict = d.get("location")
    location = None
    if isinstance(loc_dict, dict) and loc_dict.get("longitude"):
        location = Location(
            longitude=float(loc_dict["longitude"]),
            latitude=float(loc_dict["latitude"]),
        )

    avg_cost = d.get("avg_cost")
    meal = Meal(
        type=d.get("type") or category.value,
        category=category,
        name=d.get("name", ""),
        address=d.get("address"),
        location=location,
        cuisine=d.get("cuisine"),
        rating=d.get("rating"),
        avg_cost=avg_cost,
        distance=d.get("distance"),
        open_hours=d.get("open_hours"),
        tel=d.get("tel"),
        poi_id=d.get("poi_id"),
        source=d.get("source") or "user_custom",
        estimated_cost=avg_cost or _default_cost(category),
    )
    insert_after = d.get("insert_after") or ""
    return meal, insert_after


def _apply_attraction_order(
    attractions: List[Attraction], order_names: Optional[List[str]]
) -> List[Attraction]:
    if not order_names:
        return list(attractions)
    by_name = {a.name: a for a in attractions}
    ordered: List[Attraction] = []
    used: set[str] = set()
    for name in order_names:
        if name in by_name and name not in used:
            ordered.append(by_name[name])
            used.add(name)
    # 用户没列到的景点保留在末尾（避免悄悄丢失）
    for a in attractions:
        if a.name not in used:
            ordered.append(a)
    return ordered


def _default_main_meal(ctx: DraftDayContext, attractions: List[Attraction]) -> tuple[Optional[Meal], str]:
    if not attractions or not ctx.dining_pool.main:
        return None, ""
    top1 = ctx.dining_pool.main[0]
    meal = _candidate_to_meal(top1)
    mid_idx = max(len(attractions) // 2 - 1, 0)
    return meal, attractions[mid_idx].name


def _build_timeline_order(
    attractions: List[Attraction],
    meals_with_insert: List[tuple[Meal, str]],
    hotel,
) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    if hotel is not None:
        timeline.append({"kind": "hotel", "ref_name": hotel.name, "phase": "start"})

    pending = list(meals_with_insert)
    # hotel_start 上挂的餐：在 hotel 之后立即插入
    remaining = []
    for meal, ia in pending:
        if ia == "hotel_start":
            timeline.append({"kind": "meal", "ref_name": meal.name})
        else:
            remaining.append((meal, ia))
    pending = remaining

    for attr in attractions:
        timeline.append({"kind": "attraction", "ref_name": attr.name})
        remaining = []
        for meal, ia in pending:
            if ia == attr.name:
                timeline.append({"kind": "meal", "ref_name": meal.name})
            else:
                remaining.append((meal, ia))
        pending = remaining

    # 剩余（insert_after 是 hotel_end 或匹配不上的）放尾部 hotel 之前
    for meal, _ia in pending:
        timeline.append({"kind": "meal", "ref_name": meal.name})

    if hotel is not None:
        timeline.append({"kind": "hotel", "ref_name": hotel.name, "phase": "end"})

    return timeline


def rule_assemble_day_timeline(
    ctx: DraftDayContext,
    overrides: Optional[Dict[str, Any]] = None,
) -> DayDetail:
    overrides = overrides or {}

    attractions = _apply_attraction_order(
        ctx.attractions, overrides.get("attractions_order")
    )

    if "meals" in overrides:
        meals_with_insert = [
            _meal_from_override_dict(d) for d in (overrides["meals"] or [])
        ]
        meals = [m for m, _ in meals_with_insert]
    else:
        default_meal, default_after = _default_main_meal(ctx, attractions)
        if default_meal is not None:
            meals_with_insert = [(default_meal, default_after)]
            meals = [default_meal]
        else:
            meals_with_insert = []
            meals = []

    timeline = _build_timeline_order(attractions, meals_with_insert, ctx.hotel)

    return DayDetail(
        day_index=ctx.day_index,
        date=ctx.date,
        attractions=attractions,
        meals=meals,
        hotel=ctx.hotel,
        timeline_order=timeline,
        is_assembled=True,
    )
```

- [ ] **Step 5：跑测试**

```bash
cd backend && pytest tests/agents/test_rule_assemble_timeline.py -v
```
预期：7 个测试 PASS。

- [ ] **Step 6：提交**

```bash
git add backend/app/agents/langgraph_agent/assemble/ backend/tests/agents/test_rule_assemble_timeline.py
git commit -m "feat(assemble): 添加 rule_assemble_day_timeline 规则装配时间轴

无 override 时默认嵌一个 main top1 在景点中点之后；
用户传 attractions_order 重排景点；传 meals 完全替换默认餐饮。"
```

---

### Task 7：`compute_day_route` + `compute_day_budget`

**Files:**
- Create: `backend/app/agents/langgraph_agent/assemble/route.py`
- Create: `backend/app/agents/langgraph_agent/assemble/budget.py`
- Test: `backend/tests/agents/test_compute_day_budget.py`

- [ ] **Step 1：实现 `route.py`**

`backend/app/agents/langgraph_agent/assemble/route.py`：
```python
"""按 day_detail.timeline_order 计算路线段"""
from typing import List

from ...models.schemas import DayDetail, RouteSegment
from ..utils.route import compute_route_segments


async def compute_day_route(
    day_detail: DayDetail, city: str, transportation: str
) -> List[RouteSegment]:
    """从 timeline_order 提取 waypoints，调高德 directions 算路线段"""
    if not day_detail.timeline_order or len(day_detail.timeline_order) < 2:
        return []

    by_attr_name = {a.name: a for a in day_detail.attractions}
    by_meal_name = {m.name: m for m in day_detail.meals}
    hotel = day_detail.hotel

    waypoints = []
    for item in day_detail.timeline_order:
        kind = item.get("kind")
        ref = item.get("ref_name", "")
        loc = None
        if kind == "hotel" and hotel and hotel.location:
            loc = hotel.location
            name = hotel.name
        elif kind == "attraction":
            a = by_attr_name.get(ref)
            if a and a.location:
                loc = a.location
                name = a.name
        elif kind == "meal":
            m = by_meal_name.get(ref)
            if m and m.location:
                loc = m.location
                name = m.name
        else:
            continue
        if loc is None:
            continue
        wp = {"name": name, "longitude": loc.longitude, "latitude": loc.latitude}
        if waypoints and wp["longitude"] == waypoints[-1]["longitude"] and \
           wp["latitude"] == waypoints[-1]["latitude"]:
            continue
        waypoints.append(wp)

    if len(waypoints) < 2:
        return []

    try:
        segments = await compute_route_segments(waypoints, transportation, city)
    except Exception as e:
        print(f"⚠️ compute_day_route 失败: {e}")
        return []
    return segments
```

- [ ] **Step 2：写预算测试**

`backend/tests/agents/test_compute_day_budget.py`：
```python
from app.agents.langgraph_agent.assemble.budget import compute_day_budget
from app.models.schemas import (
    Attraction, Hotel, Meal, DayDetail, DiningCategory, Location,
)


def test_empty_day_has_zero_budget():
    detail = DayDetail(day_index=0, date="2026-06-01")
    b = compute_day_budget(detail)
    assert b.total == 0
    assert b.total_attractions == 0
    assert b.total_meals == 0


def test_attractions_meals_hotel_summed():
    detail = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[
            Attraction(name="A", address="...", visit_duration=120,
                       description="", ticket_price=60),
            Attraction(name="B", address="...", visit_duration=120,
                       description="", ticket_price=40),
        ],
        hotel=Hotel(name="H", estimated_cost=300),
        meals=[
            Meal(type="main", category=DiningCategory.MAIN, name="M",
                 estimated_cost=80),
            Meal(type="snack", category=DiningCategory.SNACK, name="S",
                 estimated_cost=20),
        ],
    )
    b = compute_day_budget(detail)
    assert b.total_attractions == 100
    assert b.total_meals == 100
    assert b.total_hotels == 300
    assert b.total_transportation == 50  # 默认 50
    assert b.total == 550
```

- [ ] **Step 3：实现 `budget.py`**

`backend/app/agents/langgraph_agent/assemble/budget.py`：
```python
"""单日预算计算"""
from ...models.schemas import Budget, DayDetail


_DAILY_TRANSPORT_DEFAULT = 50  # 元/天，与旧 reduce_assemble_node 保持一致


def compute_day_budget(day_detail: DayDetail) -> Budget:
    total_attractions = sum(a.ticket_price for a in day_detail.attractions)
    total_meals = sum(m.estimated_cost for m in day_detail.meals)
    total_hotels = day_detail.hotel.estimated_cost if (
        day_detail.hotel and day_detail.hotel.estimated_cost
    ) else 0
    total_transportation = _DAILY_TRANSPORT_DEFAULT
    return Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotels,
        total_meals=total_meals,
        total_transportation=total_transportation,
        total=total_attractions + total_meals + total_hotels + total_transportation,
    )
```

- [ ] **Step 4：跑测试**

```bash
cd backend && pytest tests/agents/test_compute_day_budget.py -v
```
预期：2 个测试 PASS。

- [ ] **Step 5：提交**

```bash
git add backend/app/agents/langgraph_agent/assemble/route.py \
       backend/app/agents/langgraph_agent/assemble/budget.py \
       backend/tests/agents/test_compute_day_budget.py
git commit -m "feat(assemble): 添加 compute_day_route 和 compute_day_budget"
```

---

### Task 8：`write_day_narrative_llm` —— 单日叙述文案

**Files:**
- Create: `backend/app/agents/langgraph_agent/assemble/narrative.py`

- [ ] **Step 1：实现 `narrative.py`**

`backend/app/agents/langgraph_agent/assemble/narrative.py`：
```python
"""单日叙述文案（独立 LLM 调用，不参与时间轴编排）"""
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from ...models.schemas import DayDetail, WeatherInfo
from ....services.llm_service import get_llm
from ..exceptions import _invoke_llm_with_retry


_DAY_NARRATIVE_PROMPT = """你是旅行文案专家。请根据已确定的当日行程，写一段简短的当日叙述文案。

**严格约束:**
1. 不要重新编排顺序、不要推荐新景点/餐厅、不要生成时间轴
2. 仅输出 2-3 段 Markdown 文案（含穿衣建议、亮点、注意事项）
3. 字数 200-400 字之间
4. 不要列出门票价格、不要列出路线段距离时间
"""


async def write_day_narrative_llm(
    day_detail: DayDetail,
    weather: Optional[WeatherInfo] = None,
    free_text_input: Optional[str] = None,
    city: str = "",
) -> str:
    attrs = "、".join(a.name for a in day_detail.attractions)
    meals = "、".join(f"{m.name}({(m.category or m.type)})" for m in day_detail.meals)
    hotel_name = day_detail.hotel.name if day_detail.hotel else "未定"

    weather_line = ""
    if weather:
        weather_line = (
            f"天气: 白天{weather.day_weather} {weather.day_temp}°C / "
            f"夜间{weather.night_weather} {weather.night_temp}°C, "
            f"{weather.wind_direction} {weather.wind_power}"
        )

    free_text_line = ""
    if free_text_input:
        free_text_line = f"\n用户额外要求: {free_text_input}"

    prompt = f"""请为 {city} 的第 {day_detail.day_index + 1} 天 ({day_detail.date}) 写一段叙述文案。

已确定的安排:
- 景点: {attrs or '无'}
- 餐饮: {meals or '无（用户未选择）'}
- 入住: {hotel_name}
{weather_line}{free_text_line}

请按要求输出 Markdown 文案。"""

    llm = get_llm()
    try:
        response = await _invoke_llm_with_retry(
            llm, [SystemMessage(content=_DAY_NARRATIVE_PROMPT),
                  HumanMessage(content=prompt)]
        )
        text = (response.content or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return text
    except Exception as e:
        print(f"⚠️ write_day_narrative_llm 失败: {e}")
        return ""
```

- [ ] **Step 2：写一个 smoke test（mock LLM）**

在 `backend/tests/agents/test_rule_assemble_timeline.py` 末尾追加：
```python
from unittest.mock import patch, AsyncMock

from app.agents.langgraph_agent.assemble.narrative import write_day_narrative_llm
from app.models.schemas import DayDetail, WeatherInfo


@pytest.mark.asyncio
async def test_narrative_returns_stripped_text():
    detail = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[_attr("A")],
    )
    fake_response = type("Resp", (), {"content": "  ## Day 1\n\n好天气，多带水。  "})

    with patch(
        "app.agents.langgraph_agent.assemble.narrative._invoke_llm_with_retry",
        new=AsyncMock(return_value=fake_response),
    ), patch("app.agents.langgraph_agent.assemble.narrative.get_llm",
             return_value=object()):
        text = await write_day_narrative_llm(
            detail, weather=None, free_text_input=None, city="北京"
        )
    assert "Day 1" in text
    assert not text.startswith(" ")


@pytest.mark.asyncio
async def test_narrative_returns_empty_on_failure():
    detail = DayDetail(day_index=0, date="2026-06-01", attractions=[_attr("A")])
    with patch(
        "app.agents.langgraph_agent.assemble.narrative._invoke_llm_with_retry",
        side_effect=RuntimeError("LLM down"),
    ), patch("app.agents.langgraph_agent.assemble.narrative.get_llm",
             return_value=object()):
        text = await write_day_narrative_llm(detail, None, None, "北京")
    assert text == ""
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/agents/test_rule_assemble_timeline.py -v
```
预期：9 个测试全部 PASS（原 7 个 + 新加 2 个）。

- [ ] **Step 4：提交**

```bash
git add backend/app/agents/langgraph_agent/assemble/narrative.py \
       backend/tests/agents/test_rule_assemble_timeline.py
git commit -m "feat(assemble): 添加 write_day_narrative_llm 单独 LLM 调用写当日叙述"
```

---

## Phase 4：Finalize

### Task 9：`finalize_draft` —— 定稿流水线

**Files:**
- Create: `backend/app/agents/langgraph_agent/finalize/__init__.py` (空)
- Create: `backend/app/agents/langgraph_agent/finalize/pipeline.py`
- Test: `backend/tests/agents/test_finalize_pipeline.py`

- [ ] **Step 1：写失败测试（mock 所有外部依赖）**

`backend/tests/agents/test_finalize_pipeline.py`：
```python
import json
from unittest.mock import patch, AsyncMock

import pytest

from app.database import init_db
from app.services import trip_draft_service
from app.agents.langgraph_agent.finalize.pipeline import finalize_draft
from app.models.schemas import (
    TripRequest, MacroPlan, DaySkeleton, Attraction, Hotel,
    DayDetail, Location, DiningPoolDay,
)


def _sample_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


def _sample_macro():
    return MacroPlan(
        city="北京", total_days=2,
        days=[
            DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["A"]),
            DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["B"]),
        ],
    )


@pytest.mark.asyncio
async def test_finalize_assembles_missing_days_and_writes_trip_history():
    await init_db()
    draft_id = await trip_draft_service.create_draft(
        user_id="u1", request=_sample_request(),
        selected_attractions=[],
        macro_plan=_sample_macro(),
        clusters_data=[
            [{"name": "A", "longitude": 116.4, "latitude": 39.9}],
            [{"name": "B", "longitude": 116.5, "latitude": 39.95}],
        ],
        hotels_by_day=[[], []],
        dining_pool=[DiningPoolDay().model_dump(mode="json"),
                     DiningPoolDay().model_dump(mode="json")],
        weather_info=[],
    )
    # 用户只展开了第 0 天
    await trip_draft_service.patch_day_detail(
        draft_id, 0,
        DayDetail(
            day_index=0, date="2026-06-01",
            attractions=[Attraction(name="A", address="", visit_duration=120,
                                    description="",
                                    location=Location(longitude=116.4, latitude=39.9))],
            is_assembled=True,
        ),
    )

    fake_trip_record = type("Rec", (), {"id": 777})()

    with patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer",
        new=AsyncMock(return_value=("行程标语", "总建议", "晴间多云")),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_extract_and_save_preferences",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline.save_trip",
        new=AsyncMock(return_value=fake_trip_record),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline.compute_day_route",
        new=AsyncMock(return_value=[]),
    ):
        trip_plan, trip_id = await finalize_draft(draft_id, user_id="u1")

    assert trip_id == 777
    assert trip_plan.city == "北京"
    assert len(trip_plan.days) == 2
    assert trip_plan.trip_tagline == "行程标语"
    assert trip_plan.weather_summary == "晴间多云"
    # draft 已标记 finalized
    record = await trip_draft_service.get_draft(draft_id)
    assert record.status == "finalized"
    assert record.finalized_trip_id == 777


@pytest.mark.asyncio
async def test_finalize_rejects_already_finalized():
    await init_db()
    draft_id = await trip_draft_service.create_draft(
        user_id="u1", request=_sample_request(),
        selected_attractions=[], macro_plan=_sample_macro(),
        clusters_data=[], hotels_by_day=[],
        dining_pool=[DiningPoolDay().model_dump(mode="json")] * 2,
        weather_info=[],
    )
    await trip_draft_service.mark_finalized(draft_id, trip_id=1)

    with pytest.raises(ValueError, match="已 finalized"):
        await finalize_draft(draft_id, user_id="u1")
```

- [ ] **Step 2：实现 `finalize/pipeline.py`**

`backend/app/agents/langgraph_agent/finalize/pipeline.py`：
```python
"""定稿流水线：草稿 → TripPlan → 全局综合 + 偏好提取 → trip_history"""
import json
from typing import Tuple, Optional

from ...models.schemas import (
    TripRequest, MacroPlan, TripPlan, DayPlan, DayDetail, DraftDayContext,
    DiningPoolDay, Attraction, Hotel, Budget, WeatherInfo,
)
from ...services import trip_draft_service
from ...services.trip_history_service import save_trip
from ..assemble.timeline import rule_assemble_day_timeline
from ..assemble.route import compute_day_route
from ..assemble.budget import compute_day_budget


async def _run_global_synthesizer(trip_plan: TripPlan, free_text: str) -> Tuple[str, str, str]:
    """复用旧 global_synthesizer_node 的核心 LLM 调用，返回 (tagline, suggestions, summary)"""
    from ..nodes.generate import global_synthesizer_node, _generate_weather_summary_fallback
    state = {"trip_plan": trip_plan, "request": _make_pseudo_request(trip_plan, free_text),
            "weather_info": ""}
    try:
        result = await global_synthesizer_node(state)
        plan = result.get("trip_plan") or trip_plan
        return plan.trip_tagline, plan.overall_suggestions, plan.weather_summary
    except Exception as e:
        print(f"⚠️ global_synthesizer 失败，使用兜底: {e}")
        return "", "", _generate_weather_summary_fallback(trip_plan)


def _make_pseudo_request(plan: TripPlan, free_text: str):
    from ...models.schemas import TripRequest
    return TripRequest(
        city=plan.city, start_date=plan.start_date, end_date=plan.end_date,
        travel_days=len(plan.days), transportation="公共交通",
        accommodation="经济型酒店", free_text_input=free_text,
    )


async def _run_extract_and_save_preferences(trip_plan: TripPlan, user_id: str) -> None:
    """复用旧 extract_preferences_node + save_preferences_node"""
    from ..nodes.preferences import extract_preferences_node, save_preferences_node
    state = {"trip_plan": trip_plan, "user_id": user_id, "extracted_preferences": None}
    state.update(await extract_preferences_node(state))
    await save_preferences_node(state)


def _day_detail_to_day_plan(detail: DayDetail, transportation: str, accommodation: str) -> DayPlan:
    return DayPlan(
        date=detail.date,
        day_index=detail.day_index,
        description=detail.description,
        transportation=transportation,
        accommodation=accommodation,
        hotel=detail.hotel,
        attractions=detail.attractions,
        meals=detail.meals,
        route_segments=detail.route_segments,
    )


def _build_day_context(
    day_idx: int, macro_plan: MacroPlan, clusters_data: list,
    hotels_by_day: list, dining_pool: list, weather_info: list,
) -> DraftDayContext:
    day_skeleton = macro_plan.days[day_idx]
    cluster = clusters_data[day_idx] if day_idx < len(clusters_data) else []
    attractions = [
        Attraction(
            name=c["name"], address=c.get("address", ""), visit_duration=120,
            description="",
            location=({"longitude": c["longitude"], "latitude": c["latitude"]}
                      if c.get("longitude") else None),
        ) for c in cluster
    ]
    hotel: Optional[Hotel] = None
    if day_idx < len(hotels_by_day) and hotels_by_day[day_idx]:
        h = hotels_by_day[day_idx][0]
        hotel = Hotel(**{k: h[k] for k in h.keys() if k in Hotel.model_fields})

    pool = DiningPoolDay()
    if day_idx < len(dining_pool):
        pool = DiningPoolDay.model_validate(dining_pool[day_idx])

    weather_obj = None
    if day_idx < len(weather_info):
        w = weather_info[day_idx]
        if isinstance(w, dict):
            weather_obj = WeatherInfo.model_validate(w)

    return DraftDayContext(
        day_index=day_idx, date=day_skeleton.date,
        attraction_names=day_skeleton.attraction_names,
        attractions=attractions,
        hotel=hotel,
        dining_pool=pool,
        weather=weather_obj,
    )


async def finalize_draft(draft_id: str, *, user_id: str) -> Tuple[TripPlan, int]:
    record = await trip_draft_service.get_draft(draft_id)
    if record is None:
        raise ValueError(f"draft {draft_id} 不存在")
    if record.status == "finalized":
        raise ValueError(f"draft {draft_id} 已 finalized")

    request = TripRequest.model_validate_json(record.request_json)
    macro_plan = MacroPlan.model_validate_json(record.macro_plan_json)
    clusters_data = json.loads(record.clusters_data_json)
    hotels_by_day = json.loads(record.hotels_by_day_json)
    dining_pool = json.loads(record.dining_pool_json)
    weather_info = json.loads(record.weather_info_json)
    days_detail_raw = json.loads(record.days_detail_json)

    day_plans = []
    total_budget = Budget()
    for idx in range(request.travel_days):
        existing = days_detail_raw[idx] if idx < len(days_detail_raw) else None
        if existing is not None:
            detail = DayDetail.model_validate(existing)
            if not detail.route_segments:
                detail.route_segments = await compute_day_route(
                    detail, request.city, request.transportation
                )
            if detail.day_budget is None:
                detail.day_budget = compute_day_budget(detail)
        else:
            ctx = _build_day_context(idx, macro_plan, clusters_data,
                                     hotels_by_day, dining_pool, weather_info)
            detail = rule_assemble_day_timeline(ctx, overrides=None)
            detail.route_segments = await compute_day_route(
                detail, request.city, request.transportation
            )
            detail.day_budget = compute_day_budget(detail)

        day_plans.append(_day_detail_to_day_plan(
            detail, request.transportation, request.accommodation
        ))
        b = detail.day_budget
        total_budget = Budget(
            total_attractions=total_budget.total_attractions + b.total_attractions,
            total_hotels=total_budget.total_hotels + b.total_hotels,
            total_meals=total_budget.total_meals + b.total_meals,
            total_transportation=total_budget.total_transportation + b.total_transportation,
            total=total_budget.total + b.total,
            budget_limit=request.budget,
        )

    weather_list = [WeatherInfo.model_validate(w) for w in weather_info if isinstance(w, dict)]

    trip_plan = TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=day_plans,
        weather_info=weather_list,
        overall_suggestions="",
        budget=total_budget,
        companions=request.companions,
    )

    tagline, suggestions, summary = await _run_global_synthesizer(
        trip_plan, request.free_text_input or ""
    )
    trip_plan.trip_tagline = tagline
    trip_plan.overall_suggestions = suggestions
    trip_plan.weather_summary = summary

    await _run_extract_and_save_preferences(trip_plan, user_id)

    trip_record = await save_trip(trip_plan, request=request)
    await trip_draft_service.mark_finalized(draft_id, trip_id=trip_record.id)
    await trip_draft_service.update_synthesizer_fields(
        draft_id, trip_tagline=tagline,
        overall_suggestions=suggestions, weather_summary=summary,
    )

    return trip_plan, trip_record.id
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/agents/test_finalize_pipeline.py -v
```
预期：2 个测试 PASS。

- [ ] **Step 4：提交**

```bash
git add backend/app/agents/langgraph_agent/finalize/ \
       backend/tests/agents/test_finalize_pipeline.py
git commit -m "feat(finalize): 添加 finalize_draft 把草稿转 TripPlan 并写 trip_history

把未展开的天用 rule_assemble_day_timeline 兜底装配；
跑 global_synthesizer 填 tagline/suggestions/weather_summary；
跑 extract_preferences + save_preferences 学习偏好；
写 trip_history 后把 draft.status 置 finalized。"
```

---

## Phase 5：API 端点

### Task 10：路由骨架 + `POST /draft/from-selections/stream`

**Files:**
- Create: `backend/app/api/routes/trip_draft.py`
- Modify: `backend/app/api/main.py`

- [ ] **Step 1：创建路由文件**

`backend/app/api/routes/trip_draft.py`：
```python
"""草稿（骨架/详细分离）API 路由"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...agents.langgraph_agent.graph import get_trip_planner_agent
from ...services import trip_draft_service
from ...models.schemas import PlanFromSelectionsRequest

router = APIRouter(prefix="/trip/draft", tags=["trip_draft"])


@router.post(
    "/from-selections/stream",
    summary="从 Discover 勾选结果生成草稿骨架（SSE）",
)
async def create_draft_from_selections(req: PlanFromSelectionsRequest):
    async def event_generator():
        agent = get_trip_planner_agent()
        try:
            selected = [a.model_dump() for a in req.selected_attractions]
            day_assign = None
            if req.day_assignments:
                day_assign = [[a.model_dump() for a in day] for day in req.day_assignments]
            async for event in agent.plan_from_selections_stream(
                request=req.request,
                selected_attractions=selected,
                day_assignments=day_assign,
                weather_info=req.weather_info,
                user_id=req.user_id,
            ):
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            error = json.dumps(
                {"type": "error", "message": f"骨架生成失败: {str(e)}", "progress": 0},
                ensure_ascii=False,
            )
            yield f"data: {error}\n\n"

    async def heartbeat_wrapper():
        async for chunk in event_generator():
            yield chunk
        while True:
            await asyncio.sleep(15)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        heartbeat_wrapper(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2：修改 `LangGraphTripPlanner.plan_from_selections_stream` 在 SSE complete 事件里追加 `draft_id`**

`backend/app/agents/langgraph_agent/graph.py` 中 `plan_from_selections_stream` 的最后一段（在 `trip_plan = final_state.get("trip_plan")` 处）改为：
```python
            draft_id = final_state.get("draft_id")
            if draft_id:
                yield {
                    "type": "complete",
                    "message": "✅ 骨架已生成，可进入装配",
                    "progress": 100,
                    "draft_id": draft_id,
                }
            else:
                # 骨架图未写入 draft_id（异常情况）—退回到旧 trip_plan 行为
                trip_plan = final_state.get("trip_plan")
                if not trip_plan:
                    trip_plan = _create_fallback_plan(request, final_state)
                plan_dict = trip_plan.model_dump() if hasattr(trip_plan, 'model_dump') else trip_plan.dict()
                yield {"type": "complete", "message": "✅ 旅行计划生成完成!",
                       "progress": 100, "data": plan_dict}
```

并去掉这个函数里对 `_create_fallback_plan` 的兜底（保留为最后 else 分支即可）。

- [ ] **Step 3：注册路由到 `main.py`**

`backend/app/api/main.py` 中：

把 `from .routes import trip_lg, poi_lg, map_lg, trip_history, admin` 改为：
```python
from .routes import trip_lg, poi_lg, map_lg, trip_history, admin, trip_draft
```

并追加注册：
```python
app.include_router(trip_draft.router, prefix="/api")
```

- [ ] **Step 4：手测端点存在**

```bash
cd backend && python -c "from app.api.main import app; print([r.path for r in app.routes if 'draft' in r.path])"
```
预期：包含 `/api/trip/draft/from-selections/stream`

- [ ] **Step 5：提交**

```bash
git add backend/app/api/routes/trip_draft.py backend/app/api/main.py backend/app/agents/langgraph_agent/graph.py
git commit -m "feat(api): 添加 POST /api/trip/draft/from-selections/stream 端点

SSE complete 事件返回 draft_id；plan_from_selections_stream 改为
返回 draft_id 而非完整 trip_plan。"
```

---

### Task 11：`GET /draft/{id}` + `DELETE /draft/{id}`

**Files:**
- Modify: `backend/app/api/routes/trip_draft.py`
- Test: `backend/tests/api/test_draft_endpoints.py`

- [ ] **Step 1：写失败测试**

新建 `backend/tests/api/__init__.py`（空）和 `backend/tests/api/test_draft_endpoints.py`：
```python
import json
from unittest.mock import patch, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database import init_db
from app.services import trip_draft_service
from app.models.schemas import (
    TripRequest, MacroPlan, DaySkeleton, DiningPoolDay,
)


def _sample_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


def _sample_macro():
    return MacroPlan(
        city="北京", total_days=2,
        days=[
            DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["A"]),
            DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["B"]),
        ],
    )


async def _seed_draft(user_id="u1") -> str:
    return await trip_draft_service.create_draft(
        user_id=user_id, request=_sample_request(),
        selected_attractions=[], macro_plan=_sample_macro(),
        clusters_data=[
            [{"name": "A", "longitude": 116.4, "latitude": 39.9}],
            [{"name": "B", "longitude": 116.5, "latitude": 39.95}],
        ],
        hotels_by_day=[[], []],
        dining_pool=[DiningPoolDay().model_dump(mode="json")] * 2,
        weather_info=[],
    )


@pytest.fixture(scope="function")
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_draft_returns_payload(client):
    draft_id = await _seed_draft()
    resp = await client.get(f"/api/trip/draft/{draft_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft_id"] == draft_id
    assert body["status"] == "skeleton"
    assert body["city"] == "北京"
    assert len(body["days"]) == 2
    assert len(body["days_detail"]) == 2
    assert all(d is None for d in body["days_detail"])


@pytest.mark.asyncio
async def test_get_draft_404(client):
    resp = await client.get("/api/trip/draft/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_draft_removes_it(client):
    draft_id = await _seed_draft()
    resp = await client.delete(f"/api/trip/draft/{draft_id}")
    assert resp.status_code == 200
    resp2 = await client.get(f"/api/trip/draft/{draft_id}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_draft_404(client):
    resp = await client.delete("/api/trip/draft/does-not-exist")
    assert resp.status_code == 404
```

- [ ] **Step 2：实现端点 + 添加 `_load_payload` 辅助**

`backend/app/api/routes/trip_draft.py` 末尾追加：
```python
from ...models.schemas import (
    TripDraftPayload, TripRequest, MacroPlan, DraftDayContext,
    DayDetail, DiningPoolDay, WeatherInfo, Attraction, Hotel, Location,
)


def _load_payload(record) -> TripDraftPayload:
    """ORM record → TripDraftPayload"""
    request = TripRequest.model_validate_json(record.request_json)
    macro_plan = MacroPlan.model_validate_json(record.macro_plan_json)
    clusters_data = json.loads(record.clusters_data_json)
    hotels_by_day = json.loads(record.hotels_by_day_json)
    dining_pool_raw = json.loads(record.dining_pool_json)
    weather_info_raw = json.loads(record.weather_info_json)
    days_detail_raw = json.loads(record.days_detail_json)

    days: list[DraftDayContext] = []
    for idx in range(request.travel_days):
        ds = macro_plan.days[idx] if idx < len(macro_plan.days) else None
        cluster = clusters_data[idx] if idx < len(clusters_data) else []
        attractions = []
        for c in cluster:
            loc = None
            if c.get("longitude") and c.get("latitude"):
                loc = Location(longitude=c["longitude"], latitude=c["latitude"])
            attractions.append(Attraction(
                name=c.get("name", ""), address=c.get("address", ""),
                visit_duration=120, description="", location=loc,
            ))
        hotel = None
        if idx < len(hotels_by_day) and hotels_by_day[idx]:
            h = hotels_by_day[idx][0]
            hotel_kwargs = {k: v for k, v in h.items() if k in Hotel.model_fields}
            if h.get("location") and isinstance(h["location"], dict):
                hotel_kwargs["location"] = Location(**h["location"])
            hotel = Hotel(**hotel_kwargs)
        pool = DiningPoolDay()
        if idx < len(dining_pool_raw):
            pool = DiningPoolDay.model_validate(dining_pool_raw[idx])
        weather_obj = None
        for w in weather_info_raw:
            if isinstance(w, dict) and w.get("date") == (ds.date if ds else ""):
                weather_obj = WeatherInfo.model_validate(w)
                break
        days.append(DraftDayContext(
            day_index=idx, date=ds.date if ds else "",
            attraction_names=ds.attraction_names if ds else [],
            attractions=attractions, hotel=hotel,
            dining_pool=pool, weather=weather_obj,
        ))

    days_detail = []
    for d in days_detail_raw:
        if d is None:
            days_detail.append(None)
        else:
            days_detail.append(DayDetail.model_validate(d))

    weather_list = [WeatherInfo.model_validate(w)
                    for w in weather_info_raw if isinstance(w, dict)]

    return TripDraftPayload(
        draft_id=record.id, status=record.status,
        request=request, city=macro_plan.city, macro_plan=macro_plan,
        days=days, days_detail=days_detail,
        weather_info=weather_list,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


@router.get("/{draft_id}", response_model=TripDraftPayload, summary="读取草稿完整内容")
async def get_draft(draft_id: str):
    record = await trip_draft_service.get_draft(draft_id)
    if record is None:
        raise HTTPException(404, detail="draft 不存在")
    return _load_payload(record)


@router.delete("/{draft_id}", summary="删除草稿")
async def delete_draft(draft_id: str):
    ok = await trip_draft_service.delete_draft(draft_id)
    if not ok:
        raise HTTPException(404, detail="draft 不存在")
    return {"success": True}
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/api/test_draft_endpoints.py -v
```
预期：4 个测试 PASS。

- [ ] **Step 4：提交**

```bash
git add backend/app/api/routes/trip_draft.py backend/tests/api/
git commit -m "feat(api): 添加 GET/DELETE /api/trip/draft/{id} 端点"
```

---

### Task 12：`POST /draft/{id}/day/{n}/assemble`（含 `force`）

**Files:**
- Modify: `backend/app/api/routes/trip_draft.py`
- Modify: `backend/tests/api/test_draft_endpoints.py`

- [ ] **Step 1：在 `test_draft_endpoints.py` 追加测试**

```python
@pytest.mark.asyncio
async def test_assemble_returns_day_detail_and_writes_back(client):
    draft_id = await _seed_draft()
    with patch(
        "app.api.routes.trip_draft.compute_day_route",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.api.routes.trip_draft.write_day_narrative_llm",
        new=AsyncMock(return_value="今天是晴天，多带水。"),
    ):
        resp = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["day_index"] == 0
    assert body["day_detail"]["is_assembled"] is True
    assert body["day_detail"]["description"] == "今天是晴天，多带水。"
    # 服务端已 patch 进去
    record = await trip_draft_service.get_draft(draft_id)
    days = json.loads(record.days_detail_json)
    assert days[0] is not None
    assert days[1] is None


@pytest.mark.asyncio
async def test_assemble_idempotent_returns_cached(client):
    """已 assembled 的天再调一次不重新跑 LLM；force=true 才重跑"""
    draft_id = await _seed_draft()
    narrative_mock = AsyncMock(return_value="V1 文案")
    with patch(
        "app.api.routes.trip_draft.compute_day_route",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.api.routes.trip_draft.write_day_narrative_llm",
        new=narrative_mock,
    ):
        r1 = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
        assert narrative_mock.await_count == 1
        # 再调一次（不带 force）：不该重跑 LLM
        r2 = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
        assert narrative_mock.await_count == 1
        # 带 force：重跑
        narrative_mock.return_value = "V2 文案"
        r3 = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/assemble?force=true", json={}
        )
        assert narrative_mock.await_count == 2
        assert r3.json()["day_detail"]["description"] == "V2 文案"


@pytest.mark.asyncio
async def test_assemble_day_out_of_range(client):
    draft_id = await _seed_draft()
    resp = await client.post(f"/api/trip/draft/{draft_id}/day/99/assemble", json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_assemble_rejects_finalized_draft(client):
    draft_id = await _seed_draft()
    await trip_draft_service.mark_finalized(draft_id, trip_id=1)
    resp = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
    assert resp.status_code == 409
```

- [ ] **Step 2：在 `trip_draft.py` 顶部加入装配相关导入**

```python
from ...agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from ...agents.langgraph_agent.assemble.route import compute_day_route
from ...agents.langgraph_agent.assemble.budget import compute_day_budget
from ...agents.langgraph_agent.assemble.narrative import write_day_narrative_llm
```

- [ ] **Step 3：实现 `/assemble` 端点**

```python
from fastapi import Query
from pydantic import BaseModel


class DayDetailResponse(BaseModel):
    draft_id: str
    day_index: int
    day_detail: DayDetail


def _ensure_editable(record):
    if record is None:
        raise HTTPException(404, detail="draft 不存在")
    if record.status == "finalized":
        raise HTTPException(409, detail="draft 已 finalized 不可修改")


def _get_day_context_from_record(record, day_index: int) -> DraftDayContext:
    payload = _load_payload(record)
    if day_index < 0 or day_index >= len(payload.days):
        raise HTTPException(409, detail=f"day_index 越界 (max={len(payload.days) - 1})")
    return payload.days[day_index]


@router.post("/{draft_id}/day/{day_index}/assemble", response_model=DayDetailResponse,
             summary="展开某天：规则装配 + 路线 + LLM 叙述")
async def assemble_day(
    draft_id: str, day_index: int,
    overrides: DayEditRequest, force: bool = Query(False),
):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)

    existing_days = json.loads(record.days_detail_json)
    if (not force) and existing_days[day_index] is not None and \
       existing_days[day_index].get("is_assembled"):
        cached = DayDetail.model_validate(existing_days[day_index])
        return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=cached)

    request = TripRequest.model_validate_json(record.request_json)
    override_dict = overrides.model_dump(exclude_none=True)
    detail = rule_assemble_day_timeline(ctx, overrides=override_dict or None)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    detail.day_budget = compute_day_budget(detail)
    detail.description = await write_day_narrative_llm(
        detail, weather=ctx.weather,
        free_text_input=request.free_text_input or "",
        city=request.city,
    )
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)
```

并在文件顶部导入处确保 `DayEditRequest` 已被引入：
```python
from ...models.schemas import (
    TripDraftPayload, TripRequest, MacroPlan, DraftDayContext,
    DayDetail, DiningPoolDay, WeatherInfo, Attraction, Hotel, Location,
    DayEditRequest,
)
```

- [ ] **Step 4：跑测试**

```bash
cd backend && pytest tests/api/test_draft_endpoints.py -v
```
预期：8 个测试 PASS（原 4 + 新 4）。

- [ ] **Step 5：提交**

```bash
git add backend/app/api/routes/trip_draft.py backend/tests/api/test_draft_endpoints.py
git commit -m "feat(api): 添加 POST /api/trip/draft/{id}/day/{n}/assemble (含 force 幂等)"
```

---

### Task 13：`POST /draft/{id}/day/{n}/recompute`

**Files:**
- Modify: `backend/app/api/routes/trip_draft.py`
- Modify: `backend/tests/api/test_draft_endpoints.py`

- [ ] **Step 1：在测试文件追加**

```python
@pytest.mark.asyncio
async def test_recompute_with_attractions_order_change(client):
    draft_id = await _seed_draft()
    # 先 assemble 一次
    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])), \
         patch("app.api.routes.trip_draft.write_day_narrative_llm",
               new=AsyncMock(return_value="V1")):
        await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})

    # recompute：把景点顺序倒过来
    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/recompute",
            json={"attractions_order": ["A"], "meals": []}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert [a["name"] for a in body["day_detail"]["attractions"]] == ["A"]
    assert body["day_detail"]["meals"] == []
    # 文案保留旧的（recompute 不重写）
    assert body["day_detail"]["description"] == "V1"


@pytest.mark.asyncio
async def test_recompute_field_omission_preserves_current(client):
    """不传 meals 字段应保留当前 day_detail.meals"""
    draft_id = await _seed_draft()
    # 模拟：assemble 后餐饮非空
    existing = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[Attraction(name="A", address="", visit_duration=120,
                                description="",
                                location=Location(longitude=116.4, latitude=39.9))],
        meals=[
            {"type": "main", "category": "main", "name": "保留我", "estimated_cost": 80}
        ],
        description="V1", is_assembled=True,
    )
    await trip_draft_service.patch_day_detail(draft_id, 0, existing)

    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/recompute",
            json={"attractions_order": ["A"]},  # 故意不传 meals
        )
    assert resp.status_code == 200
    body = resp.json()
    meal_names = [m["name"] for m in body["day_detail"]["meals"]]
    assert "保留我" in meal_names
```

- [ ] **Step 2：实现 `/recompute` 端点**

`backend/app/api/routes/trip_draft.py` 追加：
```python
@router.post("/{draft_id}/day/{day_index}/recompute", response_model=DayDetailResponse,
             summary="重算某天：规则装配 + amap 路线（无 LLM）")
async def recompute_day(draft_id: str, day_index: int, edit: DayEditRequest):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)

    # 取当前 day_detail 作为"保留意图"的源
    existing_days = json.loads(record.days_detail_json)
    current = (DayDetail.model_validate(existing_days[day_index])
               if existing_days[day_index] else None)

    # 合并 overrides：未传字段沿用当前 day_detail
    final_order = edit.attractions_order
    if final_order is None and current:
        final_order = [a.name for a in current.attractions]
    final_meals = edit.meals
    if final_meals is None and current:
        final_meals = [m.model_dump(mode="json") for m in current.meals]
        # 默认把每个 meal 锚回中点景点之后，避免位置漂移
        if final_meals and final_order:
            mid = max(len(final_order) // 2 - 1, 0)
            for m in final_meals:
                m.setdefault("insert_after", final_order[mid] if final_order else "")

    overrides_dict = {}
    if final_order is not None:
        overrides_dict["attractions_order"] = final_order
    if final_meals is not None:
        overrides_dict["meals"] = final_meals

    request = TripRequest.model_validate_json(record.request_json)
    detail = rule_assemble_day_timeline(ctx, overrides=overrides_dict or None)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    detail.day_budget = compute_day_budget(detail)
    # 保留当前 description（recompute 不写 LLM）
    detail.description = current.description if current else ""
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/api/test_draft_endpoints.py -v
```
预期：10 个测试 PASS。

- [ ] **Step 4：提交**

```bash
git add backend/app/api/routes/trip_draft.py backend/tests/api/test_draft_endpoints.py
git commit -m "feat(api): 添加 POST /api/trip/draft/{id}/day/{n}/recompute

字段缺失语义：不传保留当前；传空数组清空。"
```

---

### Task 14：`/ai-rearrange` + `/narrative`

**Files:**
- Modify: `backend/app/api/routes/trip_draft.py`
- Modify: `backend/tests/api/test_draft_endpoints.py`

- [ ] **Step 1：在测试文件追加**

```python
@pytest.mark.asyncio
async def test_narrative_endpoint_rewrites_description_only(client):
    draft_id = await _seed_draft()
    existing = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[Attraction(name="A", address="", visit_duration=120,
                                description="")],
        description="V1", is_assembled=True,
    )
    await trip_draft_service.patch_day_detail(draft_id, 0, existing)

    with patch("app.api.routes.trip_draft.write_day_narrative_llm",
               new=AsyncMock(return_value="V2 新文案")):
        resp = await client.post(f"/api/trip/draft/{draft_id}/day/0/narrative", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["day_detail"]["description"] == "V2 新文案"
    # 景点未动
    assert [a["name"] for a in body["day_detail"]["attractions"]] == ["A"]


@pytest.mark.asyncio
async def test_ai_rearrange_replaces_day_detail(client):
    draft_id = await _seed_draft()
    # 先 assemble
    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])), \
         patch("app.api.routes.trip_draft.write_day_narrative_llm",
               new=AsyncMock(return_value="原文案")):
        await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})

    # mock LLM 返回一组餐厅 + 景点顺序
    fake_llm_resp = type("R", (), {"content": json.dumps({
        "attractions_order": ["A"],
        "meals": [{"category": "main", "name": "AI 推荐", "insert_after": "A",
                   "estimated_cost": 100}],
    })})
    with patch("app.api.routes.trip_draft._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_llm_resp)), \
         patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/ai-rearrange",
            json={"hint": "我想吃辣的"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "AI 推荐" in [m["name"] for m in body["day_detail"]["meals"]]
```

- [ ] **Step 2：实现两个端点**

在 `backend/app/api/routes/trip_draft.py` 顶部导入区追加：
```python
from langchain_core.messages import SystemMessage, HumanMessage

from ...services.llm_service import get_llm
from ...agents.langgraph_agent.exceptions import _invoke_llm_with_retry
from ...models.schemas import AIRearrangeRequest
```

文件末尾追加：
```python
@router.post("/{draft_id}/day/{day_index}/narrative", response_model=DayDetailResponse,
             summary="重写当日叙述文案（仅刷新 description）")
async def rewrite_narrative(draft_id: str, day_index: int):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)
    request = TripRequest.model_validate_json(record.request_json)
    existing_days = json.loads(record.days_detail_json)
    if existing_days[day_index] is None:
        raise HTTPException(409, detail="该天尚未 assemble，无法重写文案")
    detail = DayDetail.model_validate(existing_days[day_index])
    detail.description = await write_day_narrative_llm(
        detail, weather=ctx.weather,
        free_text_input=request.free_text_input or "",
        city=request.city,
    )
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)


_AI_REARRANGE_SYSTEM = """你是单日行程优化专家。请从给定的餐饮候选池中给出一份当日最优组合。

严格约束：
1. 只能从候选池中挑餐厅，禁止编造名字
2. 输出 JSON，含 attractions_order (景点名顺序) 和 meals (含 category, name, insert_after, estimated_cost)
3. category 必须是 main/snack/dessert/cafe/late_night 之一
4. insert_after 必须是 attractions_order 里的景点名（或 hotel_start / hotel_end）
5. 不要输出其他字段、不要 markdown、纯 JSON"""


@router.post("/{draft_id}/day/{day_index}/ai-rearrange", response_model=DayDetailResponse,
             summary="AI 重新安排某天")
async def ai_rearrange_day(draft_id: str, day_index: int, req: AIRearrangeRequest):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)
    request = TripRequest.model_validate_json(record.request_json)

    pool_summary = []
    for cat, items in ctx.dining_pool.model_dump().items():
        if items:
            names = "、".join(it["name"] for it in items[:5])
            pool_summary.append(f"  {cat}: {names}")
    pool_text = "\n".join(pool_summary) or "（候选池为空）"

    attr_names = "、".join(a.name for a in ctx.attractions) or "（无）"
    hint = req.hint or ""

    prompt = f"""城市: {request.city}, 第 {day_index + 1} 天 ({ctx.date})

景点（可重排）: {attr_names}
餐饮候选池:
{pool_text}

用户提示: {hint or '无'}

请输出 JSON。"""

    llm = get_llm()
    try:
        resp = await _invoke_llm_with_retry(
            llm, [SystemMessage(content=_AI_REARRANGE_SYSTEM),
                  HumanMessage(content=prompt)],
        )
        raw = (resp.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
    except Exception as e:
        raise HTTPException(422, detail=f"AI 暂不可用: {str(e)[:120]}")

    overrides = {
        "attractions_order": parsed.get("attractions_order") or [a.name for a in ctx.attractions],
        "meals": parsed.get("meals") or [],
    }
    detail = rule_assemble_day_timeline(ctx, overrides=overrides)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    detail.day_budget = compute_day_budget(detail)
    # description 保留当前（用户可手动 narrative 刷新）
    existing_days = json.loads(record.days_detail_json)
    if existing_days[day_index]:
        detail.description = existing_days[day_index].get("description", "")
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/api/test_draft_endpoints.py -v
```
预期：12 个测试 PASS。

- [ ] **Step 4：提交**

```bash
git add backend/app/api/routes/trip_draft.py backend/tests/api/test_draft_endpoints.py
git commit -m "feat(api): 添加 POST /day/{n}/narrative 和 POST /day/{n}/ai-rearrange"
```

---

### Task 15：`POST /draft/{id}/finalize` SSE

**Files:**
- Modify: `backend/app/api/routes/trip_draft.py`
- Modify: `backend/tests/api/test_draft_endpoints.py`

- [ ] **Step 1：在测试文件追加**

```python
@pytest.mark.asyncio
async def test_finalize_sse_returns_trip_id(client):
    draft_id = await _seed_draft()

    fake_trip_record = type("Rec", (), {"id": 555})()
    from app.models.schemas import TripPlan, Budget
    fake_trip_plan = TripPlan(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        days=[], weather_info=[], overall_suggestions="",
        budget=Budget(),
    )

    with patch(
        "app.api.routes.trip_draft.finalize_draft",
        new=AsyncMock(return_value=(fake_trip_plan, 555)),
    ):
        async with client.stream(
            "POST", f"/api/trip/draft/{draft_id}/finalize"
        ) as resp:
            chunks = [c async for c in resp.aiter_text()]
            body = "".join(chunks)

    assert "data: " in body
    events = [
        json.loads(line.removeprefix("data: ").strip())
        for line in body.splitlines() if line.startswith("data: ")
    ]
    types = [e["type"] for e in events]
    assert "complete" in types
    complete_evt = next(e for e in events if e["type"] == "complete")
    assert complete_evt["trip_id"] == 555


@pytest.mark.asyncio
async def test_finalize_already_finalized_returns_409(client):
    draft_id = await _seed_draft()
    await trip_draft_service.mark_finalized(draft_id, trip_id=1)
    async with client.stream(
        "POST", f"/api/trip/draft/{draft_id}/finalize"
    ) as resp:
        body = "".join([c async for c in resp.aiter_text()])
    events = [
        json.loads(line.removeprefix("data: ").strip())
        for line in body.splitlines() if line.startswith("data: ")
    ]
    assert any(e["type"] == "error" for e in events)
```

- [ ] **Step 2：实现 `/finalize`**

`backend/app/api/routes/trip_draft.py` 顶部导入区追加：
```python
from ...agents.langgraph_agent.finalize.pipeline import finalize_draft
```

文件末尾追加：
```python
@router.post("/{draft_id}/finalize", summary="定稿草稿 → 写 trip_history (SSE)")
async def finalize_draft_endpoint(draft_id: str):
    async def event_generator():
        try:
            yield f"data: {json.dumps({'type':'progress','step':'preparing','message':'整理行程...'}, ensure_ascii=False)}\n\n"
            record = await trip_draft_service.get_draft(draft_id)
            if record is None:
                yield f"data: {json.dumps({'type':'error','message':'draft 不存在'}, ensure_ascii=False)}\n\n"
                return
            if record.status == "finalized":
                yield f"data: {json.dumps({'type':'error','message':'draft 已 finalized'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type':'progress','step':'synthesizer','message':'生成总体建议...'}, ensure_ascii=False)}\n\n"
            trip_plan, trip_id = await finalize_draft(draft_id, user_id=record.user_id)
            yield f"data: {json.dumps({'type':'progress','step':'saving','message':'写入历史...'}, ensure_ascii=False)}\n\n"

            payload = {
                "type": "complete",
                "trip_id": trip_id,
                "trip_plan": trip_plan.model_dump(mode="json"),
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            err = {"type": "error", "message": f"finalize 失败: {str(e)}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/api/test_draft_endpoints.py -v
```
预期：14 个测试 PASS。

- [ ] **Step 4：提交**

```bash
git add backend/app/api/routes/trip_draft.py backend/tests/api/test_draft_endpoints.py
git commit -m "feat(api): 添加 POST /api/trip/draft/{id}/finalize SSE 端点"
```

---

### Task 16：TTL 后台清理任务

**Files:**
- Modify: `backend/app/api/main.py`

- [ ] **Step 1：在 `main.py` 顶部加导入**

```python
import asyncio
from ..services import trip_draft_service
```

- [ ] **Step 2：扩展 `startup_event` 启动 TTL 清理任务**

替换现有 `startup_event` 函数末尾的 `print` 行之前，在 `print_config()` 之后插入：
```python
    # 启动草稿 TTL 清理后台任务（每 24h 跑一次）
    async def _draft_ttl_loop():
        while True:
            try:
                await trip_draft_service.delete_expired(days=30)
            except Exception as e:
                log_print(f"⚠️ draft TTL 清理失败: {e}", level="warning")
            await asyncio.sleep(24 * 3600)

    app.state.draft_ttl_task = asyncio.create_task(_draft_ttl_loop())
    log_print("✅ 草稿 TTL 清理任务已启动 (30 天保留)")
```

- [ ] **Step 3：在 `shutdown_event` 中取消任务**

替换 `shutdown_event` 函数体：
```python
@app.on_event("shutdown")
async def shutdown_event():
    print("\n" + "="*60)
    print("👋 应用正在关闭...")
    print("="*60 + "\n")
    task = getattr(app.state, "draft_ttl_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 4：手动启动看一次日志**

```bash
cd backend && python -c "
import asyncio
from app.api.main import app
async def smoke():
    pass  # FastAPI 的 startup hook 通过 TestClient 触发
print('main.py 导入成功')
"
```
预期：无 ImportError。

- [ ] **Step 5：提交**

```bash
git add backend/app/api/main.py
git commit -m "feat(api): 启动草稿 TTL 后台清理任务 (24h 周期, 30 天保留)"
```

---

## Phase 6：前端

### Task 17：前端 API 客户端方法

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1：在 `api.ts` 末尾追加 draft 相关方法**

```typescript
// ============ 草稿（骨架/详细分离）API ============

export interface DraftStreamEvent {
  type: 'init' | 'node_start' | 'node_complete' | 'progress' | 'complete' | 'error'
  message?: string
  progress?: number
  node?: string
  draft_id?: string
  data?: any
}

export async function createDraftFromSelectionsStream(
  formData: TripFormData,
  selectedAttractions: any[],
  dayAssignments: any[][] | null,
  weatherInfo: string,
  onEvent: (event: DraftStreamEvent) => void,
  options?: StreamOptions,
): Promise<void> {
  const timeout = options?.timeout || 240000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/draft/from-selections/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request: formData,
        selected_attractions: selectedAttractions,
        day_assignments: dayAssignments,
        weather_info: weatherInfo,
        user_id: 'default',
      }),
      signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') throw new Error('请求已取消或超时')
    throw error
  }
  clearTimeout(timeoutId)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)

  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法获取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event = JSON.parse(trimmed.slice(6)) as DraftStreamEvent
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') return
          } catch (e) {
            console.warn('解析 SSE 事件失败:', trimmed, e)
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}

export async function getDraft(draftId: string) {
  const resp = await apiClient.get(`/api/trip/draft/${draftId}`)
  return resp.data
}

export async function deleteDraft(draftId: string) {
  const resp = await apiClient.delete(`/api/trip/draft/${draftId}`)
  return resp.data
}

export interface DayEditBody {
  attractions_order?: string[]
  meals?: Array<Record<string, any>>
}

export async function assembleDay(
  draftId: string, dayIndex: number, body: DayEditBody = {}, force = false,
) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/assemble${force ? '?force=true' : ''}`,
    body,
  )
  return resp.data
}

export async function recomputeDay(
  draftId: string, dayIndex: number, body: DayEditBody,
) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/recompute`, body,
  )
  return resp.data
}

export async function aiRearrangeDay(
  draftId: string, dayIndex: number, hint?: string,
) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/ai-rearrange`,
    { hint: hint || null },
  )
  return resp.data
}

export async function rewriteNarrative(draftId: string, dayIndex: number) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/narrative`, {},
  )
  return resp.data
}

export async function finalizeDraftStream(
  draftId: string,
  onEvent: (event: DraftStreamEvent) => void,
  options?: StreamOptions,
): Promise<void> {
  const timeout = options?.timeout || 180000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/draft/${draftId}/finalize`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') throw new Error('请求已取消或超时')
    throw error
  }
  clearTimeout(timeoutId)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)

  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法获取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event = JSON.parse(trimmed.slice(6)) as DraftStreamEvent
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') return
          } catch {}
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}
```

- [ ] **Step 2：跑前端类型检查**

```bash
cd frontend && npx vue-tsc --noEmit
```
预期：无类型错误。

- [ ] **Step 3：提交**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(frontend): 添加 draft 系列 API 客户端方法"
```

---

### Task 18：DiscoverView 跳转改造

**Files:**
- Modify: `frontend/src/views/DiscoverView.vue`

- [ ] **Step 1：替换 `planFromSelectionsStream` 调用为 `createDraftFromSelectionsStream`**

打开 `frontend/src/views/DiscoverView.vue`，找到 import 行（约 165 行）：

```typescript
import { discoverAttractionsStream, searchAttractionManual, planFromSelectionsStream } from '@/services/api'
```

改为：
```typescript
import {
  discoverAttractionsStream, searchAttractionManual,
  createDraftFromSelectionsStream,
} from '@/services/api'
```

- [ ] **Step 2：找到 `planFromSelectionsStream(...)` 调用（约 330 行附近），改写为：**

```typescript
    await createDraftFromSelectionsStream(
      formData,
      selectedAttractions.value.map(a => ({
        name: a.name, description: a.description, address: a.address,
        category: a.category, rating: a.rating, ticket_price: a.ticket_price,
        image_url: a.image_url, location: a.location, poi_id: a.poi_id,
      })),
      dayAssignmentsToSend,
      weatherInfo.value,
      (event) => {
        progress.value = event.progress || 0
        progressMessage.value = event.message || ''
        if (event.type === 'complete' && event.draft_id) {
          router.push(`/draft/${event.draft_id}`)
        } else if (event.type === 'error') {
          message.error(event.message || '骨架生成失败')
          phase.value = 'assign'
        }
      },
    )
```

（具体变量名 `formData` / `selectedAttractions` / `dayAssignmentsToSend` / `weatherInfo` 等应沿用 DiscoverView 中已有的变量；如果命名不一致，按现有 view 内的变量名调整 — 不要凭空命名）

- [ ] **Step 3：跑 dev server 手测：发现景点 → 勾选 → 进入装配应路由到 `/draft/:id`**

```bash
cd frontend && npm run dev
```
打开浏览器走流程，确认控制台无错误。后端需同时运行（`python backend/run.py`）。

注意：此时 `/draft/:id` 路由还未注册，会显示空白页 —— 这是预期的，等 Task 19 注册后再回来手测。

- [ ] **Step 4：提交**

```bash
git add frontend/src/views/DiscoverView.vue
git commit -m "feat(frontend): DiscoverView 改为调用 createDraftFromSelectionsStream 并跳转 /draft/:id"
```

---

### Task 19：DraftView 骨架视图 + 路由

**Files:**
- Create: `frontend/src/views/DraftView.vue`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1：注册路由**

`frontend/src/main.ts` 找到路由数组（约 20-30 行），追加：
```typescript
    {
      path: '/draft/:id',
      name: 'Draft',
      component: () => import('@/views/DraftView.vue'),
      props: true,
    },
```

- [ ] **Step 2：创建 DraftView.vue 骨架**

`frontend/src/views/DraftView.vue`：
```vue
<template>
  <div class="draft-page">
    <header class="draft-hero">
      <h1>{{ draft?.city || '加载中...' }}</h1>
      <div class="meta" v-if="draft">
        {{ draft.request.start_date }} 至 {{ draft.request.end_date }} ·
        {{ draft.request.travel_days }} 天
      </div>
    </header>

    <a-spin v-if="loading" tip="加载草稿中..." />

    <main v-else-if="draft" class="draft-content">
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="itinerary" tab="行程">
          <div class="days-container">
            <DayCard
              v-for="(ctx, idx) in draft.days"
              :key="idx"
              :context="ctx"
              :detail="draft.days_detail[idx] || null"
              :is-default-expanded="idx === 0"
              @assemble="onAssemble(idx, $event)"
              @recompute="onRecompute(idx, $event)"
              @ai-rearrange="onAIRearrange(idx, $event)"
              @rewrite-narrative="onRewriteNarrative(idx)"
            />
          </div>
        </a-tab-pane>
        <a-tab-pane key="map" tab="地图">
          <div>地图占位（沿用 TabMap 组件，传 draft.days 即可）</div>
        </a-tab-pane>
        <a-tab-pane key="weather" tab="天气">
          <div>天气占位（沿用 TabWeather）</div>
        </a-tab-pane>
        <a-tab-pane key="budget" tab="预算">
          <div>预算占位：已展开 {{ assembledCount }} / {{ draft.days.length }} 天</div>
        </a-tab-pane>
      </a-tabs>

      <div class="finalize-bar">
        <a-button type="primary" size="large" :loading="finalizing"
                  @click="onFinalize">
          定稿并保存
        </a-button>
      </div>
    </main>

    <a-empty v-else description="草稿不存在或已过期" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDraft, assembleDay, recomputeDay, aiRearrangeDay,
  rewriteNarrative, finalizeDraftStream,
} from '@/services/api'
import DayCard from '@/components/draft/DayCard.vue'

const route = useRoute()
const router = useRouter()
const draftId = computed(() => route.params.id as string)

const draft = ref<any>(null)
const loading = ref(true)
const activeTab = ref('itinerary')
const finalizing = ref(false)

const assembledCount = computed(
  () => draft.value?.days_detail?.filter((d: any) => d?.is_assembled).length || 0
)

async function loadDraft() {
  loading.value = true
  try {
    draft.value = await getDraft(draftId.value)
    // 自动展开第 1 天
    if (draft.value && !draft.value.days_detail[0]) {
      await onAssemble(0, {})
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载草稿失败')
  } finally {
    loading.value = false
  }
}

async function onAssemble(idx: number, body: any) {
  try {
    const resp = await assembleDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '展开失败')
  }
}

async function onRecompute(idx: number, body: any) {
  try {
    const resp = await recomputeDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '重算失败')
  }
}

async function onAIRearrange(idx: number, hint: string) {
  try {
    const resp = await aiRearrangeDay(draftId.value, idx, hint)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'AI 重新安排失败')
  }
}

async function onRewriteNarrative(idx: number) {
  try {
    const resp = await rewriteNarrative(draftId.value, idx)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '重写叙述失败')
  }
}

async function onFinalize() {
  finalizing.value = true
  try {
    await finalizeDraftStream(draftId.value, (event) => {
      if (event.type === 'complete' && (event as any).trip_id) {
        message.success('定稿成功')
        router.replace(`/trip/${(event as any).trip_id}`)
      } else if (event.type === 'error') {
        message.error(event.message || '定稿失败')
      }
    })
  } finally {
    finalizing.value = false
  }
}

onMounted(loadDraft)
</script>

<style scoped>
.draft-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.draft-hero { margin-bottom: 24px; }
.draft-hero h1 { font-size: 32px; margin-bottom: 8px; }
.meta { color: #888; }
.days-container { display: flex; flex-direction: column; gap: 16px; }
.finalize-bar {
  position: sticky; bottom: 0; background: white;
  padding: 16px; border-top: 1px solid #eee; text-align: right;
}
</style>
```

- [ ] **Step 3：创建占位 DayCard 组件**

`frontend/src/components/draft/DayCard.vue`：
```vue
<template>
  <a-card>
    <template #title>
      <div class="day-header">
        <span>第 {{ context.day_index + 1 }} 天 · {{ context.date }}</span>
        <a-tag v-if="context.weather">
          {{ context.weather.day_weather }} {{ context.weather.day_temp }}°C
        </a-tag>
      </div>
    </template>
    <template #extra>
      <a-button v-if="!isExpanded" type="link" @click="onExpand">展开装配 →</a-button>
      <template v-else>
        <a-button type="link" @click="onAIRearrange">AI 重新安排</a-button>
        <a-button type="link" @click="$emit('rewrite-narrative')">重写叙述</a-button>
      </template>
    </template>

    <div v-if="isExpanded && detail">
      <div v-if="detail.description" class="narrative">
        <div v-html="renderedDescription"></div>
      </div>
      <ul class="timeline">
        <li v-for="(item, i) in detail.timeline_order" :key="i" :class="item.kind">
          <strong>{{ kindLabel(item.kind) }}</strong> {{ item.ref_name }}
        </li>
      </ul>
      <div class="route-info" v-if="detail.route_segments?.length">
        <h4>路线</h4>
        <ul>
          <li v-for="(seg, i) in detail.route_segments" :key="i">
            {{ seg.from_name }} → {{ seg.to_name }}: {{ seg.distance }} ({{ seg.duration }}, {{ seg.mode }})
          </li>
        </ul>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Props {
  context: any
  detail: any | null
  isDefaultExpanded: boolean
}
const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'assemble', body: any): void
  (e: 'recompute', body: any): void
  (e: 'ai-rearrange', hint: string): void
  (e: 'rewrite-narrative'): void
}>()

const isExpanded = ref(props.isDefaultExpanded)

watch(() => props.detail, (d) => {
  if (d && d.is_assembled) isExpanded.value = true
})

function onExpand() {
  isExpanded.value = true
  if (!props.detail) emit('assemble', {})
}

function onAIRearrange() {
  emit('ai-rearrange', '')
}

function kindLabel(kind: string) {
  return { hotel: '🏨', attraction: '📍', meal: '🍴' }[kind] || '·'
}

const renderedDescription = computed(() => {
  // 简易 markdown 渲染：暴露给后续 Task 21 升级为 marked
  return (props.detail?.description || '').replace(/\n/g, '<br>')
})
</script>

<style scoped>
.day-header { display: flex; gap: 8px; align-items: center; }
.narrative { padding: 12px 0; line-height: 1.6; }
.timeline { list-style: none; padding: 0; }
.timeline li { padding: 4px 0; }
.route-info { margin-top: 12px; }
.route-info h4 { margin-bottom: 4px; }
</style>
```

- [ ] **Step 4：手测**

```bash
# Terminal 1
cd backend && python run.py

# Terminal 2
cd frontend && npm run dev
```

打开浏览器：
1. `/` 填写表单 → 进 `/discover`
2. 勾选 3-5 个景点 → 点"开始规划"
3. 等 SSE 完成 → 自动跳 `/draft/:id`
4. 第 1 天卡片应自动展开显示景点和默认餐厅 + 一段 markdown 叙述
5. 点"展开装配"展开其他天

如果某步失败，看浏览器 console 和后端日志定位。

- [ ] **Step 5：提交**

```bash
git add frontend/src/views/DraftView.vue frontend/src/components/draft/DayCard.vue frontend/src/main.ts
git commit -m "feat(frontend): 添加 /draft/:id 装配器主视图和 DayCard 组件"
```

---

### Task 20：DayCard 拖拽 + 添加用餐弹层

**Files:**
- Modify: `frontend/src/components/draft/DayCard.vue`
- Create: `frontend/src/components/draft/AddDiningPopover.vue`

- [ ] **Step 1：在 `DayCard.vue` template 中把 timeline 改成可拖拽景点 + 可删除餐厅 + "+ 加用餐"按钮**

替换 timeline 块为：
```vue
      <div class="timeline-editor">
        <draggable v-model="orderedAttractions" item-key="name" handle=".drag-handle"
                   @end="onOrderChange">
          <template #item="{ element }">
            <div class="attr-row">
              <span class="drag-handle">⋮⋮</span>
              <span class="kind">📍</span>
              <span class="name">{{ element.name }}</span>
              <AddDiningPopover
                :pool="context.dining_pool"
                :insert-after="element.name"
                @add="onAddMeal"
              />
            </div>
          </template>
        </draggable>
        <div v-for="m in detail?.meals || []" :key="m.name + m.category" class="meal-row">
          <span class="kind">🍴</span>
          <span class="name">{{ m.name }}</span>
          <a-tag>{{ m.category || m.type }}</a-tag>
          <a-button size="small" danger @click="onRemoveMeal(m)">删除</a-button>
        </div>
      </div>
```

并在 `<script setup>` 中追加：
```typescript
import draggable from 'vuedraggable'
import AddDiningPopover from './AddDiningPopover.vue'

const orderedAttractions = ref<any[]>([])

watch(() => props.detail, (d) => {
  if (d?.attractions) orderedAttractions.value = [...d.attractions]
}, { immediate: true })

let debounceTimer: any = null
function debouncedRecompute() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('recompute', {
      attractions_order: orderedAttractions.value.map(a => a.name),
      meals: (props.detail?.meals || []).map((m: any) => ({
        ...m,
        insert_after: m.insert_after || (orderedAttractions.value[
          Math.max(orderedAttractions.value.length / 2 - 1, 0) | 0
        ]?.name || ''),
      })),
    })
  }, 500)
}

function onOrderChange() { debouncedRecompute() }

function onAddMeal(meal: any) {
  const currentMeals = (props.detail?.meals || []).map((m: any) => ({ ...m }))
  currentMeals.push(meal)
  emit('recompute', {
    attractions_order: orderedAttractions.value.map(a => a.name),
    meals: currentMeals,
  })
}

function onRemoveMeal(meal: any) {
  const remaining = (props.detail?.meals || [])
    .filter((m: any) => !(m.name === meal.name && (m.category || m.type) === (meal.category || meal.type)))
  emit('recompute', {
    attractions_order: orderedAttractions.value.map(a => a.name),
    meals: remaining,
  })
}
```

- [ ] **Step 2：安装 vuedraggable**

```bash
cd frontend && npm install vuedraggable@next
```

- [ ] **Step 3：创建 `AddDiningPopover.vue`**

`frontend/src/components/draft/AddDiningPopover.vue`：
```vue
<template>
  <a-popover trigger="click" placement="bottom">
    <template #content>
      <a-tabs v-model:activeKey="activeCat" size="small" style="width: 320px">
        <a-tab-pane v-for="cat in categories" :key="cat" :tab="catLabel[cat]">
          <div v-if="pool[cat]?.length">
            <div v-for="c in pool[cat]" :key="c.name" class="candidate"
                 @click="onPick(cat, c)">
              <strong>{{ c.name }}</strong>
              <span v-if="c.rating">{{ c.rating }}⭐</span>
              <span v-if="c.avg_cost">¥{{ c.avg_cost }}</span>
              <span v-if="c.distance">{{ c.distance }}</span>
            </div>
          </div>
          <a-empty v-else description="无候选，可自定义" />
          <a-divider />
          <a-input v-model:value="customName" :placeholder="`自定义 ${catLabel[cat]} 名称`" />
          <a-button block @click="onPickCustom(cat)" :disabled="!customName">添加自定义</a-button>
        </a-tab-pane>
      </a-tabs>
    </template>
    <a-button size="small">+ 加用餐</a-button>
  </a-popover>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  pool: any
  insertAfter: string
}>()
const emit = defineEmits<{
  (e: 'add', meal: any): void
}>()

const categories = ['main', 'snack', 'dessert', 'cafe', 'late_night']
const catLabel: Record<string, string> = {
  main: '正餐', snack: '小吃', dessert: '甜品', cafe: '咖啡', late_night: '夜宵',
}
const activeCat = ref('main')
const customName = ref('')

function onPick(cat: string, c: any) {
  emit('add', { ...c, category: cat, insert_after: props.insertAfter })
}

function onPickCustom(cat: string) {
  emit('add', {
    name: customName.value, category: cat,
    source: 'user_custom', insert_after: props.insertAfter,
  })
  customName.value = ''
}
</script>

<style scoped>
.candidate {
  display: flex; gap: 8px; padding: 6px 4px; cursor: pointer;
  border-radius: 4px;
}
.candidate:hover { background: #f0f0f0; }
</style>
```

- [ ] **Step 4：手测**

后端 + 前端都跑起来，进入 `/draft/:id`：
1. 拖拽景点顺序，观察 500ms 后 day_detail 刷新（route_segments 应更新）
2. 点 "+ 加用餐" 在某景点后加一个小吃，应立即出现在 meals 列表
3. 点餐厅旁"删除"，应消失

- [ ] **Step 5：提交**

```bash
git add frontend/src/components/draft/DayCard.vue \
       frontend/src/components/draft/AddDiningPopover.vue \
       frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): DayCard 支持景点拖拽 + AddDiningPopover 加餐弹层"
```

---

### Task 21：AI Rearrange + 叙述 markdown 渲染

**Files:**
- Modify: `frontend/src/components/draft/DayCard.vue`

- [ ] **Step 1：安装 marked**

```bash
cd frontend && npm install marked
```

- [ ] **Step 2：在 DayCard.vue `<script setup>` 顶部添加导入和改写 renderedDescription**

```typescript
import { marked } from 'marked'

const renderedDescription = computed(() => {
  return marked.parse(props.detail?.description || '') as string
})
```

- [ ] **Step 3：AI Rearrange 弹一个 prompt 输入框**

把 `onAIRearrange()` 改为：
```typescript
async function onAIRearrange() {
  const { Modal } = await import('ant-design-vue')
  Modal.confirm({
    title: 'AI 重新安排',
    content: () => h(/* simple input modal */),
    onOk: async (close) => {
      emit('ai-rearrange', userHint.value)
      close()
    },
  })
}
```

或者更简化：用 `prompt()` 浏览器原生：
```typescript
function onAIRearrange() {
  const hint = window.prompt('AI 重排提示（可选，比如"我想吃辣的"）：', '')
  if (hint === null) return
  emit('ai-rearrange', hint || '')
}
```

（用浏览器 prompt 更简洁，Modal 也可以等后续美化）

- [ ] **Step 4：手测**

`/draft/:id` 页面：
1. 第 1 天叙述应渲染为带格式的 markdown
2. 点 "AI 重新安排" → 输入 "我想吃辣的" → 几秒后 day_detail 整体替换

- [ ] **Step 5：提交**

```bash
git add frontend/src/components/draft/DayCard.vue frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): DayCard 用 marked 渲染叙述，AI 重排接 prompt 输入"
```

---

### Task 22：手测脚本 + 文档

**Files:**
- Create: `backend/scripts/manual_draft_demo.py`

- [ ] **Step 1：创建手测脚本**

`backend/scripts/manual_draft_demo.py`：
```python
"""手测脚本：跑完整 draft 流程，每一步 dump 到 /tmp/draft_*.json

需后端服务已启动 (python run.py)。
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
OUT = Path("/tmp")


async def main():
    async with httpx.AsyncClient(timeout=180.0) as client:
        # 1. 跑 from-selections/stream
        body = {
            "request": {
                "city": "北京", "start_date": "2026-06-01", "end_date": "2026-06-02",
                "travel_days": 2, "transportation": "公共交通",
                "accommodation": "经济型酒店", "preferences": ["历史文化"],
                "food_preference": "本地特色",
            },
            "selected_attractions": [
                {"name": "故宫博物院", "location": {"longitude": 116.397128, "latitude": 39.916527}},
                {"name": "颐和园", "location": {"longitude": 116.273, "latitude": 39.999}},
            ],
            "day_assignments": None,
            "weather_info": "",
            "user_id": "manual_test",
        }
        draft_id = None
        async with client.stream(
            "POST", f"{BASE}/api/trip/draft/from-selections/stream",
            json=body,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    print("[SSE]", evt.get("type"), evt.get("message", "")[:60])
                    if evt.get("type") == "complete":
                        draft_id = evt.get("draft_id")
        assert draft_id, "未拿到 draft_id"
        print(f"\n✅ 草稿 ID: {draft_id}")

        # 2. GET draft
        r = await client.get(f"{BASE}/api/trip/draft/{draft_id}")
        (OUT / f"draft_{draft_id}_skeleton.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2)
        )
        print(f"📝 dump → /tmp/draft_{draft_id}_skeleton.json")

        # 3. assemble day 0
        r = await client.post(f"{BASE}/api/trip/draft/{draft_id}/day/0/assemble", json={})
        (OUT / f"draft_{draft_id}_day0_assembled.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2)
        )
        print(f"📝 dump → /tmp/draft_{draft_id}_day0_assembled.json")

        # 4. recompute day 0 with re-ordered attractions
        r = await client.post(
            f"{BASE}/api/trip/draft/{draft_id}/day/0/recompute",
            json={"attractions_order": ["颐和园", "故宫博物院"], "meals": []},
        )
        print(f"  → recompute: {len(r.json()['day_detail']['route_segments'])} segments")

        # 5. finalize
        async with client.stream(
            "POST", f"{BASE}/api/trip/draft/{draft_id}/finalize",
        ) as resp:
            trip_id = None
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    print("[FIN]", evt.get("type"))
                    if evt.get("type") == "complete":
                        trip_id = evt.get("trip_id")
            assert trip_id, "finalize 未返回 trip_id"
            print(f"\n✅ 已定稿: trip_id={trip_id}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2：跑一次**

后端启动后：
```bash
cd backend && python scripts/manual_draft_demo.py
```
预期：输出 SSE 事件流，最后打印 `✅ 已定稿: trip_id=NNN`，`/tmp/draft_*.json` 文件存在且包含完整字段。

- [ ] **Step 3：提交**

```bash
git add backend/scripts/manual_draft_demo.py
git commit -m "chore: 添加 manual_draft_demo 手测脚本

跑完整 draft 流程（骨架 → assemble → recompute → finalize），
每步产物 dump 到 /tmp/draft_*.json 便于人工对比。"
```

---

## 收尾验证

- [ ] **运行全部后端测试**

```bash
cd backend && pytest -v
```
预期：全部 PASS，包括新增的 ~30 个测试和旧的（旧 plan_trip 一次性路径相关测试因死代码保留也应继续通过）。

- [ ] **运行前端类型检查**

```bash
cd frontend && npx vue-tsc --noEmit
```
预期：无类型错误。

- [ ] **前端构建**

```bash
cd frontend && npm run build
```
预期：构建成功，输出到 `dist/`。

- [ ] **完整手测一遍 §22 流程**

确认骨架→装配→拖拽→AI→定稿全链路无异常。

---

## 自检：是否覆盖了 spec 的所有要点

- ✅ §1 背景与问题 — 通过 Task 5（骨架图重构）和 Task 13（recompute 端点）解决三类痛点
- ✅ §2 目标/非目标 — `plan_trip_stream` 死代码保留不动，仅重构 planning_app
- ✅ §3 决策表 — 10 项决策全部在 Task 1-22 中落地
- ✅ §4 数据流 — Task 5 骨架图 + Task 10-15 API + Task 19-21 前端覆盖
- ✅ §5 数据模型 — Task 1 schemas / Task 2 ORM / Task 3 service
- ✅ §6 API 端点 — Task 10-15 全 8 个端点（含 `/recompute` 合并）
- ✅ §7 graph 重构 — Task 5 骨架图 + Task 6-8 assemble + Task 9 finalize
- ✅ §8 错误处理 — Task 4 dining 失败隔离、Task 9 finalize 兜底、Task 11-15 各 4xx
- ✅ §9 前端 UX — Task 18 DiscoverView 跳转、Task 19-21 DraftView 完整交互
- ✅ §10 测试 — Task 1, 2, 3, 4, 6, 7, 8, 9, 11-15 均含 pytest；Task 22 手测脚本
- ✅ §11 实施顺序 — 本计划即按该顺序展开

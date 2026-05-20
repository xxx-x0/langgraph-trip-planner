# Attractions Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace attraction discovery via Bing/DuckDuckGo plus LLM extraction with a shared AMap POI cache backed by the existing SQLite database.

**Architecture:** Add an `AttractionsCacheService` that owns AMap fetching, category normalization, SQLite upsert/query, and admin refresh/clear operations. LangGraph nodes call the service and keep downstream `attractions_info` compatible with existing cluster/route/generation nodes.

**Tech Stack:** FastAPI, LangGraph, async SQLAlchemy, SQLite/aiosqlite, Pydantic, pytest with `AsyncMock`.

---

## File Structure

- Modify `backend/app/models/db_models.py`: add the `AttractionCache` ORM model and indexes.
- Create `backend/app/services/attractions_cache_service.py`: dataclass DTO, AMap result parsing, cache query/upsert, category mapping, and admin operations.
- Modify `backend/app/agents/langgraph_agent/nodes/search.py`: replace the web-search/extract/geocode trio with `search_attractions_node`, while keeping weather, hotel, and free-text analysis.
- Modify `backend/app/agents/langgraph_agent/nodes/discovery.py`: replace extraction/geocode batching with `search_attractions_discovery_node`.
- Modify `backend/app/agents/langgraph_agent/nodes/__init__.py`: export the new node names.
- Modify `backend/app/agents/langgraph_agent/graph.py`: simplify both graph topologies and update stream progress labels/state initialization.
- Modify `backend/app/agents/langgraph_agent/state.py`: remove `raw_search_results`, `extracted_pois`, and `_geocode_batches`.
- Create `backend/app/api/routes/admin.py`: add cache refresh, clear, and stats endpoints.
- Modify `backend/app/api/main.py`: register the admin router.
- Modify `backend/app/api/routes/trip_lg.py`: update health-check graph-node list.
- Modify `frontend/src/components/PlanProgress.vue`: rename the attraction progress step and remove obsolete node mapping.
- Modify `backend/requirements.txt`: remove DuckDuckGo/DDGS/LangChain community dependencies if no longer referenced.
- Create `backend/tests/services/test_attractions_cache_service.py`: service tests around parsing, cache hits/misses, upsert, filtering, and admin methods.
- Create `backend/tests/agents/test_search_attractions_node.py`: main node tests.
- Create `backend/tests/agents/test_search_attractions_discovery_node.py`: discovery node tests.
- Create `backend/tests/api/test_admin_attractions.py`: admin route tests.
- Replace or update stale `backend/tests/agents/test_trip_planner.py` imports that reference the old HelloAgents graph.

## Task 1: ORM Model And Service Helpers

**Files:**
- Modify: `backend/app/models/db_models.py`
- Create: `backend/app/services/attractions_cache_service.py`
- Test: `backend/tests/services/test_attractions_cache_service.py`

- [ ] **Step 1: Write helper tests**

Add tests for category mapping, coordinate parsing, coordinate validation, and AMap POI normalization:

```python
import pytest

from app.services.attractions_cache_service import (
    _extract_location,
    _is_valid_coordinate,
    _normalize_category,
    _normalize_poi,
)


@pytest.mark.parametrize(
    ("amap_type", "expected"),
    [
        ("风景名胜;风景名胜;公园广场", "自然风光"),
        ("科教文化服务;博物馆", "历史文化"),
        ("购物服务;购物相关场所", "购物"),
        ("餐饮服务;中餐厅", "美食街区"),
        ("地名地址信息", "其他"),
    ],
)
def test_normalize_category(amap_type, expected):
    assert _normalize_category(amap_type) == expected


def test_extract_location_from_string():
    assert _extract_location("116.397128,39.916527") == (116.397128, 39.916527)


def test_extract_location_from_dict():
    assert _extract_location({"longitude": 116.397128, "latitude": 39.916527}) == (116.397128, 39.916527)


def test_invalid_coordinate_outside_china_bounds():
    assert _is_valid_coordinate(151.2, -33.8) is False


def test_normalize_poi_keeps_core_fields():
    poi = {
        "id": "B000A8UIN8",
        "name": "故宫博物院",
        "address": "北京市东城区景山前街4号",
        "location": "116.397128,39.916527",
        "type": "风景名胜;风景名胜;风景名胜",
        "biz_ext": {"rating": "4.8", "cost": "60"},
        "photos": [{"url": "https://example.com/gugong.jpg"}],
    }

    normalized = _normalize_poi("北京", poi)

    assert normalized["city"] == "北京"
    assert normalized["name"] == "故宫博物院"
    assert normalized["poi_id"] == "B000A8UIN8"
    assert normalized["longitude"] == 116.397128
    assert normalized["latitude"] == 39.916527
    assert normalized["category"] == "自然风光"
    assert normalized["rating"] == 4.8
    assert normalized["ticket_price"] == "60"
    assert normalized["image_url"] == "https://example.com/gugong.jpg"
```

- [ ] **Step 2: Run helper tests to confirm failure**

Run: `python -m pytest backend/tests/services/test_attractions_cache_service.py -q`

Expected: import failure for `app.services.attractions_cache_service`.

- [ ] **Step 3: Add ORM model**

Add `UniqueConstraint` to the SQLAlchemy imports and add this model after `UserPreferenceRecord`:

```python
class AttractionCache(Base):
    __tablename__ = "attractions_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    poi_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    amap_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
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

- [ ] **Step 4: Add service helper skeleton**

Create `attractions_cache_service.py` with `CachedAttraction`, category map, `_extract_location`, `_is_valid_coordinate`, `_normalize_category`, `_safe_float`, `_extract_photo`, and `_normalize_poi`.

- [ ] **Step 5: Run helper tests**

Run: `python -m pytest backend/tests/services/test_attractions_cache_service.py -q`

Expected: helper tests pass; service method tests are not present yet.

## Task 2: Cache Service DB And AMap Paths

**Files:**
- Modify: `backend/app/services/attractions_cache_service.py`
- Test: `backend/tests/services/test_attractions_cache_service.py`

- [ ] **Step 1: Add service DB tests**

Extend the service test file with async tests for:

```python
@pytest.mark.asyncio
async def test_get_attractions_returns_cache_hit(service_with_rows):
    result = await service_with_rows.get_attractions("北京", min_count=2)
    assert [p.name for p in result][:2] == ["故宫博物院", "天坛公园"]


@pytest.mark.asyncio
async def test_get_attractions_fetches_when_cache_empty(service_with_empty_db, mock_amap_tool):
    mock_amap_tool.ainvoke.return_value = {"pois": [{"name": "故宫博物院", "location": "116.397128,39.916527", "type": "风景名胜"}]}
    result = await service_with_empty_db.get_attractions("北京", min_count=1)
    assert [p.name for p in result] == ["故宫博物院"]


@pytest.mark.asyncio
async def test_category_filter_falls_back_to_all_when_too_few(service_with_rows):
    result = await service_with_rows.get_attractions("北京", min_count=2, categories=["购物"])
    assert len(result) >= 2
```

Use an in-memory async SQLite engine and patch `get_langchain_amap_service` to return an object whose `get_tool("maps_text_search")` returns `mock_amap_tool`.

- [ ] **Step 2: Run DB tests to confirm failure**

Run: `python -m pytest backend/tests/services/test_attractions_cache_service.py -q`

Expected: failures for unimplemented service methods.

- [ ] **Step 3: Implement `AttractionsCacheService`**

Implement:

```python
class AttractionsCacheService:
    def __init__(self, session_factory=async_session):
        self.session_factory = session_factory

    async def get_attractions(self, city: str, min_count: int = 20, categories: list[str] | None = None) -> list[CachedAttraction]:
        cached = await self._query_db(city, categories)
        if len(cached) >= min_count:
            return cached
        all_cached = await self._query_db(city, None)
        if categories and len(cached) < min_count and len(all_cached) >= min_count:
            return all_cached
        try:
            pois = await self._fetch_from_amap(city)
            await self._persist(city, pois)
        except Exception:
            if all_cached:
                return all_cached
            raise
        refreshed = await self._query_db(city, categories)
        if categories and len(refreshed) < min_count:
            return await self._query_db(city, None)
        return refreshed
```

Also implement `_query_db`, `_fetch_from_amap`, `_persist`, `find_by_name`, `refresh_city`, `clear_city`, `get_stats`, and `get_attractions_cache_service`.

- [ ] **Step 4: Verify service tests**

Run: `python -m pytest backend/tests/services/test_attractions_cache_service.py -q`

Expected: all service tests pass.

## Task 3: Main Trip Attraction Node

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/search.py`
- Modify: `backend/app/agents/langgraph_agent/nodes/__init__.py`
- Test: `backend/tests/agents/test_search_attractions_node.py`

- [ ] **Step 1: Add node tests**

Create tests asserting:

```python
@pytest.mark.asyncio
async def test_search_attractions_node_returns_selected_pois_and_info(mock_trip_request, cached_attractions):
    service = AsyncMock()
    service.get_attractions.return_value = cached_attractions
    service.find_by_name.return_value = None

    with patch("app.agents.langgraph_agent.nodes.search.get_attractions_cache_service", return_value=service):
        result = await search_attractions_node({"request": mock_trip_request, "errors": []})

    assert [p["name"] for p in result["selected_pois"]] == ["故宫博物院", "天坛公园"]
    assert "pois" in result["attractions_info"]
    service.get_attractions.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_attractions_node_puts_must_visit_first(mock_trip_request, cached_attractions):
    mock_trip_request.free_text_input = "一定要去颐和园"
    service = AsyncMock()
    service.get_attractions.return_value = cached_attractions
    service.find_by_name.return_value = CachedAttraction(name="颐和园", address="北京市海淀区", longitude=116.273, latitude=39.999, category="历史文化")

    with patch("app.agents.langgraph_agent.nodes.search.get_attractions_cache_service", return_value=service):
        with patch("app.agents.langgraph_agent.nodes.search.analyze_free_text", AsyncMock(return_value={"attractions": ["颐和园"], "food_preferences": [], "accommodation_preferences": [], "general_suggestions": []})):
            result = await search_attractions_node({"request": mock_trip_request, "errors": []})

    assert result["selected_pois"][0]["name"] == "颐和园"
```

- [ ] **Step 2: Run node tests to confirm failure**

Run: `python -m pytest backend/tests/agents/test_search_attractions_node.py -q`

Expected: import failure for `search_attractions_node`.

- [ ] **Step 3: Replace old search trio**

Remove `web_search_attractions_node`, `extract_attractions_node`, `geocode_attractions_node`, DuckDuckGo/Bing imports, and `WEB_SEARCH_ATTRACTION_PROMPT`/`EXTRACT_ATTRACTIONS_PROMPT` imports from `search.py`.

Add `_preferences_to_categories`, `_format_pois_as_attractions_info`, and `search_attractions_node`.

- [ ] **Step 4: Export new node**

Update `nodes/__init__.py` to import `search_attractions_node` instead of the old trio.

- [ ] **Step 5: Verify node tests**

Run: `python -m pytest backend/tests/agents/test_search_attractions_node.py -q`

Expected: all main node tests pass.

## Task 4: Discovery Node And Graph Topology

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/discovery.py`
- Modify: `backend/app/agents/langgraph_agent/graph.py`
- Modify: `backend/app/agents/langgraph_agent/state.py`
- Test: `backend/tests/agents/test_search_attractions_discovery_node.py`

- [ ] **Step 1: Add discovery node tests**

Create tests asserting:

```python
@pytest.mark.asyncio
async def test_search_attractions_discovery_node_returns_service_attractions(mock_trip_request, cached_attractions):
    service = AsyncMock()
    service.get_attractions.return_value = cached_attractions

    with patch("app.agents.langgraph_agent.nodes.discovery.get_attractions_cache_service", return_value=service):
        result = await search_attractions_discovery_node({"request": mock_trip_request, "errors": []})

    assert len(result["discovered_attractions"]) == len(cached_attractions)
    assert result["discovered_attractions"][0]["name"] == cached_attractions[0].name
    service.get_attractions.assert_awaited_once_with(city="北京", min_count=40, categories=["历史文化"])
```

- [ ] **Step 2: Run discovery tests to confirm failure**

Run: `python -m pytest backend/tests/agents/test_search_attractions_discovery_node.py -q`

Expected: import failure for `search_attractions_discovery_node`.

- [ ] **Step 3: Replace discovery extraction/geocode nodes**

In `discovery.py`, keep `gather_discovery_node` and replace `extract_attractions_expanded_node`, `geocode_dispatch_node`, and `geocode_batch_node` with `search_attractions_discovery_node`.

- [ ] **Step 4: Simplify graphs and state**

Update `create_trip_planner_graph()` so `START` connects to `search_attractions`, `search_weather`, and `search_hotel`, and `["search_attractions", "search_weather", "search_hotel"]` gathers into `gather_search`.

Update `create_discovery_graph()` so `START` connects to `search_attractions_discovery` and `search_weather`, and both gather into `gather_discovery`.

Remove `_route_after_geocode_batch`, `raw_search_results`, `extracted_pois`, and `_geocode_batches` from state builders and `DiscoveryState`.

- [ ] **Step 5: Update progress labels**

Rename stream labels to user-facing AMap cache language:

```python
"search_attractions": {"message": "🔍 正在查询景点库...", "progress": 15, "done_msg": "✅ 景点查询完成"}
"search_attractions_discovery": {"message": "🔍 正在查询景点库...", "progress": 70, "done_msg": "✅ 景点发现完成"}
```

- [ ] **Step 6: Verify discovery tests**

Run: `python -m pytest backend/tests/agents/test_search_attractions_discovery_node.py -q`

Expected: all discovery tests pass.

## Task 5: Admin API

**Files:**
- Create: `backend/app/api/routes/admin.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/api/test_admin_attractions.py`

- [ ] **Step 1: Add API tests**

Create tests using FastAPI `TestClient` and `AsyncMock`:

```python
def test_refresh_city_rejects_empty_city():
    response = client.post("/api/admin/attractions/refresh", params={"city": "   "})
    assert response.status_code == 400


def test_refresh_city_success(mock_service):
    mock_service.refresh_city.return_value = 12
    response = client.post("/api/admin/attractions/refresh", params={"city": "北京"})
    assert response.status_code == 200
    assert response.json() == {"city": "北京", "refreshed": 12}


def test_clear_city_success(mock_service):
    mock_service.clear_city.return_value = 8
    response = client.post("/api/admin/attractions/clear", params={"city": "北京"})
    assert response.status_code == 200
    assert response.json() == {"city": "北京", "cleared": 8}


def test_stats_success(mock_service):
    mock_service.get_stats.return_value = {"cities": 1, "attractions": 12}
    response = client.get("/api/admin/attractions/stats")
    assert response.status_code == 200
    assert response.json() == {"cities": 1, "attractions": 12}
```

- [ ] **Step 2: Run API tests to confirm failure**

Run: `python -m pytest backend/tests/api/test_admin_attractions.py -q`

Expected: route import or 404 failure.

- [ ] **Step 3: Implement admin router**

Create `admin.py` with:

```python
router = APIRouter(prefix="/admin/attractions", tags=["admin"])
```

Add `POST /refresh`, `POST /clear`, and `GET /stats`. Validate blank `city` with `HTTPException(status_code=400, detail="city is required")`.

- [ ] **Step 4: Register route**

Import `admin` in `main.py` and add:

```python
app.include_router(admin.router, prefix="/api")
```

- [ ] **Step 5: Verify API tests**

Run: `python -m pytest backend/tests/api/test_admin_attractions.py -q`

Expected: all admin tests pass.

## Task 6: Cleanup, Compatibility, And Existing Tests

**Files:**
- Modify: `backend/app/api/routes/trip_lg.py`
- Modify: `frontend/src/components/PlanProgress.vue`
- Modify: `backend/requirements.txt`
- Modify: `backend/tests/agents/test_trip_planner.py`

- [ ] **Step 1: Update health and UI labels**

Replace graph node names in `trip_lg.py` and `PlanProgress.vue`:

```python
"search_attractions"
```

Use the label `🔍 查询景点库`.

- [ ] **Step 2: Remove obsolete dependencies**

Remove these requirement lines when `rg` confirms no imports remain:

```text
duckduckgo-search>=6.0.0
ddgs>=9.0.0
langchain-community>=0.3.0
```

- [ ] **Step 3: Replace stale tests**

Rewrite `backend/tests/agents/test_trip_planner.py` so it covers current exported API only: `_parse_response`, `_create_fallback_plan`, and `LangGraphTripPlanner.plan_trip` fallback/success. Remove imports for `quality_gate_node`, `route_after_quality_gate`, and old state fields.

- [ ] **Step 4: Run targeted test suite**

Run:

```bash
python -m pytest \
  backend/tests/services/test_attractions_cache_service.py \
  backend/tests/agents/test_search_attractions_node.py \
  backend/tests/agents/test_search_attractions_discovery_node.py \
  backend/tests/api/test_admin_attractions.py \
  backend/tests/agents/test_trip_planner.py \
  -q
```

Expected: all targeted tests pass.

- [ ] **Step 5: Run static syntax verification**

Run:

```bash
python -m compileall backend/app backend/tests
```

Expected: all files compile without syntax errors.

## Task 7: Final Integration Check

**Files:**
- All modified files

- [ ] **Step 1: Search for removed node names**

Run:

```bash
rg "web_search_attractions|extract_attractions|geocode_attractions|raw_search_results|_geocode_batches|DuckDuckGo|ddg|bing" backend frontend
```

Expected: only `backend/app/services/bing_mcp_service.py` and non-attraction Bing configuration references remain.

- [ ] **Step 2: Search for new node names**

Run:

```bash
rg "search_attractions|search_attractions_discovery|AttractionCache|AttractionsCacheService" backend frontend
```

Expected: graph, nodes, service, tests, health output, and progress UI all reference the new names.

- [ ] **Step 3: Review diff**

Run:

```bash
git diff --stat
git diff -- backend/app/agents/langgraph_agent backend/app/services backend/app/models backend/app/api backend/tests frontend/src/components/PlanProgress.vue backend/requirements.txt
```

Expected: diff is scoped to the attraction-cache implementation and test updates.

- [ ] **Step 4: Record verification limits**

If `pytest` is unavailable in the local Python environment, record the exact failure (`No module named pytest`) and rely on `compileall` plus code review for this session.


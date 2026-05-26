# 发现页与规划流程改进 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现发现页扩容与分页、AI 攻略选景、日程时长均衡、删除独立加载页改用结果页骨架屏、修复酒店名与预算两个问题

**Architecture:** 后端在现有 LangGraph 节点旁新增可重入的"加载更多"和"AI 选景"端点；主流程的 `cluster_attractions_node` 接入已有的 `_rebalance_by_duration`；前端 `Result.vue` 改为 SSE 直接消费者（骨架屏渐进填充），`DiscoverView.vue` 移除 `PlanProgress` 全屏组件；酒店名前端工具清理 + 后端 `_parse_aigohotel_hotels` 补 `estimated_cost` 字段。

**Tech Stack:** FastAPI + LangGraph（后端）；Vue 3 + Ant Design Vue + Vite（前端）；pytest（后端测试）

**Spec:** `docs/superpowers/specs/2026-05-26-discovery-planning-improvements-design.md`

**重要发现（调整 spec 中的实现策略）：**
- `_rebalance_by_duration` 已存在于 `backend/app/agents/langgraph_agent/utils/geo.py:240`，已被 `POST /api/trip/plan/preview-day-assignment` 调用
- 主流程的 `cluster_attractions_node` (`nodes/cluster.py`) 未接入此函数 → 模块 3 任务变为"在主流程接入 + 让主流程拿到 durations"
- 该模块预算大幅缩小，无需新写算法

---

## Phase 1 — 酒店预算 bug 与名字清理（Modules 5A + 5B）

风险最低、收益最直接，先做。

### Task 1.1: 修复酒店预算 0 元（后端）

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/search.py:585-690`（`_parse_aigohotel_hotels` 函数）
- Test: `backend/tests/agents/test_search_hotels.py`

- [ ] **Step 1: 写失败测试 — 验证 estimated_cost 从 price 推出**

在 `backend/tests/agents/test_search_hotels.py` 末尾追加：

```python
def test_parse_aigohotel_hotels_fills_estimated_cost_from_price():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "测试酒店",
            "totalPrice": "688.5",
        }],
    })
    assert hotels[0]["estimated_cost"] == 688


def test_parse_aigohotel_hotels_fills_estimated_cost_from_price_obj():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "测试酒店2",
            "price": {"hasPrice": True, "lowestPrice": 350, "currency": "CNY"},
        }],
    })
    assert hotels[0]["estimated_cost"] == 350


def test_parse_aigohotel_hotels_estimated_cost_falls_back_to_star_rating():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "无价酒店",
            "starRating": 4,
        }],
    })
    # 4 星 × 200 = 800
    assert hotels[0]["estimated_cost"] == 800


def test_parse_aigohotel_hotels_estimated_cost_default_when_no_signals():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "纯净酒店",
        }],
    })
    # 无 price 也无 star → 默认 500
    assert hotels[0]["estimated_cost"] == 500
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/agents/test_search_hotels.py -v
```

Expected: 4 个新测试全部 FAIL，错误信息含 `KeyError: 'estimated_cost'` 或 `assert ... == 688` 之类断言失败。

- [ ] **Step 3: 在 `_parse_aigohotel_hotels` 末尾、`parsed.append(item)` 之前补 estimated_cost 推导**

修改 `backend/app/agents/langgraph_agent/nodes/search.py` — 在第 688 行 `parsed.append(item)` 之前插入：

```python
        if "price" in item and item.get("price"):
            try:
                item["estimated_cost"] = int(float(item["price"]))
            except (TypeError, ValueError):
                pass
        if "estimated_cost" not in item:
            star = item.get("star_rating")
            if star and star > 0:
                item["estimated_cost"] = int(star * 200)
            else:
                item["estimated_cost"] = 500
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/agents/test_search_hotels.py -v
```

Expected: 全部 PASS（含原有 3 个和新增 4 个，共 7 个）。

- [ ] **Step 5: 跑回归确认其它酒店测试未坏**

```bash
cd backend && pytest tests/agents/test_search_hotels.py tests/agents/test_compute_day_budget.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/agents/langgraph_agent/nodes/search.py backend/tests/agents/test_search_hotels.py
git commit -m "fix(hotels): 修复 AIGoHotel 解析未填充 estimated_cost 导致预算 0 元

补充 estimated_cost 推导：优先用 price，其次按 star_rating × 200 估算，
兜底 500。预算 Tab 的 total_hotels 计算依赖此字段。"
```

### Task 1.2: 酒店名清理工具函数（前端）

**Files:**
- Create: `frontend/src/utils/hotelFormat.ts`
- Test: 用 `vitest` 框架（先确认是否已安装），无则创建简单单元测试

- [ ] **Step 1: 检查前端测试框架**

```bash
cd frontend && cat package.json | grep -E "vitest|jest|@testing-library"
```

记录结果。若无测试框架，本任务跳过测试代码、改用手动验证（在调用方手动测试效果）。

- [ ] **Step 2: 写工具函数**

创建 `frontend/src/utils/hotelFormat.ts`：

```ts
/**
 * 移除酒店名中末尾的括号英文部分。
 * 例："维景大酒店(Winjing Hotel)" → "维景大酒店"
 *
 * 同时处理半角和全角括号。
 */
export function cleanHotelName(name: string | undefined | null): string {
  if (!name) return ''
  return name.replace(/[(（][^)）]*[)）]/g, '').trim()
}
```

- [ ] **Step 3: 若有 vitest，写测试**

创建 `frontend/src/utils/hotelFormat.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { cleanHotelName } from './hotelFormat'

describe('cleanHotelName', () => {
  it('strips english parentheses', () => {
    expect(cleanHotelName('维景大酒店(Winjing Hotel)')).toBe('维景大酒店')
  })

  it('handles fullwidth parentheses', () => {
    expect(cleanHotelName('丽枫酒店（Lavande）')).toBe('丽枫酒店')
  })

  it('preserves chinese-only name', () => {
    expect(cleanHotelName('如家酒店')).toBe('如家酒店')
  })

  it('handles empty/null', () => {
    expect(cleanHotelName('')).toBe('')
    expect(cleanHotelName(undefined)).toBe('')
    expect(cleanHotelName(null)).toBe('')
  })

  it('trims surrounding whitespace', () => {
    expect(cleanHotelName('  汉庭(Hanting)  ')).toBe('汉庭')
  })
})
```

运行 `npm test` 或 `npx vitest run`。Expected: 全部 PASS。

- [ ] **Step 4: 找出所有需要调用的位置**

```bash
cd frontend && grep -rn "hotel\?\.name\|hotel\.name" src/components src/views 2>/dev/null
```

记录所有位置（预计 `TabItinerary.vue`、`TabOverview.vue`、`DayCard*.vue` 等）。

- [ ] **Step 5: 在每个位置替换显示**

对每个文件：
1. 在 `<script setup>` 顶部加 `import { cleanHotelName } from '@/utils/hotelFormat'`
2. 模板中 `{{ hotel.name }}` 改为 `{{ cleanHotelName(hotel.name) }}`
3. 若是 `:title="hotel.name"` 之类的属性绑定也一并替换

- [ ] **Step 6: 启动 dev 服务器手动验证**

```bash
cd frontend && npm run dev
```

打开浏览器，进入结果页，搜索带英文的酒店（北上广深通常有）。Expected: 所有酒店名不再含括号英文。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/utils/hotelFormat.ts frontend/src/utils/hotelFormat.test.ts \
        frontend/src/components/result/ frontend/src/views/Result.vue 2>/dev/null
git commit -m "feat(hotels): 前端显示去除酒店名括号中的英文

新增 cleanHotelName 工具函数，所有显示酒店名的位置统一调用。
例：维景大酒店(Winjing Hotel) → 维景大酒店。"
```

---

## Phase 2 — 景点池扩容与分页加载（Module 1）

### Task 2.1: 后端 — 抽取可重入搜索函数

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/discovery.py`
- Test: `backend/tests/agents/test_search_attractions_discovery_node.py`

当前 `search_attractions_discovery_node` 内联从缓存读 attractions。需要把"按城市 + 排除已有 + 取 batch_size 个"抽成 helper。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/agents/test_search_attractions_discovery_node.py` 末尾追加：

```python
import pytest
from unittest.mock import patch, AsyncMock
from app.agents.langgraph_agent.nodes.discovery import (
    _fetch_attractions_batch,
)


@pytest.mark.asyncio
async def test_fetch_attractions_batch_excludes_known_names():
    from app.services.attractions_cache_service import CachedAttraction

    fake_pool = [
        CachedAttraction(name="故宫", longitude=116.397, latitude=39.916, category="博物馆"),
        CachedAttraction(name="天坛", longitude=116.412, latitude=39.882, category="古迹"),
        CachedAttraction(name="颐和园", longitude=116.273, latitude=39.999, category="公园"),
        CachedAttraction(name="圆明园", longitude=116.299, latitude=40.008, category="公园"),
    ]

    class FakeService:
        async def get_attractions(self, city, min_count, categories=None):
            return fake_pool

    with patch(
        "app.agents.langgraph_agent.nodes.discovery.get_attractions_cache_service",
        return_value=FakeService(),
    ):
        result = await _fetch_attractions_batch(
            city="北京",
            exclude_names={"故宫", "天坛"},
            batch_size=2,
            categories=None,
        )

    names = [a["name"] for a in result]
    assert "故宫" not in names
    assert "天坛" not in names
    assert len(result) == 2
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/agents/test_search_attractions_discovery_node.py::test_fetch_attractions_batch_excludes_known_names -v
```

Expected: FAIL（`ImportError` 或 `AttributeError`）。

- [ ] **Step 3: 在 `discovery.py` 添加 `_fetch_attractions_batch` 并重构现有节点**

替换 `backend/app/agents/langgraph_agent/nodes/discovery.py` 第 31-54 行（整个 `search_attractions_discovery_node` 函数加新 helper）为：

```python
async def _fetch_attractions_batch(
    city: str,
    exclude_names: set[str],
    batch_size: int,
    categories: list[str] | None,
) -> list[dict[str, Any]]:
    """从缓存取一批景点，排除已知名字。"""
    service = get_attractions_cache_service()
    # 为了去重后还能取到 batch_size 个，min_count 应当大于 batch_size + exclude 数
    target_min = max(batch_size + len(exclude_names), 40)
    attractions = await service.get_attractions(
        city=city,
        min_count=target_min,
        categories=categories,
    )
    filtered = [a for a in attractions if a.name not in exclude_names]
    return [_cached_attraction_to_discovery_item(poi) for poi in filtered[:batch_size]]


async def search_attractions_discovery_node(state: DiscoveryState) -> Dict[str, Any]:
    """从共享景点缓存获取首屏景点，供用户在发现页选择。"""
    print("🔍 执行节点: search_attractions_discovery_node (发现模式)")
    request = state["request"]
    categories = _preferences_to_categories(request.preferences or [])

    try:
        # 首屏固定 30 个，与天数解耦
        discovered = await _fetch_attractions_batch(
            city=request.city,
            exclude_names=set(),
            batch_size=30,
            categories=categories,
        )
        with_location = sum(1 for item in discovered if item.get("location"))
        print(f"🔍 发现景点: {len(discovered)} 个 ({with_location} 个有坐标)")
        return {"discovered_attractions": discovered}
    except Exception as e:
        print(f"❌ search_attractions_discovery_node 异常: {e}")
        return {
            "discovered_attractions": [],
            "errors": [f"search_attractions_discovery: 查询失败 - {str(e)[:200]}"],
        }
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/agents/test_search_attractions_discovery_node.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/agents/langgraph_agent/nodes/discovery.py backend/tests/agents/test_search_attractions_discovery_node.py
git commit -m "refactor(discovery): 抽取 _fetch_attractions_batch 支持去重批量获取

为后续 'load more' 端点准备。首屏数量固定 30，不再随天数变化。"
```

### Task 2.2: 后端 — 新增 /api/discover/load_more 端点

**Files:**
- Modify: `backend/app/api/routes/trip_lg.py`（追加路由）
- Modify: `backend/app/models/*` 或现有 schema 文件（追加 Request/Response 模型）— 实际路径需 grep 确认
- Test: `backend/tests/api/test_discover_load_more.py`（新建）

- [ ] **Step 1: 找到放 schema 的位置**

```bash
grep -rn "PreviewDayAssignmentRequest\|class DiscoveredAttraction" backend/app/ 2>/dev/null | head -5
```

记下 schema 文件路径（后续用 X 表示）。

- [ ] **Step 2: 写失败测试**

创建 `backend/tests/api/test_discover_load_more.py`：

```python
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


@pytest.fixture
def mock_fetch():
    """避免真实命中缓存/网络"""
    fake_items = [
        {"name": "新景点A", "category": "公园", "description": "x",
         "address": "", "rating": "4.5", "ticket_price": 0,
         "image_url": "", "location": {"longitude": 116.5, "latitude": 39.9},
         "poi_id": "a"},
        {"name": "新景点B", "category": "古迹", "description": "y",
         "address": "", "rating": "4.6", "ticket_price": 0,
         "image_url": "", "location": {"longitude": 116.6, "latitude": 39.8},
         "poi_id": "b"},
    ]
    with patch(
        "app.api.routes.trip_lg._fetch_attractions_batch",
        new=AsyncMock(return_value=fake_items),
    ) as m:
        yield m


def test_load_more_returns_filtered_batch(mock_fetch):
    resp = client.post("/api/discover/load_more", json={
        "city": "北京",
        "exclude_names": ["故宫", "天坛"],
        "batch_size": 20,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "attractions" in body
    assert len(body["attractions"]) == 2

    # 确认 helper 调用时把 exclude_names 转成 set
    args, kwargs = mock_fetch.call_args
    assert set(kwargs.get("exclude_names") or args[1]) == {"故宫", "天坛"}


def test_load_more_default_batch_size(mock_fetch):
    resp = client.post("/api/discover/load_more", json={
        "city": "北京",
        "exclude_names": [],
    })
    assert resp.status_code == 200
    # 默认 batch_size 应为 20
    args, kwargs = mock_fetch.call_args
    assert kwargs.get("batch_size", args[2] if len(args) > 2 else None) == 20


def test_load_more_rejects_empty_city():
    resp = client.post("/api/discover/load_more", json={
        "city": "",
        "exclude_names": [],
    })
    assert resp.status_code == 422
```

- [ ] **Step 3: 运行测试验证失败**

```bash
cd backend && pytest tests/api/test_discover_load_more.py -v
```

Expected: 全部 FAIL（404 Not Found，路由不存在）。

- [ ] **Step 4: 添加 Request/Response 模型**

在 schema 文件（X）末尾追加：

```python
class LoadMoreAttractionsRequest(BaseModel):
    city: str = Field(..., min_length=1, description="目的地城市")
    exclude_names: List[str] = Field(default_factory=list, description="已展示的景点名，需排除")
    batch_size: int = Field(default=20, ge=1, le=50, description="单次返回数量")
    categories: Optional[List[str]] = Field(default=None, description="可选的偏好类别过滤")


class LoadMoreAttractionsResponse(BaseModel):
    attractions: List[DiscoveredAttraction]
```

确保 `DiscoveredAttraction` 已存在；若类型对应不上，复用 `DiscoveryState` 中的 dict 结构即可。

- [ ] **Step 5: 在 `routes/trip_lg.py` 添加路由**

在文件顶部 import 区追加：

```python
from app.agents.langgraph_agent.nodes.discovery import _fetch_attractions_batch
from app.agents.langgraph_agent.nodes.search import _preferences_to_categories
# 同时 import LoadMoreAttractionsRequest, LoadMoreAttractionsResponse
```

在文件末尾追加路由（参照 `preview_day_assignment` 风格）：

```python
@router.post(
    "/discover/load_more",
    response_model=LoadMoreAttractionsResponse,
    summary="加载更多景点",
    description="基于城市继续搜索景点，排除已展示的名字。返回新一批 batch_size 个。"
)
async def load_more_attractions(req: LoadMoreAttractionsRequest):
    try:
        categories = _preferences_to_categories(req.categories or [])
        items = await _fetch_attractions_batch(
            city=req.city,
            exclude_names=set(req.exclude_names),
            batch_size=req.batch_size,
            categories=categories or None,
        )
        return LoadMoreAttractionsResponse(attractions=items)
    except Exception as e:
        print(f"❌ load_more_attractions 异常: {e}")
        raise HTTPException(status_code=500, detail=f"加载更多失败: {str(e)[:200]}")
```

- [ ] **Step 6: 运行测试验证通过**

```bash
cd backend && pytest tests/api/test_discover_load_more.py -v
```

Expected: 3 个测试全 PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/app/api/routes/trip_lg.py backend/app/models/ backend/tests/api/test_discover_load_more.py
git commit -m "feat(discover): 新增 POST /api/discover/load_more 端点

支持发现页'加载更多'按钮，按城市追加搜索景点，去重已展示项。
默认每次 20 个，最多 50。"
```

### Task 2.3: 前端 — DiscoverView 加"加载更多"按钮

**Files:**
- Modify: `frontend/src/views/DiscoverView.vue`
- Modify: `frontend/src/services/api.ts`（新增 API 调用）

- [ ] **Step 1: 在 api.ts 加调用**

打开 `frontend/src/services/api.ts`，在末尾追加：

```ts
export interface LoadMoreRequest {
  city: string
  exclude_names: string[]
  batch_size?: number
  categories?: string[]
}

export async function loadMoreAttractions(req: LoadMoreRequest) {
  const resp = await fetch('/api/discover/load_more', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_size: 20, ...req }),
  })
  if (!resp.ok) {
    throw new Error(`加载更多失败: ${resp.status}`)
  }
  return resp.json() as Promise<{ attractions: any[] }>
}
```

- [ ] **Step 2: 在 DiscoverView.vue 加状态**

打开 `frontend/src/views/DiscoverView.vue`，在 `<script setup>` 内加：

```ts
import { loadMoreAttractions } from '@/services/api'

const loadMoreLoading = ref(false)
const loadMoreReachedLimit = ref(false)

async function handleLoadMore() {
  if (loadMoreLoading.value || loadMoreReachedLimit.value) return
  loadMoreLoading.value = true
  try {
    const excludeNames = attractions.value.map((a: any) => a.name)
    const res = await loadMoreAttractions({
      city: destination.value,
      exclude_names: excludeNames,
      batch_size: 20,
    })
    if (res.attractions && res.attractions.length > 0) {
      attractions.value.push(...res.attractions)
    }
    if (attractions.value.length >= 100 || res.attractions.length === 0) {
      loadMoreReachedLimit.value = true
    }
  } catch (e: any) {
    message.error(e?.message || '加载更多失败')
  } finally {
    loadMoreLoading.value = false
  }
}
```

注：`destination`、`attractions`、`message` 等都使用现有定义；若 `destination` 不存在，从 `route.query.destination` 或类似来源取。

- [ ] **Step 3: 在 DiscoverView.vue 模板加按钮**

在景点列表底部（搜索按钮和"开始规划"CTA 之间）追加：

```vue
<div class="load-more-bar">
  <a-button
    type="dashed"
    block
    :loading="loadMoreLoading"
    :disabled="loadMoreReachedLimit"
    @click="handleLoadMore"
  >
    {{ loadMoreReachedLimit ? '已达上限' : `加载更多 +20` }}
  </a-button>
</div>
```

样式（加入 `<style scoped>`）：

```css
.load-more-bar {
  padding: 16px;
  margin-top: 12px;
}
```

- [ ] **Step 4: 启动 dev 服务器验证**

```bash
cd backend && python run.py &
cd frontend && npm run dev
```

打开浏览器到 `/discover`：
- 看到首屏 30 个景点（之前是 20）
- 列表底部有"加载更多 +20"按钮
- 点击后追加 20 个、按钮临时变 loading
- 累计达到 100 后按钮变"已达上限"

- [ ] **Step 5: 提交**

```bash
git add frontend/src/services/api.ts frontend/src/views/DiscoverView.vue
git commit -m "feat(discover): 前端加'加载更多 +20'按钮

首屏 30 个景点，底部按钮可续加，累计 100 时禁用。"
```

---

## Phase 3 — 主流程时长均衡接入（Module 3）

`_rebalance_by_duration` 已存在，仅需在主流程 `cluster_attractions_node` 中接入。

### Task 3.1: 把 durations 注入主流程并接入 rebalance

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/cluster.py` （行 ~275 附近）
- Test: `backend/tests/agents/test_cluster_attractions_balance.py`（新建）

- [ ] **Step 1: 阅读现有 cluster 节点完整逻辑**

```bash
sed -n '1,40p;260,330p' backend/app/agents/langgraph_agent/nodes/cluster.py
```

确认在哪一步可以拿到 durations（或要不要新查一次）。

- [ ] **Step 2: 检查 estimate_durations_batch 在哪**

```bash
grep -rn "def estimate_durations_batch\|async def estimate_durations_batch" backend/app/ | head -3
```

- [ ] **Step 3: 写失败测试**

创建 `backend/tests/agents/test_cluster_attractions_balance.py`：

```python
from unittest.mock import AsyncMock, patch
import pytest

from app.agents.langgraph_agent.nodes.cluster import cluster_attractions_node
from app.agents.langgraph_agent.state import TripPlannerState


def _build_state():
    """构造一个简单的 state：5 个景点 / 2 天 / 各景点访问 300 分钟。

    全部落到同一天会超 480 → rebalance 应该至少分到两天。
    """
    return {
        "request": type("R", (), {
            "city": "北京",
            "travel_days": 2,
            "preferences": [],
            "must_visit": [],
        })(),
        "attractions": [
            {"name": f"P{i}", "longitude": 116.4 + i * 0.001, "latitude": 39.9 + i * 0.001,
             "category": "x", "description": "", "address": "", "rating": "4",
             "ticket_price": 0, "image_url": "", "poi_id": str(i)}
            for i in range(5)
        ],
    }


@pytest.mark.asyncio
async def test_cluster_attractions_balances_long_days():
    """所有景点估时都 300 分钟时，单天不应超 480 (即每天最多 1 个)"""
    with patch(
        "app.agents.langgraph_agent.nodes.cluster.estimate_durations_batch",
        new=AsyncMock(return_value={f"P{i}": 300 for i in range(5)}),
    ):
        result = await cluster_attractions_node(_build_state())

    day_assignments = result.get("day_assignments")
    assert day_assignments is not None
    assert len(day_assignments) == 2
    for day in day_assignments:
        total = sum(300 for _ in day)
        assert total <= 480, f"单天总时长 {total} > 480 分钟，未做时长均衡"
```

注：上述测试假定 cluster 节点输出 `day_assignments` 键。若实际键名不同（如 `clusters`），按真实情况调整。

- [ ] **Step 4: 运行测试验证失败**

```bash
cd backend && pytest tests/agents/test_cluster_attractions_balance.py -v
```

Expected: FAIL — 当前未接入 rebalance，单天可能超 480。

- [ ] **Step 5: 在 cluster.py 引入 rebalance**

打开 `backend/app/agents/langgraph_agent/nodes/cluster.py`：

1. 顶部 import 区追加（依据 step 2 结果）：

```python
from ..utils.geo import _rebalance_by_duration
# 若 estimate_durations_batch 未导出，则用现有的 / 模拟一个默认 dict
```

2. 在 line 275 附近（找到 `clusters = _cluster_attractions_by_proximity(valid_attractions, request.travel_days)` 之后、TSP 排序之前）插入：

```python
    # 接入时长均衡：默认每景点 120 分钟（与 preview API 行为一致）
    durations = {a["name"]: 120 for a in valid_attractions}
    try:
        from ..utils.parsing import estimate_durations_batch  # noqa
        durations = await estimate_durations_batch(valid_attractions)
    except Exception as e:
        print(f"⚠️ 估时失败，使用默认 120 分钟: {e}")
    clusters = _rebalance_by_duration(clusters, durations, max_minutes=480)
```

（注：实际 `estimate_durations_batch` 路径见 step 2。若它在 `app.api.routes.trip_lg` 中而 cluster 节点不能引用 routes，则把它抽到 `utils/llm_duration.py` 再 import。这种重构作为本步的附属。）

- [ ] **Step 6: 运行测试验证通过**

```bash
cd backend && pytest tests/agents/test_cluster_attractions_balance.py -v
```

Expected: PASS。

- [ ] **Step 7: 跑回归确认其它聚类相关测试未坏**

```bash
cd backend && pytest tests/agents/test_cluster_from_selections.py tests/agents/test_route_segments.py tests/agents/test_skeleton_graph.py -v
```

Expected: 全部 PASS（或解释为何坏 / 修复）。

- [ ] **Step 8: 提交**

```bash
git add backend/app/agents/langgraph_agent/nodes/cluster.py \
        backend/app/agents/langgraph_agent/utils/ \
        backend/tests/agents/test_cluster_attractions_balance.py
git commit -m "feat(cluster): 主流程聚类节点接入时长均衡

调用现有 _rebalance_by_duration，使生成的每日行程不超过 480 分钟。
LLM 估时失败时降级到默认 120 分钟/景点。"
```

### Task 3.2: 前端 — 在日程分配页显示"已自动均衡"提示

**Files:**
- Modify: `frontend/src/views/DiscoverView.vue` （现有日程分配视图区段）

- [ ] **Step 1: 找到日程分配视图的 Day Card 标题渲染位置**

```bash
grep -n "第.*天\|day_index\|Day {" frontend/src/views/DiscoverView.vue | head -20
```

- [ ] **Step 2: 在 Day Card 标题旁加 tooltip**

在每个 day-card-header 模板（如 `<h3>第 {{ idx + 1 }} 天</h3>`）旁加：

```vue
<a-tooltip placement="top">
  <template #title>已根据距离和时长自动均衡，可手动拖拽调整</template>
  <InfoCircleOutlined class="day-balance-info" />
</a-tooltip>
```

确保 `InfoCircleOutlined` 已 import（`import { InfoCircleOutlined } from '@ant-design/icons-vue'`）。

样式：

```css
.day-balance-info {
  margin-left: 6px;
  color: var(--color-text-secondary, #888);
  font-size: 14px;
  cursor: help;
}
```

- [ ] **Step 3: 浏览器手动验证**

启动前后端，进入发现页 → 勾选景点 → 进入日程分配 → 检查 tooltip 出现且文案正确。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/DiscoverView.vue
git commit -m "feat(discover): 日程分配 Day Card 标题加'自动均衡'提示"
```

---

## Phase 4 — AI 帮我选（从攻略提取）（Module 2）

### Task 4.1: 后端 — extract_from_strategy 工具与端点

**Files:**
- Create: `backend/app/agents/langgraph_agent/utils/strategy_extract.py`
- Modify: `backend/app/api/routes/trip_lg.py`
- Modify: schema 文件（同 Task 2.2）
- Test: `backend/tests/agents/test_strategy_extract.py`、`backend/tests/api/test_ai_select.py`

- [ ] **Step 1: 写 strategy_extract 测试（先核心解析逻辑）**

创建 `backend/tests/agents/test_strategy_extract.py`：

```python
from app.agents.langgraph_agent.utils.strategy_extract import (
    match_names_to_pool,
    normalize_name,
)


def test_normalize_strips_common_suffixes():
    assert normalize_name("故宫博物院") == "故宫"
    assert normalize_name("颐和园景区") == "颐和园"
    assert normalize_name("天坛公园") == "天坛"
    assert normalize_name("北京大学") == "北京大学"  # 不应删"学"


def test_match_to_pool_finds_fuzzy():
    pool = [
        {"poi_id": "1", "name": "故宫博物院"},
        {"poi_id": "2", "name": "颐和园"},
        {"poi_id": "3", "name": "天坛"},
    ]
    # 攻略文本中可能写"故宫"或"天坛公园"
    matched = match_names_to_pool(["故宫", "天坛公园", "长城"], pool)
    ids = sorted([m["poi_id"] for m in matched])
    assert ids == ["1", "3"]


def test_match_to_pool_handles_empty():
    assert match_names_to_pool([], [{"poi_id": "1", "name": "X"}]) == []
    assert match_names_to_pool(["A"], []) == []
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/agents/test_strategy_extract.py -v
```

Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 strategy_extract.py**

创建 `backend/app/agents/langgraph_agent/utils/strategy_extract.py`：

```python
"""从旅游攻略文本提取景点名，并模糊匹配到当前景点池。"""

import json
import re
from typing import Any, Dict, List

from ....services.llm_service import get_chat_llm, is_structured_output_supported


SUFFIXES = ["博物院", "博物馆", "景区", "公园", "广场", "园林", "胜地", "古镇"]


def normalize_name(name: str) -> str:
    """去除常见景点后缀，便于模糊匹配。"""
    n = name.strip()
    for suf in SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf):
            n = n[: -len(suf)]
            break
    return n


def match_names_to_pool(
    candidate_names: List[str],
    pool: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把 LLM 提取出的景点名匹配到 pool 中的景点。

    匹配规则：原名包含、normalize 后包含、双向 in。"""
    if not candidate_names or not pool:
        return []
    matched: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for cand in candidate_names:
        cand_norm = normalize_name(cand)
        for item in pool:
            item_id = item.get("poi_id") or item.get("name")
            if item_id in seen_ids:
                continue
            item_name = item.get("name", "")
            item_norm = normalize_name(item_name)
            if (
                cand in item_name
                or item_name in cand
                or cand_norm in item_norm
                or item_norm in cand_norm
            ):
                matched.append(item)
                seen_ids.add(item_id)
                break
    return matched


async def extract_attractions_from_strategy(
    destination: str,
    days: int,
    pool: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """调 Bing 搜索 + LLM 解析，返回 {recommended_ids, source_strategy_title}。"""
    from ....services.bing_mcp_service import search_web

    query = f"{destination} {days}日游 经典攻略"
    try:
        results = await search_web(query, top_k=5)
    except Exception as e:
        print(f"⚠️ Bing 搜索失败: {e}")
        return {"recommended_ids": [], "source_strategy_title": None}

    # 拼接 top 5 摘要
    combined = "\n\n".join(
        f"标题：{r.get('title', '')}\n摘要：{r.get('snippet', '')[:500]}"
        for r in (results or [])[:5]
    )
    if not combined.strip():
        return {"recommended_ids": [], "source_strategy_title": None}

    prompt = f"""从下面的旅游攻略文本中提取在 {destination} 出现的所有具体景点名（不要市/区/省/餐厅/酒店）。

输出 JSON：{{"attractions": ["景点1", "景点2", ...]}}

攻略文本：
{combined[:4000]}"""

    llm = get_chat_llm()
    try:
        if is_structured_output_supported(llm):
            from pydantic import BaseModel
            from typing import List as _L

            class _Out(BaseModel):
                attractions: _L[str]

            resp = await llm.with_structured_output(_Out).ainvoke(prompt)
            names = resp.attractions
        else:
            raw = await llm.ainvoke(prompt)
            text = raw.content if hasattr(raw, "content") else str(raw)
            m = re.search(r"\{.*\}", text, re.DOTALL)
            names = json.loads(m.group(0)).get("attractions", []) if m else []
    except Exception as e:
        print(f"⚠️ LLM 提取景点名失败: {e}")
        return {"recommended_ids": [], "source_strategy_title": None}

    matched = match_names_to_pool(names, pool)
    return {
        "recommended_ids": [m.get("poi_id") or m.get("name") for m in matched],
        "source_strategy_title": (results or [{}])[0].get("title"),
    }
```

注：上面 `bing_mcp_service.search_web` 是占位名。实际函数名需 `grep` 确认。

- [ ] **Step 4: 确认 bing 服务的真实接口**

```bash
grep -n "def search\|async def search\|^def \|^async def " backend/app/services/bing_mcp_service.py | head -10
```

把上一步代码中的 `search_web` 改成真实函数名。

- [ ] **Step 5: 运行 strategy_extract 测试验证通过**

```bash
cd backend && pytest tests/agents/test_strategy_extract.py -v
```

Expected: 3 个测试全 PASS（这些都不依赖 LLM/Bing，只测纯函数）。

- [ ] **Step 6: 写 API 端点测试**

创建 `backend/tests/api/test_ai_select.py`：

```python
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_ai_select_returns_matched_ids():
    fake_result = {
        "recommended_ids": ["1", "3"],
        "source_strategy_title": "北京三日游精华路线",
    }
    with patch(
        "app.api.routes.trip_lg.extract_attractions_from_strategy",
        new=AsyncMock(return_value=fake_result),
    ):
        resp = client.post("/api/discover/ai_select", json={
            "destination": "北京",
            "days": 3,
            "attractions": [
                {"poi_id": "1", "name": "故宫"},
                {"poi_id": "2", "name": "天坛"},
                {"poi_id": "3", "name": "颐和园"},
            ],
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_ids"] == ["1", "3"]
    assert body["source_strategy_title"] == "北京三日游精华路线"


def test_ai_select_rejects_empty_destination():
    resp = client.post("/api/discover/ai_select", json={
        "destination": "",
        "days": 3,
        "attractions": [],
    })
    assert resp.status_code == 422
```

- [ ] **Step 7: 运行 API 测试验证失败**

```bash
cd backend && pytest tests/api/test_ai_select.py -v
```

Expected: FAIL（404）。

- [ ] **Step 8: 添加 schema 与路由**

schema 文件追加：

```python
class AISelectRequest(BaseModel):
    destination: str = Field(..., min_length=1)
    days: int = Field(..., ge=1, le=30)
    attractions: List[Dict[str, Any]] = Field(default_factory=list)
    preferences: Optional[Dict[str, Any]] = None


class AISelectResponse(BaseModel):
    recommended_ids: List[str]
    source_strategy_title: Optional[str] = None
```

`routes/trip_lg.py` 顶部 import：

```python
from app.agents.langgraph_agent.utils.strategy_extract import extract_attractions_from_strategy
```

追加路由：

```python
@router.post(
    "/discover/ai_select",
    response_model=AISelectResponse,
    summary="AI 从攻略选景",
    description="基于 Bing 搜索经典攻略 + LLM 提取景点名 + 模糊匹配现有景点池。"
)
async def ai_select_attractions(req: AISelectRequest):
    try:
        result = await extract_attractions_from_strategy(
            destination=req.destination,
            days=req.days,
            pool=req.attractions,
        )
        return AISelectResponse(**result)
    except Exception as e:
        print(f"❌ ai_select_attractions 异常: {e}")
        raise HTTPException(status_code=500, detail=f"AI 选景失败: {str(e)[:200]}")
```

- [ ] **Step 9: 运行 API 测试验证通过**

```bash
cd backend && pytest tests/api/test_ai_select.py tests/agents/test_strategy_extract.py -v
```

Expected: 全部 PASS。

- [ ] **Step 10: 提交**

```bash
git add backend/app/agents/langgraph_agent/utils/strategy_extract.py \
        backend/app/api/routes/trip_lg.py \
        backend/app/models/ \
        backend/tests/agents/test_strategy_extract.py \
        backend/tests/api/test_ai_select.py
git commit -m "feat(discover): 新增 AI 从攻略提取景点的端点和工具

POST /api/discover/ai_select：Bing 搜索 '{城市} {天数}日游 经典攻略' →
LLM 提取景点名 → 模糊匹配现有景点池 → 返回推荐 ID 列表。"
```

### Task 4.2: 前端 — DiscoverView 加"AI 帮我选"按钮

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/views/DiscoverView.vue`

- [ ] **Step 1: api.ts 加调用**

追加：

```ts
export interface AISelectRequest {
  destination: string
  days: number
  attractions: Array<{ poi_id?: string; name: string }>
  preferences?: Record<string, any>
}

export async function aiSelectAttractions(req: AISelectRequest) {
  const resp = await fetch('/api/discover/ai_select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) {
    throw new Error(`AI 选景失败: ${resp.status}`)
  }
  return resp.json() as Promise<{ recommended_ids: string[]; source_strategy_title?: string }>
}
```

- [ ] **Step 2: DiscoverView 模板加按钮**

在搜索栏右侧（参照现有"搜索"按钮位置）追加：

```vue
<a-button
  type="primary"
  :loading="aiSelectLoading"
  @click="handleAiSelect"
>
  <template #icon><ThunderboltOutlined /></template>
  AI 帮我选
</a-button>
```

import：`import { ThunderboltOutlined } from '@ant-design/icons-vue'`

- [ ] **Step 3: DiscoverView script 加逻辑**

```ts
import { aiSelectAttractions } from '@/services/api'

const aiSelectLoading = ref(false)

async function handleAiSelect() {
  if (aiSelectLoading.value) return
  aiSelectLoading.value = true
  try {
    message.loading({ content: '正在分析攻略…', key: 'ai-select', duration: 0 })
    const res = await aiSelectAttractions({
      destination: destination.value,
      days: travelDays.value,
      attractions: attractions.value.map((a: any) => ({
        poi_id: a.poi_id,
        name: a.name,
      })),
    })
    message.destroy('ai-select')

    if (!res.recommended_ids || res.recommended_ids.length === 0) {
      message.warning('未找到适合的攻略，请手动选择')
      return
    }

    // 自动勾选对应景点
    const idSet = new Set(res.recommended_ids)
    attractions.value.forEach((a: any) => {
      if (a.poi_id && idSet.has(a.poi_id)) {
        a.selected = true
      } else if (idSet.has(a.name)) {
        a.selected = true
      }
    })
    message.success(`已根据攻略选好 ${res.recommended_ids.length} 个景点`)
    // 滚动到底部 CTA
    document.querySelector('.start-plan-cta')?.scrollIntoView({ behavior: 'smooth' })
  } catch (e: any) {
    message.destroy('ai-select')
    message.error(e?.message || 'AI 推荐失败，请手动选择')
  } finally {
    aiSelectLoading.value = false
  }
}
```

注：`a.selected` 的字段名要与现有勾选逻辑一致。如果是用单独的 `selectedAttractionIds` Set 管理，则改为 `selectedAttractionIds.value.add(a.poi_id)`。

- [ ] **Step 4: 浏览器手动验证**

启动前后端，进入发现页（确保城市已选）：
1. 点"✨ AI 帮我选" → 看到 loading toast"正在分析攻略…"
2. 5-10 秒后：景点自动勾选若干 + 成功 toast + 滚动到底部
3. 失败场景（断网 / 后端关闭）：失败 toast

- [ ] **Step 5: 提交**

```bash
git add frontend/src/services/api.ts frontend/src/views/DiscoverView.vue
git commit -m "feat(discover): 前端加 'AI 帮我选' 按钮

点击后调 /api/discover/ai_select，自动勾选推荐景点并滚动到底部 CTA。"
```

---

## Phase 5 — 删除独立加载页，结果页骨架屏（Module 4）

最复杂，最后做。涉及：跳转链路、SSE 订阅迁移、多组件骨架态。

### Task 5.1: Result.vue 增加骨架模式入口

**Files:**
- Modify: `frontend/src/views/Result.vue`
- Modify: `frontend/src/main.ts`（路由如已是 `/result` 则不变）

- [ ] **Step 1: 看 Result.vue 现状**

```bash
sed -n '1,60p' frontend/src/views/Result.vue
```

- [ ] **Step 2: 在 Result.vue 添加 streaming 模式状态**

在 `<script setup>` 顶部增加：

```ts
import { useRoute } from 'vue-router'

const route = useRoute()
const isStreaming = computed(() => route.query.streaming === 'true')
const skeletonStage = ref<'init' | 'hero' | 'itinerary' | 'done' | 'error'>('init')
const streamError = ref<string | null>(null)
```

- [ ] **Step 3: 提交（仅状态壳，下一步接入 SSE）**

```bash
git add frontend/src/views/Result.vue
git commit -m "chore(result): 增加 streaming/skeleton 模式状态壳"
```

### Task 5.2: 把 SSE 订阅从 DiscoverView 搬到 Result.vue

**Files:**
- Modify: `frontend/src/views/Result.vue`
- Modify: `frontend/src/views/DiscoverView.vue`

- [ ] **Step 1: 找到 DiscoverView 中的 SSE 调用**

```bash
grep -n "createDraftFromSelectionsStream\|PlanProgress\|planningCurrentNode" frontend/src/views/DiscoverView.vue
```

- [ ] **Step 2: 在 Result.vue 增加 SSE 订阅函数**

新增 `subscribeToPlanStream(tripId: string)` 函数（参照 DiscoverView 现有实现），在 `onMounted` 中：

```ts
import { onMounted } from 'vue'
import { createDraftFromSelectionsStream } from '@/services/api'

onMounted(async () => {
  if (!isStreaming.value) return

  const tripId = route.query.trip_id as string
  if (!tripId) {
    streamError.value = '缺少 trip_id'
    skeletonStage.value = 'error'
    return
  }

  try {
    const stream = await createDraftFromSelectionsStream(tripId)
    for await (const event of stream) {
      if (event.node === 'macro_planner' && event.status === 'completed') {
        // 填充 hero 数据
        tripData.value = { ...tripData.value, ...event.data }
        skeletonStage.value = 'hero'
      } else if (event.node === 'reduce_assemble' && event.status === 'completed') {
        tripData.value = { ...tripData.value, ...event.data }
        skeletonStage.value = 'itinerary'
      } else if (event.node === 'global_synthesizer' && event.status === 'completed') {
        tripData.value = { ...tripData.value, ...event.data }
        skeletonStage.value = 'done'
      } else if (event.type === 'error') {
        streamError.value = event.message || '生成失败'
        skeletonStage.value = 'error'
      }
    }
  } catch (e: any) {
    streamError.value = e?.message || '连接失败'
    skeletonStage.value = 'error'
  }
})
```

注：上面 `event.node`/`event.status` 是占位 — 实际事件结构按 DiscoverView 中的解析逻辑迁移。**先 copy DiscoverView 中的 SSE 解析逻辑，确认 schema，再写到 Result 中。**

- [ ] **Step 3: 在 Result.vue 模板渲染骨架态**

参照现状（grep 找 `<ResultHero>`、`<TabOverview>` 等组件），用 `v-if="skeletonStage === 'init'"` 渲染骨架 / 用 `v-else` 渲染真实数据。

骨架元素示例（用 antd `a-skeleton`）：

```vue
<template v-if="skeletonStage === 'init' || skeletonStage === 'hero' && !tripData.title">
  <div class="hero-skeleton">
    <a-skeleton active :paragraph="{ rows: 2 }" />
    <p class="skeleton-hint">AI 正在为你定制行程…</p>
  </div>
</template>

<template v-else>
  <ResultHero :data="tripData" />
</template>
```

每个 Tab 类似处理。

错误态：

```vue
<div v-if="skeletonStage === 'error'" class="error-state">
  <p>{{ streamError }}</p>
  <a-button type="primary" @click="onRetry">重试</a-button>
</div>
```

- [ ] **Step 4: 在 DiscoverView 改跳转逻辑**

找到原本启动 SSE + 显示 PlanProgress 的地方（grep 出来），替换为：

```ts
async function handleStartPlan() {
  // 先创建 trip / 拿 trip_id（如果原本就是这样）
  const tripId = await createTripFromSelections(/* ... */)
  // 直接跳转
  router.push({
    path: '/result',
    query: { streaming: 'true', trip_id: tripId },
  })
}
```

移除 `PlanProgress` 组件的 `<template>` 使用、移除 `planningCurrentNode` 之类的状态。**保留 `PlanProgress.vue` 组件文件本身**（首页"一次性生成"流程仍可能用）。

- [ ] **Step 5: 浏览器手动验证**

完整跑一遍：首页填城市 → 发现页选景 → 日程分配 → 点"下一步"：
1. 立即跳到结果页（无独立加载页）
2. 看到骨架屏 + "AI 正在为你定制行程…"
3. 数据陆续填入 Hero → 行程 → 预算
4. 中途关后端：错误卡片出现，"重试"按钮可点

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/Result.vue frontend/src/views/DiscoverView.vue
git commit -m "feat(result): 结果页直接消费 SSE 流，骨架屏渐进填充

移除发现页到结果页之间的 PlanProgress 全屏加载页，
SSE 订阅从 DiscoverView 搬到 Result，按事件分阶段填数据。
保留 PlanProgress.vue 文件供首页流程继续使用。"
```

### Task 5.3: 给各 Tab 组件加骨架态

**Files:**
- Modify: `frontend/src/components/result/TabOverview.vue`
- Modify: `frontend/src/components/result/TabItinerary.vue`
- Modify: `frontend/src/components/result/TabBudget.vue`
- Modify: `frontend/src/components/result/TabMap.vue`
- Modify: `frontend/src/components/result/TabWeather.vue`

每个 Tab 组件接收一个 `:loading` prop，根据 prop 渲染骨架。

- [ ] **Step 1: 在每个 TabXxx.vue 顶部加 props**

```ts
const props = defineProps<{
  data?: any
  loading?: boolean
}>()
```

- [ ] **Step 2: 在 template 顶部加骨架分支**

```vue
<template>
  <div v-if="loading" class="tab-skeleton">
    <a-skeleton active :paragraph="{ rows: 4 }" />
  </div>
  <div v-else>
    <!-- 现有内容 -->
  </div>
</template>
```

- [ ] **Step 3: Result.vue 调用时按 skeletonStage 传 loading**

```vue
<TabOverview :data="tripData.overview" :loading="skeletonStage === 'init' || skeletonStage === 'hero'" />
<TabItinerary :data="tripData.day_plans" :loading="skeletonStage !== 'done' && skeletonStage !== 'itinerary'" />
<TabBudget :data="tripData.budget" :loading="skeletonStage !== 'done'" />
<TabMap :data="tripData" :loading="skeletonStage !== 'done' && skeletonStage !== 'itinerary'" />
<TabWeather :data="tripData.weather" :loading="skeletonStage !== 'done'" />
```

- [ ] **Step 4: 浏览器验证渐进填充**

正常网络下应看到：
1. 全部 Tab 骨架
2. ~3s 后 Overview 出现
3. ~6s 后 Itinerary、Map 出现
4. ~10s 后 Budget、Weather 出现（即 `global_synthesizer` 完成）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/result/
git commit -m "feat(result): 各 Tab 组件支持 loading prop 显示骨架态"
```

---

## Phase 6 — 收尾与验证

### Task 6.1: 端到端冒烟测试

- [ ] **Step 1: 启动前后端**

```bash
cd backend && python run.py &
cd frontend && npm run dev
```

- [ ] **Step 2: 走完整路径 1：手动选景**

1. 首页填城市"北京"、日期、偏好 → 进入发现页
2. ✓ 首屏 30 个景点
3. ✓ 点"加载更多 +20" → 累计 50
4. ✓ 勾选 12 个景点 → 点"开始规划"
5. ✓ 进入日程分配页，看到 3 天分配且 tooltip 显示
6. ✓ 拖动一个超长景点到空闲天，预警提示
7. ✓ 点"下一步" → 立即看到结果页骨架屏
8. ✓ 数据陆续填入
9. ✓ 预算 Tab "酒店"项 > 0
10. ✓ 所有酒店名不含英文括号

- [ ] **Step 3: 走完整路径 2：AI 选景**

1. 同样首页 → 发现页
2. ✓ 点"✨ AI 帮我选" → 5-10s 后景点被自动勾选
3. ✓ 滚动到底部 CTA
4. ✓ 后续流程同路径 1

- [ ] **Step 4: 错误恢复路径**

1. 进入结果页骨架屏后，关掉后端
2. ✓ 出现错误卡片
3. 重启后端，点"重试" → ✓ 恢复

- [ ] **Step 5: 跑全部后端测试**

```bash
cd backend && pytest -v
```

Expected: 全 PASS。

- [ ] **Step 6: 跑前端构建**

```bash
cd frontend && npm run build
```

Expected: 无类型错误，构建成功。

- [ ] **Step 7: 提交**（若有任何小修小补）

```bash
git status
# 若有变更
git add -A && git commit -m "chore: 端到端冒烟测试发现的小修"
```

### Task 6.2: 调用 requesting-code-review skill

完成所有任务后，调 `superpowers:requesting-code-review` skill 让我做 code review。

---

## Self-Review

**Spec coverage:**
- 模块 1（景点扩容+分页）→ Phase 2 ✓
- 模块 2（AI 选景）→ Phase 4 ✓
- 模块 3（时长均衡）→ Phase 3 ✓
- 模块 4（骨架屏）→ Phase 5 ✓
- 模块 5A（酒店名）→ Task 1.2 ✓
- 模块 5B（预算 bug）→ Task 1.1 ✓

**Placeholder scan：**
- Task 2.2 Step 1 中的"X"指代是引导执行者自己查 schema 文件位置（提供命令）— 这是合理的探索步骤，非延迟决策
- Task 4.1 Step 3 中的 `search_web` 是占位，紧跟 Step 4 让执行者用 grep 确认真实函数名 — 合理
- Task 5.2 Step 2 中的 `event.node`/`event.status` 显式说明"占位" + 紧跟"先 copy 现有 SSE 解析逻辑确认 schema"指引 — 合理

**Type consistency：**
- `cleanHotelName` 在 Task 1.2 定义、各组件用同名导入 ✓
- `_fetch_attractions_batch` 在 Task 2.1 定义，Task 2.2 端点中导入 ✓
- `extract_attractions_from_strategy` 在 Task 4.1 strategy_extract.py 定义、API 路由导入 ✓
- `LoadMoreAttractionsRequest/Response`、`AISelectRequest/Response` 模型与端点签名匹配 ✓
- `skeletonStage` 字面量在 Result.vue 与各 Tab 组件协同（`'init'` / `'hero'` / `'itinerary'` / `'done'` / `'error'`）✓

**Scope check：**
- 整体改动跨越后端 4 个文件 + 前端 ~8 个文件，分 6 个 Phase / 12 个 Task，每个 Task 都可独立提交
- Phase 1 完全独立可单独合入；后续 Phase 之间无严格依赖（除 Phase 5 假设 Phase 3 的 day_assignment 已正常）

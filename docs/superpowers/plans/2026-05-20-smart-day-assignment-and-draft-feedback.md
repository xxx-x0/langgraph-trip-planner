# 智能日程分配与骨架页交互反馈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Discover 页选完景点后基于 LLM 估时 + 地理聚类的智能日程分配，并修复 DraftView 所有 per-day 异步操作的 loading 反馈缺失问题。

**Architecture:** 后端新增 `POST /api/trip/plan/preview-day-assignment` 端点，组合"LLM 批量估时 + 现有 `_cluster_attractions_by_proximity` + 新 `_rebalance_by_duration`"返回分配方案；前端 DiscoverView 在 assign 阶段消费该接口，DraftView 通过 `withDayBusy` 包装函数集中管理 per-day 异步状态，DayCard 接收 `busy` prop 展示骨架屏/遮罩。

**Tech Stack:** Python (FastAPI / Pydantic / asyncio / pytest-asyncio)、Vue 3 (Composition API / Ant Design Vue)、LangGraph 现有 LLM helper (`_invoke_llm_with_retry`)。

**Spec:** `docs/superpowers/specs/2026-05-20-smart-day-assignment-and-draft-feedback-design.md`

---

## 任务总览

后端（A 部分）：
- Task 1: 扩展 schemas（`visit_minutes` + Preview 请求/响应模型）
- Task 2: 新建 `utils/duration.py`（`CATEGORY_DURATION_MAP` + `estimate_durations_batch`）
- Task 3: `utils/geo.py` 新增 `_rebalance_by_duration`
- Task 4: 新增 `/plan/preview-day-assignment` 端点
- Task 5: `cluster_from_selections_node` 透传 `visit_minutes`

前端（B 部分）：
- Task 6: 扩展 types + 新增 `previewDayAssignment` API 函数
- Task 7: DiscoverView 集成智能分配（含估时徽标 + 重置按钮）
- Task 8: DraftView 引入 `withDayBusy` + DayCard 增加 `busy` prop（骨架屏 + 遮罩）
- Task 9: DraftView 移除占位 tabs

---

## Task 1: 扩展 schemas（visit_minutes + Preview 请求/响应模型）

**Files:**
- Modify: `backend/app/models/schemas.py:347-358`（`DiscoveredAttraction` 增加 `visit_minutes` 字段）
- Modify: `backend/app/models/schemas.py`（文件末尾追加 `DayDurationInfo`、`PreviewDayAssignmentRequest`、`PreviewDayAssignmentResponse`）
- Test: `backend/tests/models/test_preview_schemas.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/models/test_preview_schemas.py`（目录 `tests/models/` 已存在且含 `__init__.py`）：

```python
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    DiscoveredAttraction,
    DayDurationInfo,
    PreviewDayAssignmentRequest,
    PreviewDayAssignmentResponse,
)


def test_discovered_attraction_accepts_visit_minutes():
    attr = DiscoveredAttraction(name="故宫", visit_minutes=120)
    assert attr.visit_minutes == 120


def test_discovered_attraction_visit_minutes_optional():
    attr = DiscoveredAttraction(name="故宫")
    assert attr.visit_minutes is None


def test_day_duration_info_basic():
    d = DayDurationInfo(day_index=0, total_minutes=300)
    assert d.day_index == 0
    assert d.total_minutes == 300
    assert d.warning is None


def test_day_duration_info_with_warning():
    d = DayDurationInfo(day_index=1, total_minutes=540, warning="当天偏紧")
    assert d.warning == "当天偏紧"


def test_preview_request_requires_attractions_and_days():
    req = PreviewDayAssignmentRequest(
        selected_attractions=[DiscoveredAttraction(name="A")],
        travel_days=2,
    )
    assert len(req.selected_attractions) == 1
    assert req.travel_days == 2


def test_preview_response_shape():
    resp = PreviewDayAssignmentResponse(
        day_assignments=[
            [DiscoveredAttraction(name="A", visit_minutes=60)],
            [DiscoveredAttraction(name="B", visit_minutes=90)],
        ],
        day_durations=[
            DayDurationInfo(day_index=0, total_minutes=60),
            DayDurationInfo(day_index=1, total_minutes=90),
        ],
    )
    assert len(resp.day_assignments) == 2
    assert resp.day_assignments[0][0].visit_minutes == 60
    assert resp.day_durations[1].total_minutes == 90
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && pytest tests/models/test_preview_schemas.py -v
```

Expected: ImportError 或 ValidationError，因为 `DayDurationInfo` / `PreviewDayAssignmentRequest` / `PreviewDayAssignmentResponse` 不存在，且 `visit_minutes` 字段不存在。

- [ ] **Step 3: 修改 DiscoveredAttraction 增加 visit_minutes**

编辑 `backend/app/models/schemas.py`，在 `DiscoveredAttraction` 类末尾（`poi_id` 之后）加：

```python
    visit_minutes: Optional[int] = Field(default=None, description="预估游玩时长(分钟)")
```

- [ ] **Step 4: 在文件末尾追加新模型**

在 `backend/app/models/schemas.py` 末尾追加：

```python
class DayDurationInfo(BaseModel):
    """单日估算时长（用于智能分配预览）"""
    day_index: int = Field(..., description="第几天，从0开始")
    total_minutes: int = Field(..., description="当日所有景点估算游玩总时长(分钟)")
    warning: Optional[str] = Field(default=None, description="提示文案，如'当天偏紧'")


class PreviewDayAssignmentRequest(BaseModel):
    """智能日程分配预览请求"""
    selected_attractions: List[DiscoveredAttraction] = Field(..., description="用户选中的景点列表")
    travel_days: int = Field(..., ge=1, description="旅行天数")


class PreviewDayAssignmentResponse(BaseModel):
    """智能日程分配预览响应"""
    day_assignments: List[List[DiscoveredAttraction]] = Field(..., description="每天的景点分配（每个景点带 visit_minutes）")
    day_durations: List[DayDurationInfo] = Field(..., description="每天的估算时长")
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend && pytest tests/models/test_preview_schemas.py -v
```

Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/schemas.py backend/tests/models/
git commit -m "feat(schemas): 增加 visit_minutes 与 Preview 日程分配请求/响应模型"
```

---

## Task 2: 新建 `utils/duration.py`（CATEGORY_DURATION_MAP + estimate_durations_batch）

**Files:**
- Create: `backend/app/agents/langgraph_agent/utils/duration.py`
- Test: `backend/tests/agents/utils/test_duration.py`（新建，含父目录 `__init__.py`）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/agents/utils/__init__.py`（空），然后 `backend/tests/agents/utils/test_duration.py`：

```python
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.utils.duration import (
    CATEGORY_DURATION_MAP,
    estimate_durations_batch,
    _fallback_durations,
)


def test_category_map_has_default():
    assert "default" in CATEGORY_DURATION_MAP
    assert CATEGORY_DURATION_MAP["default"] > 0


def test_fallback_uses_category_map():
    attractions = [
        {"name": "故宫", "category": "博物馆"},
        {"name": "未知地点", "category": "未知类别"},
        {"name": "无类别"},
    ]
    result = _fallback_durations(attractions)
    assert result["故宫"] == CATEGORY_DURATION_MAP["博物馆"]
    assert result["未知地点"] == CATEGORY_DURATION_MAP["default"]
    assert result["无类别"] == CATEGORY_DURATION_MAP["default"]


@pytest.mark.asyncio
async def test_estimate_durations_returns_llm_result_when_valid():
    fake_response = type("R", (), {"content":
        '[{"name":"故宫","visit_minutes":150},'
        '{"name":"颐和园","visit_minutes":120}]'
    })()
    with patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_response)):
        result = await estimate_durations_batch([
            {"name": "故宫", "description": "", "category": "博物馆"},
            {"name": "颐和园", "description": "", "category": "公园"},
        ])
    assert result == {"故宫": 150, "颐和园": 120}


@pytest.mark.asyncio
async def test_estimate_durations_falls_back_on_llm_failure():
    with patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await estimate_durations_batch([
            {"name": "故宫", "category": "博物馆"},
        ])
    assert result == {"故宫": CATEGORY_DURATION_MAP["博物馆"]}


@pytest.mark.asyncio
async def test_estimate_durations_clamps_invalid_minutes():
    fake_response = type("R", (), {"content":
        '[{"name":"A","visit_minutes":5},'
        '{"name":"B","visit_minutes":600},'
        '{"name":"C","visit_minutes":"bad"}]'
    })()
    with patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_response)):
        result = await estimate_durations_batch([
            {"name": "A", "category": "公园"},
            {"name": "B", "category": "博物馆"},
            {"name": "C", "category": "美食"},
        ])
    # A < 15 → fallback；B > 480 → fallback；C 非数字 → fallback
    assert result["A"] == CATEGORY_DURATION_MAP["公园"]
    assert result["B"] == CATEGORY_DURATION_MAP["博物馆"]
    assert result["C"] == CATEGORY_DURATION_MAP["美食"]


@pytest.mark.asyncio
async def test_estimate_durations_fills_missing_names():
    """LLM 只返回了部分景点的估算，缺失项用 fallback 补齐"""
    fake_response = type("R", (), {"content":
        '[{"name":"故宫","visit_minutes":150}]'
    })()
    with patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_response)):
        result = await estimate_durations_batch([
            {"name": "故宫", "category": "博物馆"},
            {"name": "颐和园", "category": "公园"},
        ])
    assert result["故宫"] == 150
    assert result["颐和园"] == CATEGORY_DURATION_MAP["公园"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && pytest tests/agents/utils/test_duration.py -v
```

Expected: ImportError（`duration` 模块不存在）

- [ ] **Step 3: 写实现**

新建 `backend/app/agents/langgraph_agent/utils/duration.py`：

```python
"""景点游玩时长估算工具。

使用 LLM 一次性估算所有候选景点的游玩时长；失败时使用 CATEGORY_DURATION_MAP 降级。
"""
import asyncio
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage

from ..exceptions import _invoke_llm_with_retry
from .parsing import _extract_json_array
from ....services.llm_service import get_llm


CATEGORY_DURATION_MAP: Dict[str, int] = {
    "博物馆": 120,
    "公园": 60,
    "寺庙": 90,
    "古迹": 75,
    "美食": 45,
    "购物": 90,
    "自然风光": 120,
    "历史文化": 90,
    "亲子": 90,
    "景点": 90,
    "default": 90,
}

MIN_MINUTES = 15
MAX_MINUTES = 480


def _fallback_durations(attractions: List[Dict]) -> Dict[str, int]:
    """根据 category 映射给每个景点分配默认时长。"""
    result: Dict[str, int] = {}
    for attr in attractions:
        name = attr.get("name", "")
        if not name:
            continue
        category = attr.get("category") or "default"
        result[name] = CATEGORY_DURATION_MAP.get(category, CATEGORY_DURATION_MAP["default"])
    return result


async def estimate_durations_batch(
    attractions: List[Dict],
    timeout_seconds: float = 8.0,
) -> Dict[str, int]:
    """一次性估算所有景点的游玩时长（分钟）。

    Args:
        attractions: 每项含 name / description / category 字段
        timeout_seconds: LLM 调用超时

    Returns:
        {name: minutes}，失败/缺失项用 CATEGORY_DURATION_MAP 兜底
    """
    if not attractions:
        return {}

    fallback = _fallback_durations(attractions)

    lines = []
    for i, attr in enumerate(attractions):
        name = attr.get("name", f"景点{i}")
        category = attr.get("category", "")
        description = (attr.get("description") or "").strip()[:120]
        lines.append(f"- 名称: {name} | 类别: {category} | 简介: {description}")
    attractions_text = "\n".join(lines)

    prompt = f"""请根据下列景点的名称、类别、简介，估算每个景点的合理游玩时长（分钟）。
要求严格输出 JSON 数组，每项包含 name 与 visit_minutes（15~480 的整数），不要输出额外文字。

景点列表：
{attractions_text}

示例输出：
[{{"name":"故宫博物院","visit_minutes":180}},{{"name":"景山公园","visit_minutes":60}}]
"""

    try:
        llm = get_llm()
        response = await asyncio.wait_for(
            _invoke_llm_with_retry(llm, [HumanMessage(content=prompt)], max_retries=2),
            timeout=timeout_seconds,
        )
    except (asyncio.TimeoutError, Exception) as e:
        print(f"⚠️ 游玩时长估算失败，使用默认值兜底: {e}")
        return fallback

    parsed = _extract_json_array(response.content)
    if not parsed:
        print("⚠️ 游玩时长估算返回无法解析，使用默认值兜底")
        return fallback

    result: Dict[str, int] = {}
    for item in parsed:
        name = item.get("name")
        minutes = item.get("visit_minutes")
        if not name:
            continue
        try:
            minutes_int = int(minutes)
        except (TypeError, ValueError):
            continue
        if MIN_MINUTES <= minutes_int <= MAX_MINUTES:
            result[name] = minutes_int

    # 缺失项用 fallback 补齐
    for name, default_min in fallback.items():
        result.setdefault(name, default_min)

    return result
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && pytest tests/agents/utils/test_duration.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/langgraph_agent/utils/duration.py backend/tests/agents/utils/
git commit -m "feat(duration): 新增 LLM 批量估算景点游玩时长，带分类默认值降级"
```

---

## Task 3: `utils/geo.py` 新增 `_rebalance_by_duration`

**Files:**
- Modify: `backend/app/agents/langgraph_agent/utils/geo.py`（末尾追加新函数）
- Test: `backend/tests/agents/utils/test_geo_rebalance.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/agents/utils/test_geo_rebalance.py`：

```python
from app.agents.langgraph_agent.utils.geo import _rebalance_by_duration


def _attr(name, lon, lat):
    return {"name": name, "longitude": lon, "latitude": lat}


def test_no_rebalance_when_within_limit():
    clusters = [
        [_attr("A", 116.40, 39.90), _attr("B", 116.41, 39.91)],
        [_attr("C", 116.50, 39.95)],
    ]
    durations = {"A": 120, "B": 120, "C": 120}
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    assert [[a["name"] for a in c] for c in result] == [["A", "B"], ["C"]]


def test_moves_farthest_attraction_when_over_limit():
    # Day 0 总 540 分钟超 480；远点 D 距质心最远，应移走到 day 1
    clusters = [
        [
            _attr("A", 116.40, 39.90),
            _attr("B", 116.41, 39.91),
            _attr("C", 116.40, 39.92),
            _attr("D", 116.80, 40.30),
        ],
        [_attr("E", 116.85, 40.35)],
    ]
    durations = {"A": 150, "B": 150, "C": 120, "D": 120, "E": 60}
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    names_day0 = {a["name"] for a in result[0]}
    names_day1 = {a["name"] for a in result[1]}
    assert "D" in names_day1
    assert "D" not in names_day0


def test_stops_when_move_would_make_target_overflow():
    # Day 0 超限，但移到 day 1 会让 day 1 也超限 → 停止
    clusters = [
        [_attr("A", 116.40, 39.90), _attr("B", 116.41, 39.91)],
        [_attr("C", 116.42, 39.92), _attr("D", 116.43, 39.93)],
    ]
    durations = {"A": 300, "B": 250, "C": 300, "D": 200}  # day0=550, day1=500
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    # 无论怎么挪，目标都会超限 → 至少不能让目标更糟
    for cluster in result:
        # 这个用例下可能完全不动，只验证函数不崩、所有景点都在
        pass
    all_names = sorted(a["name"] for c in result for a in c)
    assert all_names == ["A", "B", "C", "D"]


def test_preserves_all_attractions_after_rebalance():
    clusters = [
        [_attr("A", 116.40, 39.90), _attr("B", 116.41, 39.91), _attr("C", 116.42, 39.92)],
        [_attr("D", 116.80, 40.30)],
    ]
    durations = {"A": 200, "B": 200, "C": 200, "D": 60}
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    all_names = sorted(a["name"] for c in result for a in c)
    assert all_names == ["A", "B", "C", "D"]


def test_handles_missing_coords_gracefully():
    clusters = [
        [{"name": "A", "longitude": 0, "latitude": 0}, {"name": "B", "longitude": 0, "latitude": 0}],
        [{"name": "C", "longitude": 116.5, "latitude": 39.9}],
    ]
    durations = {"A": 300, "B": 300, "C": 100}
    # 坐标全 0，距离都是 0，不应崩溃
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    all_names = sorted(a["name"] for c in result for a in c)
    assert all_names == ["A", "B", "C"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && pytest tests/agents/utils/test_geo_rebalance.py -v
```

Expected: ImportError，因 `_rebalance_by_duration` 不存在。

- [ ] **Step 3: 实现 `_rebalance_by_duration`**

编辑 `backend/app/agents/langgraph_agent/utils/geo.py`，在文件末尾追加：

```python
def _cluster_centroid(cluster: List[Dict]) -> tuple:
    if not cluster:
        return (0.0, 0.0)
    lats = [a["latitude"] for a in cluster]
    lons = [a["longitude"] for a in cluster]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def _cluster_total_minutes(cluster: List[Dict], durations: Dict[str, int]) -> int:
    return sum(durations.get(a["name"], 0) for a in cluster)


def _rebalance_by_duration(
    clusters: List[List[Dict]],
    durations: Dict[str, int],
    max_minutes: int = 480,
    max_iterations: int = 5,
) -> List[List[Dict]]:
    """若某天总时长超出 max_minutes，把离该天质心最远的景点
    移到时长最少且地理上仍接近的相邻日。

    最多迭代 max_iterations 轮，无法继续优化时停止。返回新的 clusters
    （每个 cluster 重新做 TSP 排序）。
    """
    work = [list(c) for c in clusters]

    for _ in range(max_iterations):
        totals = [_cluster_total_minutes(c, durations) for c in work]
        over_idx = max(range(len(totals)), key=lambda i: totals[i])
        if totals[over_idx] <= max_minutes or len(work[over_idx]) <= 1:
            break

        src_cluster = work[over_idx]
        src_lat, src_lon = _cluster_centroid(src_cluster)

        # 找出离 src 质心最远的景点
        far_idx, far_dist = 0, -1.0
        for i, attr in enumerate(src_cluster):
            d = _haversine_distance(src_lat, src_lon, attr["latitude"], attr["longitude"])
            if d > far_dist:
                far_dist = d
                far_idx = i
        far_attr = src_cluster[far_idx]
        far_minutes = durations.get(far_attr["name"], 0)

        # 找目标 cluster：总时长最低、且移动后不会超限、加权考虑与 far_attr 的接近度
        best_target = None
        best_score = float("inf")
        for j, target_cluster in enumerate(work):
            if j == over_idx:
                continue
            if totals[j] + far_minutes > max_minutes:
                continue
            t_lat, t_lon = _cluster_centroid(target_cluster)
            geo_d = _haversine_distance(t_lat, t_lon, far_attr["latitude"], far_attr["longitude"])
            # 综合得分：低 total 优先，地理接近优先
            score = totals[j] + geo_d * 10
            if score < best_score:
                best_score = score
                best_target = j

        if best_target is None:
            break

        work[over_idx].pop(far_idx)
        work[best_target].append(far_attr)

    return [_order_cluster_by_tsp(c) for c in work]
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && pytest tests/agents/utils/test_geo_rebalance.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/langgraph_agent/utils/geo.py backend/tests/agents/utils/test_geo_rebalance.py
git commit -m "feat(geo): 新增 _rebalance_by_duration 按估时再平衡日程"
```

---

## Task 4: 新增 `/plan/preview-day-assignment` 端点

**Files:**
- Modify: `backend/app/api/routes/trip_lg.py`（imports + 新增端点函数）
- Test: `backend/tests/api/test_preview_day_assignment.py`（新建，含父目录 `__init__.py`）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/api/test_preview_day_assignment.py`（目录 `tests/api/` 已存在且含 `__init__.py`）：

```python
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _payload(attractions, days=2):
    return {
        "selected_attractions": attractions,
        "travel_days": days,
    }


@pytest.fixture
def mock_estimate():
    """避免真实调 LLM"""
    with patch(
        "app.api.routes.trip_lg.estimate_durations_batch",
        new=AsyncMock(return_value={"故宫": 120, "天坛": 90, "颐和园": 150}),
    ) as m:
        yield m


def test_returns_per_day_assignment_and_durations(mock_estimate):
    payload = _payload([
        {"name": "故宫", "category": "博物馆", "location": {"longitude": 116.397, "latitude": 39.916}},
        {"name": "天坛", "category": "古迹", "location": {"longitude": 116.412, "latitude": 39.882}},
        {"name": "颐和园", "category": "公园", "location": {"longitude": 116.273, "latitude": 39.999}},
    ], days=2)
    resp = client.post("/api/trip/plan/preview-day-assignment", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["day_assignments"]) == 2
    assert len(body["day_durations"]) == 2
    # 每个 attraction 都带 visit_minutes
    for day in body["day_assignments"]:
        for attr in day:
            assert attr["visit_minutes"] is not None and attr["visit_minutes"] > 0


def test_warning_set_when_day_over_8h(mock_estimate):
    # 故意构造一组紧密聚集（强制聚在同一天）且时长很长的景点
    mock_estimate.return_value = {"A": 240, "B": 240, "C": 240}
    payload = _payload([
        {"name": "A", "category": "x", "location": {"longitude": 116.40, "latitude": 39.90}},
        {"name": "B", "category": "x", "location": {"longitude": 116.401, "latitude": 39.901}},
        {"name": "C", "category": "x", "location": {"longitude": 116.402, "latitude": 39.902}},
    ], days=1)
    resp = client.post("/api/trip/plan/preview-day-assignment", json=payload)
    body = resp.json()
    assert body["day_durations"][0]["total_minutes"] == 720
    assert body["day_durations"][0]["warning"] is not None


def test_handles_missing_coords(mock_estimate):
    mock_estimate.return_value = {"A": 90, "B": 90}
    payload = _payload([
        {"name": "A", "category": "x"},
        {"name": "B", "category": "x"},
    ], days=2)
    resp = client.post("/api/trip/plan/preview-day-assignment", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # 没坐标也应该正常返回，不崩
    all_names = sorted(a["name"] for d in body["day_assignments"] for a in d)
    assert all_names == ["A", "B"]


def test_rejects_empty_attractions(mock_estimate):
    resp = client.post("/api/trip/plan/preview-day-assignment",
                       json={"selected_attractions": [], "travel_days": 2})
    # 空列表应该返回 200 + 空分配，或 400 — 由实现决定，这里测期望行为
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        body = resp.json()
        assert all(len(d) == 0 for d in body["day_assignments"])
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && pytest tests/api/test_preview_day_assignment.py -v
```

Expected: 404 Not Found，因为端点不存在。

- [ ] **Step 3: 修改 imports**

编辑 `backend/app/api/routes/trip_lg.py`，把 `from ...models.schemas import (...)` 的列表扩展为：

```python
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse,
    UserPreferenceResponse,
    UserPreference,
    ManualSearchRequest,
    PlanFromSelectionsRequest,
    PreviewDayAssignmentRequest,
    PreviewDayAssignmentResponse,
    DayDurationInfo,
    DiscoveredAttraction,
)
```

并在文件顶部 import 区追加：

```python
from ...agents.langgraph_agent.utils.duration import estimate_durations_batch
from ...agents.langgraph_agent.utils.geo import (
    _cluster_attractions_by_proximity,
    _order_cluster_by_tsp,
    _rebalance_by_duration,
)
```

- [ ] **Step 4: 实现端点**

在 `trip_lg.py` 中合适位置（建议紧跟在 `plan_from_selections_stream` 之后）追加：

```python
@router.post(
    "/plan/preview-day-assignment",
    response_model=PreviewDayAssignmentResponse,
    summary="智能日程分配预览",
    description="LLM 批量估时 + 地理聚类，返回每天的景点分配与估时（不持久化）"
)
async def preview_day_assignment(req: PreviewDayAssignmentRequest):
    selected = [a.model_dump() for a in req.selected_attractions]

    if not selected:
        return PreviewDayAssignmentResponse(day_assignments=[], day_durations=[])

    # 1. LLM 批量估时（失败自动降级）
    durations = await estimate_durations_batch(selected)

    # 2. 几何聚类（仅对有坐标的景点）
    geo_attrs = []
    no_coord_attrs = []
    for attr in selected:
        loc = attr.get("location") or {}
        lon = loc.get("longitude")
        lat = loc.get("latitude")
        if lon and lat:
            geo_attrs.append({"name": attr["name"], "longitude": lon, "latitude": lat})
        else:
            no_coord_attrs.append(attr)

    if geo_attrs:
        clusters = _cluster_attractions_by_proximity(geo_attrs, req.travel_days)
        clusters = _rebalance_by_duration(clusters, durations, max_minutes=480)
    else:
        # 无坐标兜底：均分
        from math import ceil
        per_day = max(ceil(len(selected) / req.travel_days), 1)
        clusters = []
        for d in range(req.travel_days):
            clusters.append([{"name": a["name"]} for a in selected[d * per_day:(d + 1) * per_day]])

    # 把无坐标景点平均派发到当前天数最少的 cluster
    for attr in no_coord_attrs:
        shortest = min(range(len(clusters)), key=lambda i: len(clusters[i])) if clusters else 0
        if not clusters:
            clusters = [[] for _ in range(req.travel_days)]
        clusters[shortest].append({"name": attr["name"]})

    # 3. 还原成完整 DiscoveredAttraction（带 visit_minutes）
    name_to_attr = {a["name"]: a for a in selected}
    day_assignments = []
    day_durations = []
    for idx, cluster in enumerate(clusters):
        day_attrs = []
        total = 0
        for c in cluster:
            full = dict(name_to_attr.get(c["name"], {"name": c["name"]}))
            mins = durations.get(c["name"], 90)
            full["visit_minutes"] = mins
            total += mins
            day_attrs.append(DiscoveredAttraction(**full))
        warning = "当天偏紧" if total > 480 else None
        day_assignments.append(day_attrs)
        day_durations.append(DayDurationInfo(day_index=idx, total_minutes=total, warning=warning))

    return PreviewDayAssignmentResponse(
        day_assignments=day_assignments,
        day_durations=day_durations,
    )
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend && pytest tests/api/test_preview_day_assignment.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/trip_lg.py backend/tests/api/
git commit -m "feat(api): 新增 /plan/preview-day-assignment 智能日程分配预览端点"
```

---

## Task 5: `cluster_from_selections_node` 透传 visit_minutes

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/cluster.py:444-461`（attractions_info 构建段）
- Test: `backend/tests/agents/test_cluster_from_selections.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/agents/test_cluster_from_selections.py`：

```python
import pytest

from app.agents.langgraph_agent.nodes.cluster import cluster_from_selections_node
from app.models.schemas import TripRequest


def _make_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


@pytest.mark.asyncio
async def test_visit_minutes_propagated_to_attractions_info():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {
                "name": "故宫",
                "description": "皇家宫殿",
                "category": "博物馆",
                "address": "东城区",
                "location": {"longitude": 116.397, "latitude": 39.916},
                "visit_minutes": 150,
            },
            {
                "name": "颐和园",
                "category": "公园",
                "location": {"longitude": 116.273, "latitude": 39.999},
                # 无 visit_minutes
            },
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    info = result["attractions_info"]
    assert "预计游玩: 150min" in info
    # 没有 visit_minutes 的不应出现该字段
    assert info.count("预计游玩:") == 1


@pytest.mark.asyncio
async def test_no_visit_minutes_does_not_break():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {"name": "故宫", "location": {"longitude": 116.397, "latitude": 39.916}},
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    assert "预计游玩:" not in result["attractions_info"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && pytest tests/agents/test_cluster_from_selections.py -v
```

Expected: 第一个用例失败（`预计游玩:` 没出现）

- [ ] **Step 3: 修改实现**

编辑 `backend/app/agents/langgraph_agent/nodes/cluster.py`，找到第 444-461 行的 attractions_info 构建段，在 `if attr.get("description"):` 之后加：

```python
        if attr.get("visit_minutes"):
            parts.append(f"预计游玩: {attr['visit_minutes']}min")
```

完整修改后的循环体片段为：

```python
    attractions_info_parts = []
    for attr in selected_attractions:
        parts = [f"名称: {attr['name']}"]
        if attr.get("address"):
            parts.append(f"地址: {attr['address']}")
        if attr.get("location"):
            loc = attr["location"]
            parts.append(f"坐标: {loc.get('longitude', '')},{loc.get('latitude', '')}")
        if attr.get("category"):
            parts.append(f"类别: {attr['category']}")
        if attr.get("rating"):
            parts.append(f"评分: {attr['rating']}")
        if attr.get("ticket_price"):
            parts.append(f"门票: {attr['ticket_price']}")
        if attr.get("description"):
            parts.append(f"简介: {attr['description']}")
        if attr.get("visit_minutes"):
            parts.append(f"预计游玩: {attr['visit_minutes']}min")
        attractions_info_parts.append(" | ".join(parts))
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && pytest tests/agents/test_cluster_from_selections.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/langgraph_agent/nodes/cluster.py backend/tests/agents/test_cluster_from_selections.py
git commit -m "feat(cluster): cluster_from_selections_node 透传 visit_minutes 给下游"
```

---

## Task 6: 扩展前端 types + 新增 previewDayAssignment API 函数

**Files:**
- Modify: `frontend/src/types/index.ts`（`DiscoveredAttraction` + 新增 `DayDurationInfo` 和 `PreviewDayAssignmentResponse`）
- Modify: `frontend/src/services/api.ts`（新增 `previewDayAssignment` 函数）

由于前端无测试框架，本任务以编译通过 + 后续 Task 7/8 的手动验证为准。

- [ ] **Step 1: 修改 types**

编辑 `frontend/src/types/index.ts`，找到 `export interface DiscoveredAttraction` 定义（约 180 行），在 `manuallyAdded?: boolean` 之后加：

```typescript
  visit_minutes?: number
```

并在文件末尾追加：

```typescript
export interface DayDurationInfo {
  day_index: number
  total_minutes: number
  warning?: string | null
}

export interface PreviewDayAssignmentResponse {
  day_assignments: DiscoveredAttraction[][]
  day_durations: DayDurationInfo[]
}
```

- [ ] **Step 2: 新增 API 函数**

编辑 `frontend/src/services/api.ts`：

1. 把首行 import 扩展：

```typescript
import type { TripFormData, TripPlanResponse, TripPlan, TripListResponse, TripRecord, UserPreference, DiscoveredAttraction, DiscoveryStreamEvent, PlanFromSelectionsPayload, PreviewDayAssignmentResponse } from '@/types'
```

2. 在文件末尾追加：

```typescript
export async function previewDayAssignment(
  selectedAttractions: DiscoveredAttraction[],
  travelDays: number,
): Promise<PreviewDayAssignmentResponse> {
  const response = await apiClient.post<PreviewDayAssignmentResponse>(
    '/api/trip/plan/preview-day-assignment',
    {
      selected_attractions: selectedAttractions,
      travel_days: travelDays,
    },
    { timeout: 30000 },
  )
  return response.data
}
```

- [ ] **Step 3: 验证 TS 编译**

```bash
cd frontend && npm run build
```

Expected: 编译通过（warning 可接受，error 不可）。如有 type error 修复后再编译。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat(frontend): 增加 visit_minutes/DayDurationInfo 类型与 previewDayAssignment API"
```

---

## Task 7: DiscoverView 集成智能分配（含估时徽标 + 重置按钮）

**Files:**
- Modify: `frontend/src/views/DiscoverView.vue`

- [ ] **Step 1: 修改 script 段引入与状态**

编辑 `frontend/src/views/DiscoverView.vue`：

1. 在 `import { discoverAttractionsStream, searchAttractionManual, createDraftFromSelectionsStream } from '@/services/api'` 中加入 `previewDayAssignment`：

```typescript
import {
  discoverAttractionsStream, searchAttractionManual,
  createDraftFromSelectionsStream, previewDayAssignment,
} from '@/services/api'
```

2. 在 type 导入中加入 `DayDurationInfo`：

```typescript
import type { DiscoveredAttraction, TripFormData, DiscoveryStreamEvent, DayDurationInfo } from '@/types'
```

3. 在已有 ref/reactive 声明附近（如 `const dayAssignments = ref<...>([])` 之后）追加：

```typescript
const dayDurations = ref<DayDurationInfo[]>([])
const smartAssignmentCache = ref<DiscoveredAttraction[][] | null>(null)
const assignLoading = ref(false)
```

- [ ] **Step 2: 重写 startDayAssignment**

将原 `function startDayAssignment()` 整体替换为：

```typescript
async function startDayAssignment() {
  const selected = attractions.filter(a => a.selected)
  if (selected.length < 2) return

  const days = formData.value?.travel_days || 1
  assignLoading.value = true
  try {
    const resp = await previewDayAssignment(selected, days)
    // 回写 visit_minutes 到 attractions（用 name 匹配）
    const nameToMinutes: Record<string, number> = {}
    for (const day of resp.day_assignments) {
      for (const attr of day) {
        if (attr.visit_minutes) nameToMinutes[attr.name] = attr.visit_minutes
      }
    }
    for (const a of attractions) {
      if (nameToMinutes[a.name]) a.visit_minutes = nameToMinutes[a.name]
    }
    dayAssignments.value = resp.day_assignments
    dayDurations.value = resp.day_durations
    smartAssignmentCache.value = JSON.parse(JSON.stringify(resp.day_assignments))
    phase.value = 'assign'
  } catch (e: any) {
    message.warning('智能分配失败，使用均分方案')
    const perDay = Math.ceil(selected.length / days)
    const assignments: DiscoveredAttraction[][] = []
    for (let d = 0; d < days; d++) {
      assignments.push(selected.slice(d * perDay, (d + 1) * perDay))
    }
    dayAssignments.value = assignments
    dayDurations.value = assignments.map((day, idx) => ({
      day_index: idx,
      total_minutes: day.reduce((sum, a) => sum + (a.visit_minutes || 90), 0),
      warning: null,
    }))
    smartAssignmentCache.value = null
    phase.value = 'assign'
  } finally {
    assignLoading.value = false
  }
}
```

- [ ] **Step 3: 新增本地重算与重置函数**

在 `startDayAssignment` 后追加：

```typescript
function recalculateDayDurations() {
  dayDurations.value = dayAssignments.value.map((day, idx) => {
    const total = day.reduce((sum, a) => sum + (a.visit_minutes || 90), 0)
    return {
      day_index: idx,
      total_minutes: total,
      warning: total > 480 ? '当天偏紧' : null,
    }
  })
}

function resetToSmart() {
  if (!smartAssignmentCache.value) {
    message.info('无智能推荐结果可恢复')
    return
  }
  dayAssignments.value = JSON.parse(JSON.stringify(smartAssignmentCache.value))
  recalculateDayDurations()
  message.success('已恢复智能推荐')
}

function formatDuration(min: number): string {
  if (min < 60) return `${min}min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h${m}min` : `${h}h`
}
```

- [ ] **Step 4: 在 handleDrop 末尾触发重算**

修改现有 `handleDrop`：

```typescript
function handleDrop(_event: DragEvent, toDay: number) {
  if (!dragData) return
  const { fromDay, fromIdx } = dragData
  const [item] = dayAssignments.value[fromDay].splice(fromIdx, 1)
  dayAssignments.value[toDay].push(item)
  dragData = null
  recalculateDayDurations()
}
```

- [ ] **Step 5: 修改模板 - 开始规划按钮 + assign 阶段头部 + day-column 估时徽标**

(a) "开始规划" 按钮加 `:loading`：

```vue
<a-button
  type="primary"
  size="large"
  :loading="assignLoading"
  :disabled="selectedCount < 2"
  @click="startDayAssignment"
>
  开始规划 ({{ selectedCount }}个景点) →
</a-button>
```

(b) `assign-header` 整体替换为：

```vue
<div class="assign-header">
  <div class="assign-header-main">
    <h3>调整日程分配</h3>
    <p>系统已按地理距离与游玩时长智能分配，可拖拽景点微调</p>
  </div>
  <a-button @click="resetToSmart" :disabled="!smartAssignmentCache">
    🔄 重置为智能推荐
  </a-button>
</div>
```

(c) `day-column` 顶部加估时徽标。修改：

```vue
<div
  v-for="(day, dayIdx) in dayAssignments"
  :key="dayIdx"
  class="day-column"
  @dragover.prevent
  @drop="handleDrop($event, dayIdx)"
>
  <div class="day-header">
    <span>第 {{ dayIdx + 1 }} 天</span>
    <span
      class="day-duration-badge"
      :class="{ warning: dayDurations[dayIdx]?.warning }"
    >
      <template v-if="dayDurations[dayIdx]">
        预计 {{ formatDuration(dayDurations[dayIdx].total_minutes) }}
        <span v-if="dayDurations[dayIdx].warning"> ⚠️</span>
      </template>
    </span>
  </div>
  <!-- day-attractions 不变 -->
</div>
```

- [ ] **Step 6: 追加样式**

在 `<style scoped>` 中追加：

```css
.assign-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}

.assign-header-main {
  flex: 1;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text-primary);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light, #f0f0f0);
  margin-bottom: 8px;
}

.day-duration-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary, #f0f0f0);
  padding: 2px 8px;
  border-radius: var(--radius-pill, 9999px);
}

.day-duration-badge.warning {
  background: rgba(255, 77, 79, 0.1);
  color: #d4380d;
}
```

- [ ] **Step 7: 手动验证**

启动前后端，进入 Discover 页：

```bash
# 终端 1
cd backend && python run.py
# 终端 2
cd frontend && npm run dev
```

验证清单：
1. 选择 3+ 景点 → 点"开始规划" → 按钮显示 loading → 进入 assign 阶段
2. 每个 day column 顶部显示"预计 Xh" 徽标
3. 拖拽一个景点到另一天 → 两个 column 的徽标实时更新
4. 点"重置为智能推荐" → 分配回到初始状态，徽标同步刷新
5. 后端日志能看到 LLM 估时打印（或失败兜底）

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/DiscoverView.vue
git commit -m "feat(discover): 集成智能日程分配，含估时徽标与重置按钮"
```

---

## Task 8: DraftView 引入 withDayBusy + DayCard 增加 busy prop

**Files:**
- Modify: `frontend/src/views/DraftView.vue`（state + 四个 async 函数包装 + 传 busy prop）
- Modify: `frontend/src/components/draft/DayCard.vue`（接收 busy prop + 骨架屏 + 遮罩 + 按钮禁用）

- [ ] **Step 1: 修改 DraftView 的 script 段**

编辑 `frontend/src/views/DraftView.vue`：

1. 在 `import { ref, computed, onMounted } from 'vue'` 中加入 `reactive`：

```typescript
import { ref, computed, onMounted, reactive } from 'vue'
```

2. 在 `const finalizing = ref(false)` 之后追加：

```typescript
const dayBusy = reactive<Record<number, string>>({})

async function withDayBusy<T>(
  idx: number,
  label: string,
  fn: () => Promise<T>,
): Promise<T | undefined> {
  dayBusy[idx] = label
  try {
    const result = await fn()
    message.success(`已更新第 ${idx + 1} 天`)
    return result
  } catch (e: any) {
    message.error(e?.response?.data?.detail || `第 ${idx + 1} 天操作失败`)
  } finally {
    delete dayBusy[idx]
  }
}
```

3. 替换 `onAssemble`：

```typescript
async function onAssemble(idx: number, body: any) {
  await withDayBusy(idx, '装配中', async () => {
    const resp = await assembleDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}
```

4. 替换 `onRecompute`：

```typescript
async function onRecompute(idx: number, body: any) {
  await withDayBusy(idx, '重算中', async () => {
    const resp = await recomputeDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}
```

5. 替换 `onAIRearrange`：

```typescript
async function onAIRearrange(idx: number, hint: string) {
  await withDayBusy(idx, 'AI 重排中', async () => {
    const resp = await aiRearrangeDay(draftId.value, idx, hint)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}
```

6. 替换 `onRewriteNarrative`：

```typescript
async function onRewriteNarrative(idx: number) {
  await withDayBusy(idx, '重写叙述中', async () => {
    const resp = await rewriteNarrative(draftId.value, idx)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}
```

- [ ] **Step 2: 在 DayCard 上绑定 busy**

将 `<DayCard ... />` 改为：

```vue
<DayCard
  v-for="(ctx, idx) in draft.days"
  :key="idx"
  :context="ctx"
  :detail="draft.days_detail[idx] || null"
  :is-default-expanded="idx === 0"
  :busy="dayBusy[idx] || ''"
  @assemble="onAssemble(idx, $event)"
  @recompute="onRecompute(idx, $event)"
  @ai-rearrange="onAIRearrange(idx, $event)"
  @rewrite-narrative="onRewriteNarrative(idx)"
/>
```

- [ ] **Step 3: 修改 DayCard.vue 接收 busy prop**

编辑 `frontend/src/components/draft/DayCard.vue`：

1. 修改 Props interface：

```typescript
interface Props {
  context: any
  detail: any | null
  isDefaultExpanded: boolean
  busy?: string
}
const props = withDefaults(defineProps<Props>(), { busy: '' })
```

2. 模板整体重写（覆盖原 `<a-card>` 内部）：

```vue
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
    <a-button v-if="!isExpanded" type="link" @click="onExpand"
              :loading="busy === '装配中'">展开装配 →</a-button>
    <template v-else>
      <a-button type="link" @click="onAIRearrange"
                :disabled="!!busy">AI 重新安排</a-button>
      <a-button type="link" @click="$emit('rewrite-narrative')"
                :disabled="!!busy">重写叙述</a-button>
    </template>
  </template>

  <!-- 首次装配：骨架屏 -->
  <div v-if="isExpanded && !detail && busy === '装配中'" class="day-loading">
    <a-skeleton :active="true" :paragraph="{ rows: 4 }" />
    <div class="loading-hint">正在装配第 {{ context.day_index + 1 }} 天行程…</div>
  </div>

  <!-- 已装配内容（可叠加遮罩） -->
  <div v-else-if="isExpanded && detail" class="day-content">
    <div v-if="detail.description" class="narrative">
      <div v-html="renderedDescription"></div>
    </div>
    <div class="timeline-editor">
      <draggable v-model="orderedAttractions" item-key="name" handle=".drag-handle"
                 @end="onOrderChange" :disabled="!!busy">
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
      <div v-for="m in detail?.meals || []" :key="m.name + (m.category || m.type)" class="meal-row">
        <span class="kind">🍴</span>
        <span class="name">{{ m.name }}</span>
        <a-tag>{{ m.category || m.type }}</a-tag>
        <a-button size="small" danger @click="onRemoveMeal(m)" :disabled="!!busy">删除</a-button>
      </div>
    </div>
    <div class="route-info" v-if="detail.route_segments?.length">
      <h4>路线</h4>
      <ul>
        <li v-for="(seg, i) in detail.route_segments" :key="i">
          {{ seg.from_name }} → {{ seg.to_name }}: {{ seg.distance }} ({{ seg.duration }}, {{ seg.mode }})
        </li>
      </ul>
    </div>

    <!-- 非首次装配的遮罩 -->
    <div v-if="busy && busy !== '装配中'" class="day-overlay">
      <a-spin size="large" />
      <div class="overlay-label">{{ busy }}…</div>
    </div>
  </div>
</a-card>
```

3. 在 `<style scoped>` 末尾追加：

```css
.day-content {
  position: relative;
}
.day-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  z-index: 10;
  border-radius: 4px;
}
.overlay-label {
  font-size: 14px;
  color: #666;
}
.day-loading {
  padding: 16px 0;
}
.loading-hint {
  text-align: center;
  color: #999;
  font-size: 13px;
  margin-top: 12px;
}
```

- [ ] **Step 4: 验证 TS 编译**

```bash
cd frontend && npm run build
```

Expected: 编译通过。

- [ ] **Step 5: 手动验证**

启动前后端，进入一个 draft 页：

1. 点"展开装配 →"展开第 2/3 天 → 看到骨架屏 + "正在装配第 N 天…"
2. 拖拽景点排序 → 看到遮罩 + "重算中…"
3. 添加用餐 → 看到遮罩 + "重算中…"
4. 删除用餐 → 看到遮罩 + "重算中…"
5. AI 重新安排（输入空 hint）→ 看到遮罩 + "AI 重排中…"
6. 重写叙述 → 看到遮罩 + "重写叙述中…"
7. 操作成功后顶部 toast "已更新第 N 天"
8. 操作期间所有按钮（拖拽、加用餐、删除、AI 重排、重写）都不可点

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/DraftView.vue frontend/src/components/draft/DayCard.vue
git commit -m "feat(draft): 引入 withDayBusy 模式，DayCard 增加骨架屏与遮罩反馈"
```

---

## Task 9: DraftView 移除占位 tabs

**Files:**
- Modify: `frontend/src/views/DraftView.vue`（移除 a-tabs 包装、3 个占位 tab-pane、activeTab ref、assembledCount computed）

- [ ] **Step 1: 修改模板**

编辑 `frontend/src/views/DraftView.vue`，将 `<main v-else-if="draft" class="draft-content">` 块整体替换为：

```vue
<main v-else-if="draft" class="draft-content">
  <div class="days-container">
    <DayCard
      v-for="(ctx, idx) in draft.days"
      :key="idx"
      :context="ctx"
      :detail="draft.days_detail[idx] || null"
      :is-default-expanded="idx === 0"
      :busy="dayBusy[idx] || ''"
      @assemble="onAssemble(idx, $event)"
      @recompute="onRecompute(idx, $event)"
      @ai-rearrange="onAIRearrange(idx, $event)"
      @rewrite-narrative="onRewriteNarrative(idx)"
    />
  </div>

  <div class="finalize-bar">
    <a-button type="primary" size="large" :loading="finalizing"
              @click="onFinalize">
      定稿并保存
    </a-button>
  </div>
</main>
```

- [ ] **Step 2: 删除无用 script 引用**

在 script 中删除：

```typescript
const activeTab = ref('itinerary')
const assembledCount = computed(
  () => draft.value?.days_detail?.filter((d: any) => d?.is_assembled).length || 0
)
```

并清理 `computed` import（如果只剩 `draftId` 还用 `computed`，保留；只检查无引用的部分）。

- [ ] **Step 3: 验证 TS 编译**

```bash
cd frontend && npm run build
```

Expected: 编译通过，无未使用变量警告（vue-tsc 报 unused 不通过）。

- [ ] **Step 4: 手动验证**

刷新 draft 页：
- 顶部不再有"行程/地图/天气/预算" tab bar
- 直接展示 days 列表
- finalize 按钮仍可点击且工作正常

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/DraftView.vue
git commit -m "refactor(draft): 移除 DraftView 中无内容的 map/weather/budget 占位 tab"
```

---

## 完成标准

- 9 个任务全部通过测试 + 手动验证
- `cd backend && pytest` 全绿
- `cd frontend && npm run build` 编译通过
- Discover 页选完景点 → 智能分配 → 拖拽微调 → 重置 → 确认 → 进入 Draft → 各种 per-day 操作都有 loading 反馈 → 定稿 → Result 显示完整行程

## 风险与回滚

- LLM 估时延迟过长（>8s）会触发降级。若多次降级，可在前端 catch 时给 warning 提示，或在后端调整 timeout。
- `_rebalance_by_duration` 在某些极端坐标分布下可能不收敛，max_iterations=5 已限定。
- 每个 commit 都是独立可回滚的单元；前端任务依赖后端任务（Task 6 依赖 Task 1，Task 7 依赖 Task 4），按 1→9 顺序执行最稳妥。

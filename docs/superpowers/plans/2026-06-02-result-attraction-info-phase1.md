# 结果页：标签栏不固定 + 景点信息增强（Phase 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让结果页标签栏随内容滚走（切换标签自动回顶），并让景点卡片信息变丰富——通过停止 `cluster_from_selections_node` 丢弃用户已选的景点字段（地址/评分/门票/类别/描述/游览时长/封面图）。

**Architecture:** 纯后端数据串接 + 一处前端样式/交互。后端：`cluster_from_selections_node` 用新纯函数 `_selection_to_cluster_dict` 把已选景点完整转入 `clusters_data`（不再只留 name+坐标）；`_build_day_context` 把这些字段完整映射到 `Attraction`（门票用 `_parse_ticket_price` 把字符串转 int）。聚类辅助函数 `_cluster_attractions_by_proximity`/`_order_cluster_by_tsp` 按引用透传 dict，已核实不会丢字段。前端：删除 `.tab-bar` 的 sticky 定位 + 加切换回顶 watcher。**无数据库改动、无新增 AMap 调用。** 卡片前端对 address/rating/ticket_price/category/visit_duration/description 已有渲染，数据一通即自动丰富。

**Tech Stack:** Python / FastAPI / LangGraph；pytest + pytest-asyncio（strict 模式，async 测试需 `@pytest.mark.asyncio`）；Vue 3 + Vite + TypeScript。

---

## File Structure

- 修改 `backend/app/agents/langgraph_agent/finalize/pipeline.py` — 新增 `_parse_ticket_price`；扩展 `_build_day_context` 的 `Attraction(...)` 字段映射。
- 修改 `backend/app/agents/langgraph_agent/nodes/cluster.py` — 新增 `_selection_to_cluster_dict`；在 `cluster_from_selections_node` 两个分支使用它。
- 测试 `backend/tests/agents/test_finalize_pipeline.py` — 新增 `_parse_ticket_price` 与 `_build_day_context` 测试。
- 测试 `backend/tests/agents/test_cluster_from_selections.py` — 新增 `clusters_data` 富字段测试。
- 修改 `frontend/src/views/Result.vue` — 标签栏去 sticky + 切换回顶。

所有 `pytest` 命令在 `backend/` 目录下执行；`npm` 命令在 `frontend/` 目录下执行。

---

### Task 1: `_parse_ticket_price` 门票字符串转 int 纯函数

**Files:**
- Modify: `backend/app/agents/langgraph_agent/finalize/pipeline.py`
- Test: `backend/tests/agents/test_finalize_pipeline.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/agents/test_finalize_pipeline.py` 顶部 import 区下方追加：

```python
from app.agents.langgraph_agent.finalize.pipeline import _parse_ticket_price


@pytest.mark.parametrize("raw,expected", [
    ("60", 60),
    ("免费", 0),
    (None, 0),
    ("￥80起", 80),
    (120, 120),
    ("", 0),
])
def test_parse_ticket_price(raw, expected):
    assert _parse_ticket_price(raw) == expected
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/agents/test_finalize_pipeline.py::test_parse_ticket_price -v`
Expected: FAIL — `ImportError: cannot import name '_parse_ticket_price'`

- [ ] **Step 3: 实现**

在 `backend/app/agents/langgraph_agent/finalize/pipeline.py` 顶部，把 `import json` 改成：

```python
import json
import re
```

并在 `_make_pseudo_request` 函数定义之前（约第 32 行附近，任意模块级位置即可）新增：

```python
def _parse_ticket_price(val) -> int:
    """把发现页门票字段转成 int 元。

    "60"->60, "免费"->0, "￥80起"->80, None/""/无数字 ->0, 数字原样取整。
    """
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    m = re.search(r"\d+", str(val))
    return int(m.group()) if m else 0
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/agents/test_finalize_pipeline.py::test_parse_ticket_price -v`
Expected: PASS（6 个参数全过）

- [ ] **Step 5: 提交**

```bash
cd /Users/finn/Developer/langgraph-trip-planner/langgraph-trip-planner
git add backend/app/agents/langgraph_agent/finalize/pipeline.py backend/tests/agents/test_finalize_pipeline.py
git commit -m "feat(finalize): 加 _parse_ticket_price 门票字符串转int helper"
```

---

### Task 2: `_selection_to_cluster_dict` + 接入 `cluster_from_selections_node` 两个分支

**Files:**
- Modify: `backend/app/agents/langgraph_agent/nodes/cluster.py:391-416`
- Test: `backend/tests/agents/test_cluster_from_selections.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/agents/test_cluster_from_selections.py` 追加（文件已有 `import pytest`、`cluster_from_selections_node`、`_make_request`）：

```python
from app.agents.langgraph_agent.nodes.cluster import _selection_to_cluster_dict


def test_selection_to_cluster_dict_preserves_fields():
    attr = {
        "name": "故宫", "description": "皇家宫殿", "category": "博物馆",
        "address": "东城区景山前街4号", "rating": 4.8, "ticket_price": "60",
        "image_url": "http://img/gugong.jpg", "poi_id": "B000A8UIN8",
        "location": {"longitude": 116.397, "latitude": 39.916},
        "visit_minutes": 180,
    }
    d = _selection_to_cluster_dict(attr)
    assert d["name"] == "故宫"
    assert d["longitude"] == 116.397
    assert d["latitude"] == 39.916
    assert d["address"] == "东城区景山前街4号"
    assert d["category"] == "博物馆"
    assert d["rating"] == 4.8
    assert d["ticket_price"] == "60"
    assert d["description"] == "皇家宫殿"
    assert d["poi_id"] == "B000A8UIN8"
    assert d["visit_minutes"] == 180
    assert d["image_url"] == "http://img/gugong.jpg"


def test_selection_to_cluster_dict_missing_location_defaults_zero():
    d = _selection_to_cluster_dict({"name": "X"})
    assert d["name"] == "X"
    assert d["longitude"] == 0
    assert d["latitude"] == 0
    assert d["address"] == ""


@pytest.mark.asyncio
async def test_clusters_data_preserves_rich_fields():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {"name": "故宫", "address": "东城区", "rating": 4.8,
             "ticket_price": "60", "category": "博物馆", "description": "皇家宫殿",
             "poi_id": "P1", "image_url": "http://img/1.jpg",
             "location": {"longitude": 116.397, "latitude": 39.916},
             "visit_minutes": 180},
            {"name": "颐和园", "address": "海淀区", "rating": 4.7,
             "ticket_price": "30", "category": "公园", "description": "皇家园林",
             "poi_id": "P2", "image_url": "http://img/2.jpg",
             "location": {"longitude": 116.273, "latitude": 39.999},
             "visit_minutes": 150},
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    flat = [a for cluster in result["clusters_data"] for a in cluster]
    by_name = {a["name"]: a for a in flat}
    assert by_name["故宫"]["address"] == "东城区"
    assert by_name["故宫"]["rating"] == 4.8
    assert by_name["故宫"]["ticket_price"] == "60"
    assert by_name["故宫"]["category"] == "博物馆"
    assert by_name["故宫"]["description"] == "皇家宫殿"
    assert by_name["故宫"]["poi_id"] == "P1"
    assert by_name["故宫"]["visit_minutes"] == 180
    assert by_name["故宫"]["image_url"] == "http://img/1.jpg"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/agents/test_cluster_from_selections.py -v`
Expected: FAIL — `ImportError: cannot import name '_selection_to_cluster_dict'`

- [ ] **Step 3: 实现 helper + 接入两分支**

在 `backend/app/agents/langgraph_agent/nodes/cluster.py` 中 `cluster_from_selections_node` 定义之前（约 380 行上方），新增模块级函数：

```python
def _selection_to_cluster_dict(attr: dict) -> dict:
    """把发现页已选景点（DiscoveredAttraction 形状的 dict）映射成下游用的
    cluster dict，保留全部展示字段（不再只留 name + 坐标）。

    坐标从 location 取，缺失则 0（沿用旧行为，便于无坐标兜底）。
    """
    loc = attr.get("location") or {}
    return {
        "name": attr.get("name", ""),
        "longitude": loc.get("longitude", 0),
        "latitude": loc.get("latitude", 0),
        "address": attr.get("address", ""),
        "category": attr.get("category"),
        "rating": attr.get("rating"),
        "ticket_price": attr.get("ticket_price"),
        "description": attr.get("description", ""),
        "poi_id": attr.get("poi_id"),
        "visit_minutes": attr.get("visit_minutes"),
        "image_url": attr.get("image_url"),
    }
```

替换 `day_assignments` 分支（当前 `cluster.py:393-406`）为：

```python
        print(f"📊 使用用户自定义日程分配: {len(day_assignments)} 天")
        clusters = []
        for day_attrs in day_assignments:
            day_cluster = [_selection_to_cluster_dict(attr) for attr in day_attrs]
            clusters.append(day_cluster)
```

替换 `valid_attractions` 分支的收集循环（当前 `cluster.py:408-416`）为：

```python
        valid_attractions = []
        for attr in selected_attractions:
            loc = attr.get("location")
            if loc and loc.get("longitude") and loc.get("latitude"):
                valid_attractions.append(_selection_to_cluster_dict(attr))
```

（其余逻辑——`dist_matrix`、`_cluster_attractions_by_proximity`、`_order_cluster_by_tsp`、`attractions_info` 构建、返回——保持不变。这两个聚类函数按引用透传 dict，富字段会保留。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/agents/test_cluster_from_selections.py -v`
Expected: PASS（新增 3 个 + 原有 2 个 `test_visit_minutes_*` 仍通过，因为 `attractions_info` 逻辑未动）

- [ ] **Step 5: 提交**

```bash
cd /Users/finn/Developer/langgraph-trip-planner/langgraph-trip-planner
git add backend/app/agents/langgraph_agent/nodes/cluster.py backend/tests/agents/test_cluster_from_selections.py
git commit -m "fix(cluster): cluster_from_selections 保留已选景点全字段，不再砍成name+坐标"
```

---

### Task 3: `_build_day_context` 完整映射 `Attraction` 字段

**Files:**
- Modify: `backend/app/agents/langgraph_agent/finalize/pipeline.py:81-91`
- Test: `backend/tests/agents/test_finalize_pipeline.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/agents/test_finalize_pipeline.py` 追加（文件已 import `DiningPoolDay`、`pytest`、`_sample_macro`）：

```python
from app.agents.langgraph_agent.finalize.pipeline import _build_day_context


def _pool_two_days():
    return [DiningPoolDay().model_dump(mode="json"),
            DiningPoolDay().model_dump(mode="json")]


def test_build_day_context_maps_all_attraction_fields():
    clusters_data = [[{
        "name": "故宫", "longitude": 116.397, "latitude": 39.916,
        "address": "东城区景山前街4号", "category": "博物馆", "rating": 4.8,
        "ticket_price": "60", "description": "皇家宫殿",
        "poi_id": "P1", "visit_minutes": 180, "image_url": "http://img/1.jpg",
    }], []]
    ctx = _build_day_context(
        0, _sample_macro(), clusters_data, [[], []],
        _pool_two_days(), [], "08:00",
    )
    a = ctx.attractions[0]
    assert a.name == "故宫"
    assert a.address == "东城区景山前街4号"
    assert a.category == "博物馆"
    assert a.rating == 4.8
    assert a.ticket_price == 60          # "60" -> int
    assert a.description == "皇家宫殿"
    assert a.visit_duration == 180       # 来自 visit_minutes
    assert a.image_url == "http://img/1.jpg"
    assert a.poi_id == "P1"
    assert a.location.longitude == 116.397


def test_build_day_context_defaults_when_fields_missing():
    clusters_data = [[{"name": "X", "longitude": 116.4, "latitude": 39.9}], []]
    ctx = _build_day_context(
        0, _sample_macro(), clusters_data, [[], []],
        _pool_two_days(), [], "08:00",
    )
    a = ctx.attractions[0]
    assert a.address == ""
    assert a.description == ""
    assert a.visit_duration == 120       # 默认
    assert a.ticket_price == 0
    assert a.category == "景点"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/agents/test_finalize_pipeline.py::test_build_day_context_maps_all_attraction_fields -v`
Expected: FAIL — 断言失败（如 `a.category` 仍是默认 `"景点"` 而非 `"博物馆"`、`a.rating` 为 `None`、`a.ticket_price` 为 `0`），因为当前 `_build_day_context` 只映射了 name/address/location。

- [ ] **Step 3: 实现**

在 `backend/app/agents/langgraph_agent/finalize/pipeline.py` 把 `_build_day_context` 内构造 `Attraction` 的部分（当前 `81-91`）替换为：

```python
    for c in cluster:
        loc = None
        if c.get("longitude") and c.get("latitude"):
            loc = Location(longitude=c["longitude"], latitude=c["latitude"])
        attractions.append(Attraction(
            name=c["name"],
            address=c.get("address") or "",
            visit_duration=c.get("visit_minutes") or 120,
            description=c.get("description") or "",
            category=c.get("category") or "景点",
            rating=c.get("rating"),
            ticket_price=_parse_ticket_price(c.get("ticket_price")),
            image_url=c.get("image_url"),
            poi_id=c.get("poi_id") or "",
            location=loc,
        ))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/agents/test_finalize_pipeline.py -v`
Expected: PASS（新增 2 个 + 原有 3 个 finalize 测试仍通过——它们喂的 `clusters_data` 只有 name+坐标，会安全走默认值）

- [ ] **Step 5: 提交**

```bash
cd /Users/finn/Developer/langgraph-trip-planner/langgraph-trip-planner
git add backend/app/agents/langgraph_agent/finalize/pipeline.py backend/tests/agents/test_finalize_pipeline.py
git commit -m "feat(finalize): _build_day_context 完整映射景点字段(地址/评分/门票/类别/时长/封面图)"
```

---

### Task 4: 前端标签栏不固定 + 切换回顶

**Files:**
- Modify: `frontend/src/views/Result.vue`

本任务无前端单测框架（项目用 `vue-tsc` 做类型检查），以构建通过 + 人工核对验证。

- [ ] **Step 1: 改 CSS——去掉 sticky 定位**

把 `frontend/src/views/Result.vue` 的 `.tab-bar` 规则（约 `560-567`）：

```css
.tab-bar {
  position: sticky;
  top: 64px;
  z-index: var(--z-sticky);
  background: var(--white);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-4) var(--space-6);
}
```

改为（删除前三行）：

```css
.tab-bar {
  background: var(--white);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-4) var(--space-6);
}
```

- [ ] **Step 2: 加 `watch` import**

把 `frontend/src/views/Result.vue` 的（`145` 行）：

```ts
import { ref, computed, onMounted, nextTick } from 'vue'
```

改为：

```ts
import { ref, computed, onMounted, nextTick, watch } from 'vue'
```

- [ ] **Step 3: 加切换回顶 watcher**

在 `visibleTabs` computed 定义之后（约 `201` 行 `})` 之后）新增：

```ts
// 切换标签时回到顶部（标签栏已不再固定，避免停在上一个标签的滚动位置）
watch(activeTab, () => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
})
```

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 构建成功，无 TS / vue-tsc 报错。

- [ ] **Step 5: 人工核对（开发服务器）**

Run: `cd frontend && npm run dev`（后端 `cd backend && python run.py` 同时跑），打开一个行程结果页：
- 向下滚动 → 标签栏跟随内容滚走、**不再钉在顶部**。
- 点击切换标签 → 页面平滑滚回顶部。
- 景点卡片现在显示**地址、简介、评分、门票（有则）、真实游览时长**（不再是空地址 / 120 分钟默认）。

- [ ] **Step 6: 提交**

```bash
cd /Users/finn/Developer/langgraph-trip-planner/langgraph-trip-planner
git add frontend/src/views/Result.vue
git commit -m "feat(result): 标签栏改为不固定，切换标签平滑回顶"
```

---

### Task 5: 全量回归验证

**Files:** 无（仅运行）

- [ ] **Step 1: 跑后端受影响测试**

Run: `cd backend && pytest tests/agents/test_finalize_pipeline.py tests/agents/test_cluster_from_selections.py tests/agents/test_skeleton_graph.py tests/agents/test_rule_assemble_timeline.py -v`
Expected: 全部 PASS（验证 `_build_day_context` / `cluster_from_selections` 改动未破坏装配、骨架图、时间轴）。

- [ ] **Step 2: 跑 agents 目录全量做冒烟**

Run: `cd backend && pytest tests/agents -q`
Expected: 全部 PASS。若有失败，定位是否与本次改动相关；不相关的既有失败记录下来交由用户判断，**不要**标记本计划完成。

---

## Self-Review

**1. Spec coverage（对照 v2 spec 的 Phase 1）：**
- 标签栏不固定 + 切换回顶 → Task 4 ✓
- `cluster_from_selections` 保留 address/rating/ticket_price/category/description/poi_id/visit_minutes/image_url → Task 2 ✓
- `_build_day_context` 全字段映射 + 真实 visit_duration + image_url → Task 3 ✓
- `_parse_ticket_price`（str→int）→ Task 1 ✓
- 卡片前端已有渲染、无需改 → 已在 Architecture 注明 ✓
- 开放时间/电话/缓存表加列 → **不在 Phase 1**（Phase 2 独立计划），spec 已声明 ✓

**2. Placeholder scan：** 无 TBD/TODO；每个代码步骤含完整代码与可运行命令。✓

**3. Type consistency：**
- `_selection_to_cluster_dict`（Task 2）输出的键 `address/category/rating/ticket_price/description/poi_id/visit_minutes/image_url/longitude/latitude` 与 `_build_day_context`（Task 3）读取的 `c.get(...)` 键完全一致。✓
- `_parse_ticket_price`（Task 1）在 Task 3 中被 `_build_day_context` 调用，函数名/位置一致（同文件 `pipeline.py`）。✓
- `ticket_price`：cluster dict 内保持原始字符串（如 `"60"`），到 `_build_day_context` 才用 `_parse_ticket_price` 转 int —— 测试断言与此一致（Task 2 断言 `"60"`，Task 3 断言 `60`）。✓

---

## Phase 2（独立计划，本计划完成后再写）

开放时间 / 电话：`attractions_cache_service` 抓 `biz_ext.opentime_*`/`tel` → `AttractionCache` 表加 2 列 → `CachedAttraction`/discovery item/`DiscoveredAttraction`/`_selection_to_cluster_dict`/`_build_day_context` 透传 → 前端 `Attraction` 类型 + `AttractionCard.vue` 加两行展示。详见 spec `2026-06-02-result-tabbar-attraction-info-design.md` 的 Phase 2 段。

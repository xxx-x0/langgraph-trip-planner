# 智能日程分配与骨架页交互反馈

**日期**: 2026-05-20
**作者**: Claude + finn
**状态**: 待实施

## 背景

用户反馈两个相关问题：

1. **日程分配缺乏智能**：用户在 Discover 页选完景点后，前端 `DiscoverView.startDayAssignment()`
   只是 `Math.ceil(selected.length / days)` 按数量平均切片，完全没用上后端已有的地理聚类算法
   （`_cluster_attractions_by_proximity` + `_order_cluster_by_tsp`）。用户希望"智能根据距离和
   游玩时间安排"，并允许手动微调。

2. **骨架页交互无反馈**：`DraftView` / `DayCard` 中所有 per-day 异步操作（展开装配、AI 重排、
   重写叙述、拖拽排序、添加用餐、删除用餐）都没有任何 loading 状态，用户点击后看到空白
   或瞬间突变，不知道操作是否生效。

3. **骨架页占位 tab**：`DraftView` 中 map/weather/budget 三个 tab 是字符串占位
   （"地图占位"/"天气占位"/"预算占位"），点进去什么都没有。

## 目标

- 用户选完景点点"开始规划"后，自动得到一个基于**地理距离 + LLM 估算游玩时长**的
  日程分配方案；可手动拖拽微调；可一键重置回智能推荐。
- 骨架页所有异步操作都有明确的 loading 反馈，用户始终知道当前在做什么。
- 移除骨架页中无实际内容的 map/weather/budget 占位 tab。

## 非目标

- 不重写 Discover → Planning 整体流程，只在 assign 阶段插入智能算法。
- 不实现骨架页的真实 map/weather/budget 内容（已在最终 Result 页有，不重复）。
- 不实现乐观 UI（添加/删除用餐立即显示再异步确认），仅做 loading 态以避免错误回滚的复杂度。

---

## 一、智能日程分配

### 1.1 用户流程

1. Discover 页：用户选景点（不变）
2. 点击"开始规划 (N个景点) →"
3. **新增**：前端调用 `POST /api/trip/preview-day-assignment`，UI 显示"正在智能分配…"（2-3s）
4. 进入 assign 阶段，展示后端返回的分配方案：
   - 每个 day column 顶部显示估时徽标，如 `预计 5.5h`
   - 超过 8h 标红显示"⚠️ 当天偏紧"
5. 用户可继续拖拽调整；拖拽时本地实时重算 day 总时长
6. 顶部新增"重置为智能推荐"按钮：清空当前手动调整，恢复后端推荐
7. 点"确认并生成行程"调用 `plan_from_selections`（不变，但 selected_attractions 现在带
   `visit_minutes` 字段透传给下游）

### 1.2 后端改动

#### `backend/app/agents/langgraph_agent/utils/duration.py`（新文件）

```python
CATEGORY_DURATION_MAP = {
    "博物馆": 120, "公园": 60, "寺庙": 90, "古迹": 75,
    "美食": 45, "购物": 90, "景点": 90, "default": 90,
}

async def estimate_durations_batch(
    attractions: list[dict],  # [{name, description, category}]
    timeout_seconds: float = 8.0,
) -> dict[str, int]:
    """
    LLM 一次性估算所有景点的游玩时长（分钟）。
    返回 {name: minutes}。
    失败/超时时降级到 CATEGORY_DURATION_MAP。
    """
```

实现要点：
- Prompt 让 LLM 输出严格 JSON 数组：`[{"name": "...", "visit_minutes": 90, "reason": "..."}]`
- 使用现有 `_invoke_llm_with_retry` 复用重试逻辑
- 使用 `asyncio.wait_for` 套 timeout
- 失败时遍历 attractions，用 `CATEGORY_DURATION_MAP.get(category, 90)` 兜底
- 解析时校验 minutes 在 `[15, 480]` 区间，越界用默认值

#### `backend/app/agents/langgraph_agent/utils/geo.py`（扩展）

新增 `_rebalance_by_duration`：

```python
def _rebalance_by_duration(
    clusters: list[list[dict]],
    durations: dict[str, int],
    max_minutes: int = 480,
    max_iterations: int = 5,
) -> list[list[dict]]:
    """
    若某天总时长 > max_minutes，把离该天质心最远的景点
    移到时长最少且地理上仍接近的相邻日。
    最多迭代 max_iterations 轮，无法继续优化时停止。
    """
```

算法：
- 计算每个 cluster 的 (total_minutes, centroid_lat, centroid_lon)
- while iterations < max_iterations:
  - 找出 total_minutes 最大的 cluster
  - 如果未超 max_minutes，break
  - 找出该 cluster 中离质心最远的 attraction
  - 找出剩余 clusters 中 total_minutes 最小、且与该 attraction 距离最近的目标
  - 如果移动后目标 cluster 仍 < max_minutes，执行移动；否则 break
- 返回平衡后的 clusters（每个 cluster 用 `_order_cluster_by_tsp` 重新排序）

#### `backend/app/models/schemas.py`（修改）

`DiscoveredAttraction` 增加可选字段：

```python
visit_minutes: Optional[int] = Field(default=None, description="预估游玩时长(分钟)")
```

#### `backend/app/api/routes/trip_lg.py`（新增端点）

```python
@router.post("/plan/preview-day-assignment")
async def preview_day_assignment(req: PreviewDayAssignmentRequest):
    """
    输入：选中景点 + 天数
    输出：智能分配方案 + 每天估时
    纯计算（地理 + LLM 估时），不调用 MCP、不入数据库。
    """
```

Request schema：
```python
class PreviewDayAssignmentRequest(BaseModel):
    selected_attractions: List[DiscoveredAttraction]
    travel_days: int
```

Response schema：
```python
class DayDurationInfo(BaseModel):
    day_index: int
    total_minutes: int
    warning: Optional[str] = None  # 如 "当天偏紧"

class PreviewDayAssignmentResponse(BaseModel):
    day_assignments: List[List[DiscoveredAttraction]]  # 每个 attr 带 visit_minutes
    day_durations: List[DayDurationInfo]
```

端点逻辑：
1. 调 `estimate_durations_batch(selected_attractions)` 获取每景点 minutes
2. 把 minutes 写回每个 attraction 的 `visit_minutes` 字段
3. 把 attractions 转为 geo 用的 dict 格式（{name, longitude, latitude}）
4. 调 `_cluster_attractions_by_proximity(geo_attrs, travel_days)`
5. 调 `_rebalance_by_duration(clusters, durations)`
6. 每个 cluster 内用 `_order_cluster_by_tsp` 排序
7. 把 cluster 中的 geo dict 还原成完整的 DiscoveredAttraction（带 visit_minutes）
8. 计算 day_durations，超 480min 标 warning
9. 返回

#### `backend/app/agents/langgraph_agent/nodes/cluster.py`（小改）

`cluster_from_selections_node`：如果 `selected_attractions` 中已有 `visit_minutes`，
透传给下游节点（用于后续 day_plan 阶段避免重复估时）。透传方式：写入 `attractions_info`
拼接字符串时增加 "预计游玩: Xmin" 字段。

### 1.3 前端改动

#### `frontend/src/types/index.ts`（修改）

```typescript
export interface DiscoveredAttraction {
  // ...existing fields
  visit_minutes?: number  // 新增
}

export interface DayDurationInfo {
  day_index: number
  total_minutes: number
  warning?: string
}
```

#### `frontend/src/services/api.ts`（新增函数）

```typescript
export async function previewDayAssignment(
  selectedAttractions: DiscoveredAttraction[],
  travelDays: number,
): Promise<{
  day_assignments: DiscoveredAttraction[][]
  day_durations: DayDurationInfo[]
}>
```

#### `frontend/src/views/DiscoverView.vue`（修改）

- 新增 ref `assignLoading = ref(false)` 和 `dayDurations = ref<DayDurationInfo[]>([])`
- `startDayAssignment()` 改为 async：
  1. 设 `assignLoading = true`
  2. 调 `previewDayAssignment(selected, days)`
  3. 把返回的 `day_assignments` 赋给 `dayAssignments.value`
  4. 把 `day_durations` 赋给 `dayDurations.value`
  5. 把每个 attraction 的 `visit_minutes` 同步回 `attractions` 数组（用 name 匹配）
  6. 失败时降级到原来的 `Math.ceil` 均分逻辑 + `message.warning('智能分配失败，使用均分方案')`
  7. `phase.value = 'assign'`
  8. 设 `assignLoading = false`
- 加载状态：在 "开始规划" 按钮旁加 `:loading="assignLoading"`
- assign 阶段 UI：
  - day-column 顶部加估时徽标 `<div class="day-duration">预计 {{ formatDuration(dur) }}</div>`，
    超限加 `.warning` 类（红字 + ⚠️）
  - 拖拽时 `handleDrop` 之后立即调用 `recalculateDayDurations()` 本地重算
  - assign-header 右侧加 "重置为智能推荐" 按钮，调用 `resetToSmart()` 把 cached 的智能推荐
    重新赋值

- 缓存智能推荐：新增 `smartAssignmentCache = ref<DiscoveredAttraction[][] | null>(null)`，
  preview 接口返回后保存一份深拷贝；reset 时从 cache 恢复

- "确认并生成行程" 调用 `createDraftFromSelectionsStream` 时，selected 数组里的
  `visit_minutes` 字段自动透传到后端

#### `frontend/src/services/api.ts` 中的 `createDraftFromSelectionsStream`（无需改动）

只要请求体里的 attraction 对象包含 `visit_minutes` 字段，后端 Pydantic 模型已扩展即可接收。

### 1.4 降级策略

- **LLM 估时失败/超时**：兜底用 `CATEGORY_DURATION_MAP`，前端无感
- **预览接口整体失败**：前端 catch 后降级到原 `Math.ceil` 均分 + 提示
- **景点缺失坐标**：跳过这些景点的几何计算，使用其在 selected 中的顺序作为兜底

---

## 二、骨架页交互反馈

### 2.1 问题盘点

| 操作 | 当前 | 修复后 |
|------|------|--------|
| 展开装配（点"展开装配 →"） | 点完空白 | 整张 card 内容区骨架屏 + "正在装配第 N 天…" |
| AI 重新安排（点"AI 重新安排"） | 静默 → 突变 | 整张 card 半透明遮罩 + 中央 spin + "AI 重排中…" |
| 重写叙述（点"重写叙述"） | 静默 → 突变 | 整张 card 半透明遮罩 + 中央 spin + "重写叙述中…" |
| 拖拽景点排序 | 无反馈，500ms 防抖后突变 | 拖完立即显示遮罩 + "重新计算路线…" |
| 添加用餐（popover 内点候选） | popover 关闭后无反馈 | popover 关闭，整张 card 遮罩 + "重新计算路线…" |
| 删除用餐（点"删除"） | 静默 → 突变 | 整张 card 遮罩 + "重新计算路线…" |
| 定稿（点"定稿并保存"） | 已有 `finalizing` flag | 保持不变 |

### 2.2 实现方案

#### `frontend/src/views/DraftView.vue`（修改）

集中管理 per-day 忙状态：

```typescript
const dayBusy = reactive<Record<number, string>>({})  // {0: '装配中', 1: '', ...}

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

包装现有四个异步函数：

```typescript
async function onAssemble(idx: number, body: any) {
  await withDayBusy(idx, '装配中', async () => {
    const resp = await assembleDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}

async function onRecompute(idx: number, body: any) {
  await withDayBusy(idx, '重算中', async () => {
    const resp = await recomputeDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}

async function onAIRearrange(idx: number, hint: string) {
  await withDayBusy(idx, 'AI 重排中', async () => {
    const resp = await aiRearrangeDay(draftId.value, idx, hint)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}

async function onRewriteNarrative(idx: number) {
  await withDayBusy(idx, '重写叙述中', async () => {
    const resp = await rewriteNarrative(draftId.value, idx)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}
```

把 `:busy="dayBusy[idx] || ''"` 传给 `<DayCard>`。

#### `frontend/src/components/draft/DayCard.vue`（修改）

新增 prop：

```typescript
interface Props {
  context: any
  detail: any | null
  isDefaultExpanded: boolean
  busy?: string  // '' / '装配中' / '重算中' / 'AI 重排中' / '重写叙述中'
}
```

模板结构调整：

```vue
<a-card>
  <template #title>...</template>
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

  <!-- 初次装配：骨架屏 -->
  <div v-if="isExpanded && !detail && busy === '装配中'" class="day-loading">
    <a-skeleton :active="true" :paragraph="{ rows: 4 }" />
    <div class="loading-hint">正在装配第 {{ context.day_index + 1 }} 天行程…</div>
  </div>

  <!-- 已装配的内容（遮罩在内容外） -->
  <div v-else-if="isExpanded && detail" class="day-content" :class="{ 'is-busy': !!busy }">
    <!-- 原来的 narrative / timeline-editor / route-info 内容 -->
    ...

    <!-- 遮罩：busy 非空且不是首次装配 -->
    <div v-if="busy && busy !== '装配中'" class="day-overlay">
      <a-spin size="large" />
      <div class="overlay-label">{{ busy }}…</div>
    </div>
  </div>
</a-card>
```

样式：

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
  border-radius: var(--radius-md, 8px);
}
.overlay-label {
  font-size: 14px;
  color: var(--color-text-secondary);
}
.day-loading {
  padding: 16px 0;
}
.loading-hint {
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 13px;
  margin-top: 12px;
}
```

DayCard 内的局部按钮（删除用餐、加用餐 popover）保持原样，因为遮罩会覆盖它们。

### 2.3 错误处理

`withDayBusy` catch 块统一弹 `message.error`，原 `detail` 保持不变（不变成 null），
用户看到错误提示但 UI 不会"消失"。

---

## 三、移除骨架页占位 tab

### `frontend/src/views/DraftView.vue`（修改）

- 删除 `<a-tabs>` 整个包装层
- 删除 `<a-tab-pane key="map">`、`key="weather"`、`key="budget"` 三个面板
- 删除 `activeTab` ref
- 删除 `assembledCount` computed（仅 budget tab 用过）
- 顶层 `<main>` 直接渲染 `<div class="days-container">`

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

---

## 测试要点

### 后端
- `estimate_durations_batch`：mock LLM 返回 valid/invalid/timeout，验证降级
- `_rebalance_by_duration`：构造超限/不超限/无法平衡的场景，验证迭代收敛
- `preview-day-assignment` 端点：端到端，含坐标缺失场景

### 前端
- DiscoverView：手动验证 preview 调用、降级到均分、估时徽标显示、超限警告、
  拖拽后重算、"重置为智能推荐"按钮
- DraftView：手动验证每个操作的 loading 状态都能看到
- 骨架页 tab 移除：手动验证 finalize 流程不受影响

## 风险与权衡

- **LLM 估时延迟 2-3s**：用户能感知，但比"假分配"+"后台真聚类"的体验更直观
- **降级方案可能差异较大**：CATEGORY_DURATION_MAP 比 LLM 粗糙，但极少触发
- **遮罩可能遮住用户正在操作的按钮**：可接受，因为操作本身就是异步排队的

## 变更文件列表

**后端新增**
- `backend/app/agents/langgraph_agent/utils/duration.py`

**后端修改**
- `backend/app/agents/langgraph_agent/utils/geo.py`（新增 `_rebalance_by_duration`）
- `backend/app/agents/langgraph_agent/nodes/cluster.py`（透传 visit_minutes）
- `backend/app/models/schemas.py`（`DiscoveredAttraction.visit_minutes` 字段、
  `PreviewDayAssignmentRequest/Response` schemas）
- `backend/app/api/routes/trip_lg.py`（新增端点）

**前端修改**
- `frontend/src/types/index.ts`（`visit_minutes`、`DayDurationInfo`）
- `frontend/src/services/api.ts`（`previewDayAssignment`）
- `frontend/src/views/DiscoverView.vue`（智能分配集成、估时徽标、重置按钮）
- `frontend/src/views/DraftView.vue`（`dayBusy` 状态、`withDayBusy` 包装、移除占位 tab）
- `frontend/src/components/draft/DayCard.vue`（`busy` prop、骨架屏、遮罩）

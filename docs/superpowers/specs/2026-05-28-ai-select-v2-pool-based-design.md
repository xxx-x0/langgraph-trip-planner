# AI 帮我选 v2 — 池内 LLM 挑选（替代 Bing 攻略提取）

- 日期：2026-05-28
- 关联 spec：`docs/superpowers/specs/2026-05-26-discovery-planning-improvements-design.md` Module 2
- 状态：替换原 Module 2 的"从攻略提取"实现

## 背景

原 v1 实现（commits c94b888 / 2585a49 / 58a625a）走 Bing 搜索"<城市> <天数>日游 经典攻略" → LLM 提取景点名 → 模糊匹配到池子。线上测试反馈：

- 经常返回"未找到适合的攻略"（Bing 命中弱 / snippet 太短不足以提取景点）
- 模糊匹配规则收紧（>=3 字符）后误命中变少，但同时漏匹配率也升高
- 景点池里高质量的景点（rating 高）反而可能不在攻略文本里出现

外部搜索质量不可控 → 用户期望"AI 帮我选"是一次即得的体验，不能让外部 SEO 决定推荐质量。

## 新设计：池内 LLM 挑选

不再依赖外部攻略，把景点池本身当作 LLM 的候选集，让 LLM 基于"目的地 + 天数 + 偏好 + 每个景点的预估时长"在池内挑选。

### 核心改进

1. **时长预算驱动**（替代 `days × 5` 硬编码）
   - 目标总时长 `days × 7 小时`（420 min/天）
   - LLM 自己根据每个景点的 `visit_duration` 决定挑多少 — 文化历史多的城市可能 days×3，主题乐园可能 days×7
   - 解决"死板"问题

2. **分级输出（must / optional）**
   - LLM 输出两层：`must`（必去，~days × 6h）+ `optional`（备选，额外 ~days × 2h）
   - 前端：must 默认勾选，optional 不勾让用户决定
   - 解决"全选还是部分选"的纠结

3. **可靠兜底**
   - LLM 失败时：按 rating 降序取 `must = top days×3`, `optional = next days×2`
   - 永远有结果，不再"找不到攻略"

## 后端设计

### 新工具：`pick_attractions_from_pool`

位置：`backend/app/agents/langgraph_agent/utils/strategy_extract.py` 末尾新增（旧函数保留供后续清理）

签名：

```python
async def pick_attractions_from_pool(
    destination: str,
    days: int,
    pool: List[Dict[str, Any]],
    preferences: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """从景点池中挑选推荐项，返回 {must_ids, optional_ids}。"""
```

流程：

1. 用 `estimate_durations_batch(pool)` 拿到 `{name: minutes}` 映射；失败时默认 120 分钟
2. 构造 prompt：destination / days / preferences / 池内每个景点的 `name, category, rating, visit_duration`
3. LLM 输出 JSON `{"must": [{poi_id, reason}], "optional": [{poi_id, reason}]}`，要求：
   - must 总 visit_duration ≈ days × 360 min（6h/天）
   - optional 额外 ≈ days × 120 min（2h/天）
4. 失败兜底：`_rating_based_fallback(pool, days)`
   - rating 解析为 float（解析失败按 0 处理）
   - rating 降序：must = top `days*3`，optional = next `days*2`

### 端点更新：`POST /api/discover/ai_select`

`AISelectResponse` schema 改为：

```python
class AISelectResponse(BaseModel):
    must_ids: List[str]
    optional_ids: List[str]
```

去掉 `recommended_ids` 和 `source_strategy_title`。

调用：`extract_attractions_from_strategy` → 改调 `pick_attractions_from_pool`。

### Prompt 设计

```
你是行程规划助手。请从下面这个 {destination} 的景点池里，
为一个 {days} 天的行程挑选必去和备选景点。

行程目标：
- 必去景点（must）：总游览时长约 {days * 360} 分钟（6 小时/天）
- 备选景点（optional）：额外约 {days * 120} 分钟（2 小时/天）

用户偏好：{preferences or '无特别偏好'}

景点池（poi_id | 名称 | 类别 | 评分 | 预估时长 min）：
{pool 列表...}

输出 JSON：
{
  "must": [{"poi_id": "xxx", "reason": "为什么必去"}],
  "optional": [{"poi_id": "xxx", "reason": "为什么备选"}]
}
```

## 前端设计

### 数据模型

`SelectableAttraction` 类型加一个可选字段（不修改 backend 返回，前端本地标记）：

```ts
interface SelectableAttraction {
  // ... 现有字段
  recommendation?: 'must' | 'optional' | null
}
```

### handleAiSelect 改造

```ts
const res = await aiSelectAttractions({ destination, days, attractions, preferences })

// 清除上一轮推荐标记
attractions.forEach(a => { a.recommendation = null })

const mustSet = new Set(res.must_ids)
const optionalSet = new Set(res.optional_ids)
let mustCount = 0
let optionalCount = 0

attractions.forEach(a => {
  if (a.poi_id && mustSet.has(a.poi_id)) {
    a.recommendation = 'must'
    a.selected = true
    mustCount++
  } else if (a.poi_id && optionalSet.has(a.poi_id)) {
    a.recommendation = 'optional'
    // 不修改 selected
    optionalCount++
  }
})

message.success(`已为你推荐 ${mustCount} 个必去 + ${optionalCount} 个备选`)
```

### 三分区渲染

DiscoverView 新增 computed：

```ts
const aiSelectionActive = computed(
  () => attractions.some(a => a.recommendation)
)

const filteredByCategory = computed(() => /* 现有 category filter */)

const mustAttractions = computed(
  () => filteredByCategory.value.filter(a => a.recommendation === 'must')
)
const optionalAttractions = computed(
  () => filteredByCategory.value.filter(a => a.recommendation === 'optional')
)
const otherAttractions = computed(
  () => filteredByCategory.value.filter(a => !a.recommendation)
)
```

模板：

```vue
<template v-if="aiSelectionActive">
  <section v-if="mustAttractions.length > 0" class="reco-section reco-must">
    <h3 class="section-title">⭐ AI 推荐必去</h3>
    <div class="attractions-grid">
      <SelectableAttractionCard v-for="a in mustAttractions" :key="a.name" :attraction="a" @toggle="toggleAttraction" />
    </div>
  </section>
  <section v-if="optionalAttractions.length > 0" class="reco-section reco-optional">
    <h3 class="section-title">💡 备选推荐</h3>
    <div class="attractions-grid">...</div>
  </section>
  <section v-if="otherAttractions.length > 0" class="reco-section reco-other">
    <h3 class="section-title">其他景点</h3>
    <div class="attractions-grid">...</div>
  </section>
</template>
<template v-else>
  <!-- 现有单列表 -->
</template>
```

### 分类筛选继续生效

`filteredByCategory` 先过滤 → 再分区，保证两个交互正交。

## 测试

### 新建 `tests/agents/test_pick_from_pool.py`

涵盖：
- `_rating_based_fallback`：按 rating 降序、days × 3 / days × 2 切分
- `pick_attractions_from_pool` 调用 LLM 失败时退到兜底
- `pick_attractions_from_pool` LLM 成功时返回正确格式

### 改 `tests/api/test_ai_select.py`

- 把 `recommended_ids` 改为 `must_ids` + `optional_ids`
- 422 / 500 测试保留

### 测试不需要：

- Bing 调用相关测试（保留但本次不强化）
- match_names_to_pool 测试（保留，函数暂不删除）

## 实施任务拆分

- **Task v2-1**：后端 — 新工具 `pick_attractions_from_pool` + 兜底 + 单元测试
- **Task v2-2**：后端 — 端点改造 + schema 更新 + API 测试更新
- **Task v2-3**：前端 — 三分区渲染 + handleAiSelect 适配

## 不在范围内

- 不删除旧 `extract_attractions_from_strategy` / `match_names_to_pool` / `normalize_name`（避免污染本次 diff，后续清理）
- 不改后端 SSE 协议
- 不重写偏好系统（preferences 来源沿用现有传参）
- 不引入"节奏 toggle"（紧凑/标准/宽松）— 留作 follow-up

## 已知 trade-off

- LLM 候选完全限定在景点池里 — 如果池子里没有某个"经典必看"，AI 不会推荐它。前期用 Task 2.x 的"加载更多"按钮可以让用户主动扩容。
- LLM 估时不准时（DeepSeek 偶尔输出 0 或 999），兜底是默认 120 min。前端不会因此崩。

# 加载页 Bauhaus 重设计 — Phase A（CONSTRUCTION）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Discover→Draft 之间的加载体验改成一张 Bauhaus 海报式全屏 overlay，并通过 GSAP Flip 让海报的红色 Hero 块平滑"演变"成草稿页 Hero，同时消除草稿页原本的 10 秒 `a-spin` 断层。

**Architecture:** 新增模块级单例状态机 composable `useTripLoader`（纯逻辑，TDD）。新增全局组件 `BauhausLoader.vue` 挂在 `App.vue` 顶层，`position: fixed` 横跨路由切换，消费状态机。`DiscoverView` 用 `begin('construction')` 启动 loader 并把 SSE 节点事件喂给 `updateProgress`；路由切到 `/draft/:id` 后由 `DraftView` 在第一天装配完成时调 `markReady()`，触发 `Flip.fit()` 把 loader 的 Hero 块吸附到草稿页 Hero。

**Tech Stack:** Vue 3 (`<script setup>`)、TypeScript、GSAP（core + Flip + SplitText）、Vitest + happy-dom（仅用于状态机单元测试）、既有 Bauhaus CSS tokens（`frontend/src/styles/bauhaus-tokens.css`）。

---

## 范围与非范围

**本计划做：** Phase A 完整垂直切片 —— CONSTRUCTION 海报 + Discover→Draft 的 Flip 过渡 + reduced-motion 降级 + SSE 错误撤场。完成后是一个可独立运行、可目视验收的功能。

**本计划不做（留待 Phase B 下一轮 brainstorm+plan）：**
- Poster B（REFINEMENT）构图
- `DraftView.onFinalize` → `Result.vue` 的 refinement loader 接入
- 用户主动取消按钮（spec §7.3，次要优化）

状态机 `useTripLoader` 设计成 poster 无关（`poster` 只是透传字符串），Phase B 复用时无需改状态机。`BauhausLoader` 本计划只实现 `construction` 模板；`refinement` 分支暂留一个最小占位（不渲染内容），Phase B 再补。

---

## 测试策略（已与用户确认：混合）

- **状态机 `useTripLoader`**：TDD，Vitest + happy-dom（纯逻辑，高价值）。
- **其余（BauhausLoader 渲染、GSAP 入场/steady、Flip 变形、接入改动）**：靠 `npm run build`（vue-tsc 类型检查）作为自动门 + 手动 `npm run dev` 目视验证。原因：happy-dom 无布局引擎，`getBoundingClientRect` 返回全 0，Flip / 动画无法被有意义地单测。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `frontend/package.json` | 加 `gsap` 依赖、`vitest`/`happy-dom`/`@vue/test-utils` devDep、`test` 脚本 | Modify |
| `frontend/vitest.config.ts` | Vitest 配置（happy-dom + `@` alias），独立于 vite.config.ts 不干扰构建 | Create |
| `frontend/src/main.ts` | 注册 GSAP Flip + SplitText 插件 | Modify |
| `frontend/src/composables/useTripLoader.ts` | 加载状态机单例 + 公开 API | Create |
| `frontend/src/composables/__tests__/useTripLoader.test.ts` | 状态机单元测试 | Create |
| `frontend/src/components/loader/constructionSteps.ts` | LangGraph 节点 → 中文标签映射 + 进度计算（供状态条复用） | Create |
| `frontend/src/components/loader/BauhausLoader.vue` | 全屏 overlay 海报组件，消费状态机，含 GSAP timeline + Flip | Create |
| `frontend/src/App.vue` | 在 `#app` 内挂 `<BauhausLoader />` | Modify |
| `frontend/src/views/DiscoverView.vue` | `confirmAndPlan` 改用 `useTripLoader`，移除内联 `<PlanProgress>` | Modify |
| `frontend/src/views/DraftView.vue` | Hero 加 `data-flip-id="loader-hero"` 锚点、移除 `a-spin`、第一天装配后 `markReady()` | Modify |

---

## Task 1: 安装依赖与测试脚手架

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: 安装运行时与测试依赖**

Run（在 `frontend/` 目录）:
```bash
npm install gsap
npm install -D vitest happy-dom @vue/test-utils
```
Expected: `package.json` 中 `dependencies` 出现 `gsap`，`devDependencies` 出现 `vitest` / `happy-dom` / `@vue/test-utils`。

- [ ] **Step 2: 加 test 脚本**

修改 `frontend/package.json` 的 `scripts`，加入：
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

- [ ] **Step 3: 创建 Vitest 配置**

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
  },
})
```

- [ ] **Step 4: 在 main.ts 注册 GSAP 插件**

修改 `frontend/src/main.ts`，在现有 import 之后、`createRouter` 之前加入插件注册（GSAP 插件应在 app 级注册一次）：
```ts
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(Flip, SplitText)
```
（放在 `import App from './App.vue'` 等 import 之后即可。）

- [ ] **Step 5: 验证构建通过**

Run（在 `frontend/`）: `npm run build`
Expected: vue-tsc 与 vite build 均成功，无类型错误（确认 GSAP 类型可解析）。

- [ ] **Step 6: 验证 Vitest 能跑（空跑）**

Run: `npm run test`
Expected: vitest 启动并报告 "No test files found"（此时还没写测试），进程退出码 0 或提示无测试 —— 关键是 vitest 配置本身能加载、happy-dom 环境可用。

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/main.ts
git commit -m "chore(frontend): 引入 GSAP 与 Vitest，注册 Flip/SplitText 插件"
```

---

## Task 2: useTripLoader 状态机（TDD）

**Files:**
- Create: `frontend/src/composables/useTripLoader.ts`
- Test: `frontend/src/composables/__tests__/useTripLoader.test.ts`

状态机是模块级单例（所有调用方共享同一个 reactive store）。phase 迁移：
`idle → entering →(setSteady)→ steady →(markReady)→ flipping →(finishFlip)→ idle`，任意活动态可被 `dismiss()` 拉回 `idle`。

- [ ] **Step 1: 写失败测试**

Create `frontend/src/composables/__tests__/useTripLoader.test.ts`:
```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { useTripLoader } from '@/composables/useTripLoader'

const ctx = { city: '北京', days: 5, attractionCount: 12 }

describe('useTripLoader 状态机', () => {
  beforeEach(() => {
    useTripLoader().reset()
  })

  it('初始为 idle，无 context', () => {
    const { state } = useTripLoader()
    expect(state.phase).toBe('idle')
    expect(state.context).toBeNull()
    expect(state.poster).toBeNull()
  })

  it('begin 进入 entering 并存下 poster/context', () => {
    const { begin, state } = useTripLoader()
    begin('construction', ctx)
    expect(state.phase).toBe('entering')
    expect(state.poster).toBe('construction')
    expect(state.context).toEqual(ctx)
  })

  it('setSteady 仅在 entering 时生效', () => {
    const loader = useTripLoader()
    loader.setSteady()
    expect(loader.state.phase).toBe('idle') // idle 时无效
    loader.begin('construction', ctx)
    loader.setSteady()
    expect(loader.state.phase).toBe('steady')
  })

  it('updateProgress 更新节点/消息/进度', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.updateProgress('macro_planner', '编排骨架', 62)
    expect(loader.state.currentNode).toBe('macro_planner')
    expect(loader.state.currentMessage).toBe('编排骨架')
    expect(loader.state.progress).toBe(62)
  })

  it('markReady 从 entering 或 steady 进入 flipping', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.setSteady()
    loader.markReady()
    expect(loader.state.phase).toBe('flipping')
  })

  it('markReady 在 idle 时无效', () => {
    const loader = useTripLoader()
    loader.markReady()
    expect(loader.state.phase).toBe('idle')
  })

  it('finishFlip 从 flipping 回 idle 并清空 context', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.markReady()
    loader.finishFlip()
    expect(loader.state.phase).toBe('idle')
    expect(loader.state.context).toBeNull()
  })

  it('dismiss 从任意活动态拉回 idle', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.setSteady()
    loader.dismiss()
    expect(loader.state.phase).toBe('idle')
    expect(loader.state.context).toBeNull()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `frontend/`）: `npm run test`
Expected: FAIL，报 `Failed to resolve import '@/composables/useTripLoader'`（模块还不存在）。

- [ ] **Step 3: 写最小实现**

Create `frontend/src/composables/useTripLoader.ts`:
```ts
import { reactive, readonly } from 'vue'

export type LoaderPoster = 'construction' | 'refinement'
export type LoaderPhase = 'idle' | 'entering' | 'steady' | 'flipping'

export interface LoaderContext {
  city: string
  days: number
  attractionCount: number
  weatherSummary?: string
}

interface LoaderStore {
  phase: LoaderPhase
  poster: LoaderPoster | null
  context: LoaderContext | null
  currentNode: string
  currentMessage: string
  progress: number
}

// 模块级单例：所有调用方共享同一份状态
const store = reactive<LoaderStore>({
  phase: 'idle',
  poster: null,
  context: null,
  currentNode: '',
  currentMessage: '',
  progress: 0,
})

function reset(): void {
  store.phase = 'idle'
  store.poster = null
  store.context = null
  store.currentNode = ''
  store.currentMessage = ''
  store.progress = 0
}

export function useTripLoader() {
  function begin(poster: LoaderPoster, context: LoaderContext): void {
    store.poster = poster
    store.context = context
    store.currentNode = ''
    store.currentMessage = ''
    store.progress = 0
    store.phase = 'entering'
  }

  function setSteady(): void {
    if (store.phase === 'entering') store.phase = 'steady'
  }

  function updateProgress(node: string, message: string, progress: number): void {
    store.currentNode = node
    store.currentMessage = message
    store.progress = progress
  }

  function markReady(): void {
    if (store.phase === 'entering' || store.phase === 'steady') {
      store.phase = 'flipping'
    }
  }

  function finishFlip(): void {
    reset()
  }

  function dismiss(): void {
    reset()
  }

  return {
    state: readonly(store),
    begin,
    setSteady,
    updateProgress,
    markReady,
    finishFlip,
    dismiss,
    reset,
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm run test`
Expected: PASS，8 个测试全绿。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useTripLoader.ts frontend/src/composables/__tests__/useTripLoader.test.ts
git commit -m "feat(loader): useTripLoader 加载状态机（TDD）"
```

---

## Task 3: 构建步骤常量与进度映射

**Files:**
- Create: `frontend/src/components/loader/constructionSteps.ts`

把 LangGraph 节点的中文标签集中到一处（复用自 `DiscoverView.vue` 现有 `planningSteps`，避免重复定义），并提供按"已完成节点数 / 总数"算百分比的纯函数。状态条 label 与进度都从这里取。

- [ ] **Step 1: 创建常量与帮助函数**

Create `frontend/src/components/loader/constructionSteps.ts`:
```ts
// CONSTRUCTION（Discover→Draft）阶段的 LangGraph 节点顺序与中文标签。
// 与 DiscoverView.vue 的 planningSteps 保持一致。
export interface ConstructionStep {
  key: string
  label: string
}

export const CONSTRUCTION_STEPS: ConstructionStep[] = [
  { key: 'cluster_from_selections', label: '聚类分析景点' },
  { key: 'search_food', label: '搜索美食' },
  { key: 'search_hotel', label: '搜索酒店' },
  { key: 'plan_route', label: '规划路线' },
  { key: 'macro_planner', label: '编排行程骨架' },
  { key: 'day_plan_subgraph', label: '生成每日行程' },
  { key: 'reduce_assemble', label: '合并行程数据' },
  { key: 'global_synthesizer', label: '生成全局建议' },
]

export const CONSTRUCTION_TOTAL = CONSTRUCTION_STEPS.length

/** 给定当前节点 key，返回其中文标签；未知节点返回兜底文案。 */
export function labelForNode(nodeKey: string): string {
  return CONSTRUCTION_STEPS.find((s) => s.key === nodeKey)?.label ?? '规划中'
}

/** 给定当前节点 key，按其在序列中的序号算完成百分比（0-100，取整）。 */
export function progressForNode(nodeKey: string): number {
  const idx = CONSTRUCTION_STEPS.findIndex((s) => s.key === nodeKey)
  if (idx < 0) return 0
  return Math.round(((idx + 1) / CONSTRUCTION_TOTAL) * 100)
}
```

- [ ] **Step 2: 验证类型/构建**

Run（在 `frontend/`）: `npm run build`
Expected: 构建成功，无类型错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/loader/constructionSteps.ts
git commit -m "feat(loader): CONSTRUCTION 节点标签与进度映射常量"
```

---

## Task 4: BauhausLoader 静态海报外壳（无 GSAP）

**Files:**
- Create: `frontend/src/components/loader/BauhausLoader.vue`
- Modify: `frontend/src/App.vue`

先把海报的**静态构图**搭出来（纯 CSS，CSS 关键帧旋转黄圆即可），用状态机的 `phase !== 'idle'` 控制显隐。GSAP 入场/Flip 留到后续 Task。本 Task 目标：路由层面手动把 phase 设成 entering 时，能看到一张正确的 Bauhaus 海报铺满全屏。

构图依据 spec §5 与 mockup `.superpowers/brainstorm/51605-1779963574/content/02-poster-a-construction.html`。

- [ ] **Step 1: 创建 BauhausLoader.vue（静态版）**

Create `frontend/src/components/loader/BauhausLoader.vue`:
```vue
<template>
  <div v-if="state.phase !== 'idle'" class="bh-loader" role="status" aria-live="polite">
    <!-- CONSTRUCTION 海报 -->
    <div v-if="state.poster === 'construction'" ref="posterRef" class="bh-poster">
      <!-- 贯穿垂直轴线 -->
      <div ref="axisRef" class="bh-axis"></div>

      <!-- 左上：旋转黄圆 -->
      <div ref="circleRef" class="bh-circle"></div>

      <!-- 右上：corner tag -->
      <div ref="cornerRef" class="bh-corner">CONSTRUCTING · {{ stepIndexLabel }}</div>

      <!-- 中左：巨型天数 -->
      <div ref="megaRef" class="bh-mega">{{ ctx.days }}</div>

      <!-- 中右：Flip 源（红色 Hero 块） -->
      <div ref="heroRef" class="bh-hero" data-flip-source="loader-hero">
        <div class="bh-hero-cn">{{ ctx.city }}</div>
        <div class="bh-hero-en">{{ cityEn }}</div>
        <div class="bh-hero-line"></div>
        <div class="bh-hero-meta">{{ ctx.weatherSummary || 'YOUR TRIP' }}</div>
      </div>

      <!-- 左下：蓝三角 -->
      <div ref="triangleRef" class="bh-triangle"></div>

      <!-- 右下：黄方块（景点数） -->
      <div ref="squareRef" class="bh-square">
        <div class="bh-square-n">{{ ctx.attractionCount }}</div>
        <div class="bh-square-lbl">SPOTS</div>
      </div>

      <!-- 底部状态条 -->
      <div ref="statusRef" class="bh-status">
        <span class="bh-status-node">▶ {{ nodeLabel }}</span>
        <div class="bh-status-bar"><div class="bh-status-fill" :style="{ width: progressPct + '%' }"></div></div>
        <span class="bh-status-pct">{{ progressPct }}%</span>
      </div>
    </div>

    <!-- REFINEMENT 海报：Phase B 实现，暂留占位 -->
    <div v-else class="bh-poster bh-poster--placeholder"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTripLoader, type LoaderContext } from '@/composables/useTripLoader'
import { labelForNode, progressForNode, CONSTRUCTION_STEPS, CONSTRUCTION_TOTAL } from './constructionSteps'

const { state } = useTripLoader()

// 元素 ref（GSAP Task 用得到，先声明）
const posterRef = ref<HTMLElement | null>(null)
const axisRef = ref<HTMLElement | null>(null)
const circleRef = ref<HTMLElement | null>(null)
const cornerRef = ref<HTMLElement | null>(null)
const megaRef = ref<HTMLElement | null>(null)
const heroRef = ref<HTMLElement | null>(null)
const triangleRef = ref<HTMLElement | null>(null)
const squareRef = ref<HTMLElement | null>(null)
const statusRef = ref<HTMLElement | null>(null)

// context 兜底，避免 null 解构崩溃
const ctx = computed<LoaderContext>(() => state.context ?? { city: '', days: 0, attractionCount: 0 })

const cityEn = computed(() => (ctx.value.city ? ctx.value.city.toUpperCase() : ''))

const nodeLabel = computed(() => labelForNode(state.currentNode))

// 进度：优先用节点序号推算；若 state.progress 已被显式设置则取较大值，保证单调
const progressPct = computed(() => {
  const byNode = progressForNode(state.currentNode)
  return Math.max(byNode, state.progress || 0)
})

const stepIndexLabel = computed(() => {
  const idx = CONSTRUCTION_STEPS.findIndex((s) => s.key === state.currentNode)
  const human = idx < 0 ? 0 : idx + 1
  return `${String(human).padStart(2, '0')}/${String(CONSTRUCTION_TOTAL).padStart(2, '0')}`
})
</script>

<style scoped>
.bh-loader {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: #faf8f3;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.bh-poster {
  position: relative;
  width: 100%;
  height: 100%;
  font-family: var(--font-family);
}

.bh-axis {
  position: absolute;
  left: 38%;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--foreground);
  opacity: 0.85;
}

.bh-circle {
  position: absolute;
  top: 5vh;
  left: 5vw;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--primary-yellow);
  border: 3px solid var(--foreground);
  box-shadow: 4px 4px 0 var(--foreground);
}
.bh-circle::after {
  content: '';
  position: absolute;
  inset: 9px;
  border-radius: 50%;
  border: 3px solid var(--foreground);
  border-right-color: transparent;
  animation: bh-spin 2.5s linear infinite;
}
@keyframes bh-spin { to { transform: rotate(360deg); } }

.bh-corner {
  position: absolute;
  top: 5vh;
  right: 5vw;
  background: var(--foreground);
  color: #fff;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

.bh-mega {
  position: absolute;
  left: 6vw;
  top: 50%;
  transform: translateY(-50%);
  font-size: clamp(160px, 32vw, 360px);
  line-height: 0.8;
  font-weight: 900;
  color: var(--foreground);
  letter-spacing: -0.06em;
}

.bh-hero {
  position: absolute;
  right: 8vw;
  top: 50%;
  transform: translateY(-50%);
  background: var(--primary-red);
  color: #fff;
  padding: 32px 44px 28px;
  border: 3px solid var(--foreground);
  box-shadow: 8px 8px 0 var(--foreground);
  min-width: 260px;
}
.bh-hero-cn { font-size: 52px; font-weight: 900; line-height: 1; letter-spacing: -0.02em; }
.bh-hero-en { font-size: 16px; letter-spacing: 0.42em; margin-top: 8px; opacity: 0.92; }
.bh-hero-line { height: 2px; background: #fff; opacity: 0.5; margin: 18px 0 14px; }
.bh-hero-meta { font-size: 13px; letter-spacing: 0.14em; font-weight: 700; }

.bh-triangle {
  position: absolute;
  bottom: 12vh;
  left: 8vw;
  width: 0;
  height: 0;
  border-left: 34px solid transparent;
  border-right: 34px solid transparent;
  border-bottom: 58px solid var(--primary-blue);
  transform: rotate(15deg);
  filter: drop-shadow(3px 3px 0 var(--foreground));
}

.bh-square {
  position: absolute;
  bottom: 12vh;
  right: 8vw;
  width: 104px;
  height: 104px;
  background: var(--primary-yellow);
  border: 3px solid var(--foreground);
  box-shadow: 4px 4px 0 var(--foreground);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.bh-square-n { font-size: 44px; font-weight: 900; line-height: 1; }
.bh-square-lbl { font-size: 10px; letter-spacing: 0.16em; margin-top: 3px; }

.bh-status {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--foreground);
  color: #fff;
  padding: 14px 5vw;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.12em;
}
.bh-status-bar { flex: 1; height: 4px; background: rgba(255,255,255,0.18); margin: 0 24px; }
.bh-status-fill { height: 100%; background: var(--primary-yellow); transition: width 0.4s ease; }

.bh-poster--placeholder { background: #faf8f3; }

@media (max-width: 640px) {
  .bh-hero { right: 5vw; padding: 20px 24px; min-width: 180px; }
  .bh-hero-cn { font-size: 34px; }
  .bh-circle { width: 52px; height: 52px; }
  .bh-square { width: 76px; height: 76px; }
}
</style>
```

- [ ] **Step 2: 在 App.vue 挂载 loader**

修改 `frontend/src/App.vue`：先在 `<script setup>` 引入组件：
```ts
import { useTheme } from '@/composables/useTheme'
import BauhausLoader from '@/components/loader/BauhausLoader.vue'

const { resolvedTheme, toggleTheme } = useTheme()
```
再在模板里把 `<BauhausLoader />` 放到 `</a-layout>` 之后、`</div>`（`#app`）之前：
```vue
      <a-layout-footer class="app-footer">
        <span>Let's Go! 智能旅行助手 ©2025</span>
      </a-layout-footer>
    </a-layout>
    <BauhausLoader />
  </div>
</template>
```

- [ ] **Step 3: 临时手测海报渲染**

在 `BauhausLoader.vue` 的 `<script setup>` 末尾**临时**加一段调试代码（验证后删除）：
```ts
// TODO(临时调试，Step 5 删除)
import { onMounted } from 'vue'
const { begin } = useTripLoader()
onMounted(() => begin('construction', { city: '北京', days: 5, attractionCount: 12, weatherSummary: 'SUMMER · 2026' }))
```

Run（在 `frontend/`）: `npm run dev`，浏览器打开 `http://localhost:5173`
Expected: 全屏出现 Bauhaus 海报 —— 左上旋转黄圆、巨型"5"、右侧红块"北京 / BEIJING"、右下黄方块"12 SPOTS"、底部黑色状态条。目视确认构图、配色（红/蓝/黄/黑）、响应式无明显错位。

- [ ] **Step 4: 删除临时调试代码**

移除 Step 3 加入的 `onMounted` 调试块与多余 import，`BauhausLoader.vue` 回到由外部状态机驱动。

- [ ] **Step 5: 验证构建**

Run: `npm run build`
Expected: 成功，无类型错误。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/loader/BauhausLoader.vue frontend/src/App.vue
git commit -m "feat(loader): BauhausLoader 静态海报外壳 + App 顶层挂载"
```

---

## Task 5: DiscoverView 接入 loader（替换内联 PlanProgress）

**Files:**
- Modify: `frontend/src/views/DiscoverView.vue`

让 `confirmAndPlan()` 用 `useTripLoader().begin('construction')` 启动全局 loader；SSE `node_complete` 喂给 `updateProgress`；`complete` 事件**立即** `router.push('/draft/:id')`（不再 `setTimeout`，loader 横跨路由保持显示，由 DraftView 接力 `markReady`）；`error` 调 `dismiss()`。移除 `phase === 'planning'` 分支里的 `<PlanProgress>`。

参考现状：`confirmAndPlan` 在 `frontend/src/views/DiscoverView.vue:510-574`；planning 模板分支在 `:187-198`。

- [ ] **Step 1: 引入 composable 与进度映射**

在 `DiscoverView.vue` 的 `<script setup>` import 区加入：
```ts
import { useTripLoader } from '@/composables/useTripLoader'
import { labelForNode, progressForNode } from '@/components/loader/constructionSteps'
```
并在 setup 顶部（其它 ref 声明附近）取得 loader：
```ts
const tripLoader = useTripLoader()
```

- [ ] **Step 2: 改写 confirmAndPlan 的事件处理**

把 `confirmAndPlan()`（约 `:510`）中 `phase.value = 'planning'` 之后的 loader 启动与回调改为：
```ts
  phase.value = 'planning'

  const selected = attractions.filter(a => a.selected)

  // 启动全局 Bauhaus 加载海报（CONSTRUCTION）
  tripLoader.begin('construction', {
    city: formData.value.city,
    days: formData.value.travel_days,
    attractionCount: selected.length,
    weatherSummary: weatherInfo.value || undefined,
  })

  try {
    await createDraftFromSelectionsStream(
      formData.value,
      selected.map(a => ({
        name: a.name,
        description: a.description,
        address: a.address,
        category: a.category,
        rating: a.rating,
        ticket_price: a.ticket_price,
        image_url: a.image_url,
        location: a.location,
        poi_id: a.poi_id,
        visit_minutes: a.visit_minutes,
      })),
      dayAssignments.value.map(day =>
        day.map(a => ({
          name: a.name,
          description: a.description,
          address: a.address,
          category: a.category,
          rating: a.rating,
          ticket_price: a.ticket_price,
          image_url: a.image_url,
          location: a.location,
          poi_id: a.poi_id,
          visit_minutes: a.visit_minutes,
        }))
      ),
      weatherInfo.value,
      (event: DraftStreamEvent) => {
        if (event.type === 'node_complete' && event.node) {
          tripLoader.setSteady()
          tripLoader.updateProgress(
            event.node,
            event.message || labelForNode(event.node),
            progressForNode(event.node),
          )
        } else if (event.type === 'complete' && event.draft_id) {
          // 立即切路由；loader 保持显示，由 DraftView 在第一天装配后 markReady 触发 Flip
          router.push(`/draft/${event.draft_id}`)
        } else if (event.type === 'error') {
          tripLoader.dismiss()
          message.error(event.message || '骨架生成失败')
          phase.value = 'assign'
        }
      }
    )
  } catch (e: any) {
    tripLoader.dismiss()
    message.error('规划失败: ' + (e.message || '未知错误'))
    phase.value = 'assign'
  }
```

> 注意：旧代码里 `complete` 分支的 `message.success('骨架生成完成!')` 与 `setTimeout(...router.push...)` 一并删除（成功提示由海报本身承担，不再弹 toast）。

- [ ] **Step 3: 移除内联 PlanProgress 渲染**

把 planning 阶段模板分支（约 `:187-198`）替换为空壳（全局 loader 已覆盖整屏，底层无需再渲染步骤清单）：
```vue
    <!-- 阶段3: 规划中（由全局 BauhausLoader 覆盖展示） -->
    <div v-else-if="phase === 'planning'" class="planning-layout"></div>
```

- [ ] **Step 4: 清理不再使用的 PlanProgress 相关代码**

- 删除 import：`import PlanProgress from '@/components/PlanProgress.vue'`
- 删除不再被模板使用的 planning 状态变量：`planningCurrentNode`、`planningCompletedNodes`、`planningMessage`、`planningSteps`（约 `:248-260`）。
- 若 `PlanProgress` 在文件中已无其它引用，保留组件文件本身（其它视图可能仍用），仅移除本文件的 import 与变量。

> 验证无残留引用：`grep -n "planningCurrentNode\|planningCompletedNodes\|planningMessage\|planningSteps\|PlanProgress" frontend/src/views/DiscoverView.vue` 应无输出。

- [ ] **Step 5: 验证构建**

Run（在 `frontend/`）: `npm run build`
Expected: 成功，无类型错误、无 "declared but never used" 报错。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/DiscoverView.vue
git commit -m "feat(loader): DiscoverView 改用全局 BauhausLoader，移除内联 PlanProgress"
```

---

## Task 6: DraftView 接入 — Flip 锚点 + 移除 a-spin + 接力 markReady

**Files:**
- Modify: `frontend/src/views/DraftView.vue`

草稿页 Hero 加一个 `data-flip-id="loader-hero"` 的红色锚点元素（Flip 目标）；移除 `a-spin "加载草稿中"`（被全局 loader 覆盖）；在 `loadDraft()` + 第一天 `onAssemble(0)` 都完成后调 `markReady()` 触发 Flip。

参考现状：`frontend/src/views/DraftView.vue` 整文件（1-140），hero 在 `:3-9`，`loading` 控制 `a-spin` 在 `:11`，`loadDraft` 在 `:76-89`，`onMounted(loadDraft)` 在 `:126`。

- [ ] **Step 1: Hero 加 Flip 锚点元素**

把 `frontend/src/views/DraftView.vue` 的 `<header class="draft-hero">`（`:3-9`）改为包含一个红色锚点块（无条件渲染，保证 markReady 时 DOM 已存在）：
```vue
    <header class="draft-hero">
      <div class="draft-hero-anchor" data-flip-id="loader-hero">
        <span class="draft-hero-city">{{ draft?.city || '行程' }}</span>
        <span class="draft-hero-days">{{ draft?.request?.travel_days || '' }} 日</span>
      </div>
      <div class="meta" v-if="draft">
        {{ draft.request.start_date }} 至 {{ draft.request.end_date }} ·
        {{ draft.request.travel_days }} 天
      </div>
    </header>
```

- [ ] **Step 2: 移除 a-spin**

删除 `:11` 行的 `<a-spin v-if="loading" tip="加载草稿中..." />`。把主体内容渲染条件从 `v-else-if="draft"` 调整为 `v-if="draft"`（因为不再有 `a-spin` 占据 `v-if` 链）：
```vue
    <main v-if="draft" class="draft-content">
```
`<a-empty v-else ...>` 保持不变（draft 加载失败时仍展示）。

- [ ] **Step 3: 引入 loader 并在数据就绪后 markReady**

在 `<script setup>` import 区加入：
```ts
import { useTripLoader } from '@/composables/useTripLoader'
```
取得 loader（在 `const draft = ref...` 附近）：
```ts
const tripLoader = useTripLoader()
```
改写 `loadDraft()`（`:76-89`），在 try 块成功路径末尾、`finally` 之前触发 markReady：
```ts
async function loadDraft() {
  loading.value = true
  try {
    draft.value = await getDraft(draftId.value)
    // 自动展开并装配第 1 天
    if (draft.value && !draft.value.days_detail[0]) {
      await onAssemble(0, {})
    }
    // 草稿与第一天内容已就绪：若从 Discover 接力来的 loader 仍在，触发 Flip 收束
    if (tripLoader.state.phase !== 'idle') {
      await nextTick()
      tripLoader.markReady()
    }
  } catch (e: any) {
    tripLoader.dismiss() // 直接撤场，露出下方错误/空态
    message.error(e?.response?.data?.detail || '加载草稿失败')
  } finally {
    loading.value = false
  }
}
```
在文件顶部的 Vue import 补上 `nextTick`：
```ts
import { ref, computed, onMounted, reactive, nextTick } from 'vue'
```

- [ ] **Step 4: 给锚点加 Bauhaus 样式**

在 `DraftView.vue` 的 `<style scoped>` 末尾追加：
```css
.draft-hero-anchor {
  display: inline-flex;
  align-items: baseline;
  gap: 12px;
  background: var(--primary-red);
  color: #fff;
  padding: 16px 24px;
  border: 3px solid var(--foreground);
  box-shadow: 6px 6px 0 var(--foreground);
}
.draft-hero-city { font-size: 32px; font-weight: 900; line-height: 1; letter-spacing: -0.02em; }
.draft-hero-days { font-size: 16px; font-weight: 700; letter-spacing: 0.1em; opacity: 0.9; }
```

- [ ] **Step 5: 验证构建**

Run（在 `frontend/`）: `npm run build`
Expected: 成功，无类型错误。

- [ ] **Step 6: 端到端目视（无 Flip，先验证接力不卡死）**

Run: `npm run dev`，完整走一遍：Home 填表 → Discover 选景点 → 确认生成。
Expected:
- 点"确认并生成行程"后立即全屏出现 CONSTRUCTION 海报；
- 底部状态条随后端节点推进更新文案与百分比；
- 路由切到 `/draft/:id` 期间海报**不消失**（无中途白屏 / 无 `a-spin`）；
- 草稿第一天装配完成后，海报消失，露出草稿页（此刻 Flip 尚未实现，表现为海报直接隐藏，可接受）。
> 若海报一直不消失：检查 `markReady` 是否被调用、`tripLoader.state.phase` 是否到了 `flipping`（Task 7 会在 BauhausLoader 里消费 flipping 并最终 finishFlip；当前 Task 尚未实现 flipping→idle，故海报会停在 flipping。**这是预期**，下一 Task 修复）。

> 说明：本 Task 结束时 phase 会停在 `flipping` 且海报不会自动消失，因为消费 `flipping` 的逻辑在 Task 7。如需本 Task 独立验收"接力链路通"，可临时在 `markReady()` 后直接 `tripLoader.finishFlip()` 观察海报消失，验证后改回 `markReady()`。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/DraftView.vue
git commit -m "feat(loader): DraftView 加 Flip 锚点、移除 a-spin、就绪后 markReady"
```

---

## Task 7: GSAP 入场 + steady + Flip 收束动画

**Files:**
- Modify: `frontend/src/components/loader/BauhausLoader.vue`

给 BauhausLoader 接上 GSAP：`watch` phase 变化，`entering` 播放入场 timeline（spec §5 幕1-3）、`steady` 进入轻微浮动循环（幕4），`flipping` 先飞散装饰、再用 **`Flip.fit()`** 把红块吸附到草稿页 `[data-flip-id="loader-hero"]`（幕5），onComplete 调 `finishFlip()`。用 `gsap.matchMedia()` 处理 reduced-motion。

> **Flip 机制修正（相对 spec §4.4）：** spec 描述的 "getState + detach data-flip-id + from()" 在两个不同 DOM 元素间不成立——`Flip.from(state)` 动画的是 getState 捕获的元素引用，不重查 selector。正确做法是 `Flip.fit(源元素, 目标元素, {...})`：把 loader 的红块（`heroRef`，标记 `data-flip-source`）吸附到草稿页锚点（`document.querySelector('[data-flip-id="loader-hero"]')`）。两个元素用**不同**标记，避免 selector 冲突。

- [ ] **Step 1: 引入 GSAP 与生命周期，建立 context**

在 `BauhausLoader.vue` 的 `<script setup>` 顶部补充 import 与清理逻辑：
```ts
import { computed, ref, watch, onUnmounted, nextTick } from 'vue'
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'
import { useTripLoader, type LoaderContext } from '@/composables/useTripLoader'
import { labelForNode, progressForNode, CONSTRUCTION_STEPS, CONSTRUCTION_TOTAL } from './constructionSteps'

const { state, setSteady, finishFlip } = useTripLoader()
```
（替换原 `const { state } = useTripLoader()` 行。）

声明动画句柄与清理：
```ts
let entranceTl: gsap.core.Timeline | null = null
let steadyTl: gsap.core.Timeline | null = null
let splitInstance: SplitText | null = null
// 用 ReturnType 推导，避免依赖具体类型名（不同 gsap 版本类型导出名不一）
let mm: ReturnType<typeof gsap.matchMedia> | null = null

function killAll() {
  entranceTl?.kill(); entranceTl = null
  steadyTl?.kill(); steadyTl = null
  splitInstance?.revert(); splitInstance = null
  mm?.revert(); mm = null
}

onUnmounted(killAll)
```

- [ ] **Step 2: 入场 + steady timeline**

在 `<script setup>` 中加入播放函数：
```ts
function playEntrance() {
  killAll()
  if (!posterRef.value) return

  mm = gsap.matchMedia()

  mm.add('(prefers-reduced-motion: no-preference)', () => {
    const tl = gsap.timeline({
      defaults: { ease: 'power3.out' },
      onComplete: () => {
        setSteady()
        startSteady()
      },
    })
    entranceTl = tl

    // 幕1 SCAFFOLD：轴线划下
    tl.from(axisRef.value, { scaleY: 0, transformOrigin: 'top', duration: 0.6 })

    // 幕2 SHAPES IN：几何件入场
    tl.from(circleRef.value, { y: -120, opacity: 0, duration: 0.5, ease: 'back.out(1.7)' }, 0.5)
      .from(triangleRef.value, { rotation: -90, opacity: 0, duration: 0.5 }, 0.6)
      .from(squareRef.value, { x: 120, y: 120, opacity: 0, duration: 0.5 }, 0.7)
      .from(cornerRef.value, { opacity: 0, y: -10, duration: 0.4 }, 0.7)

    // 幕3 DATA REVEAL：大数字、红块、城市名、状态条
    tl.from(megaRef.value, { scale: 0.6, opacity: 0, duration: 0.6, ease: 'back.out(1.7)' }, 1.0)
      .from(heroRef.value, { x: 160, opacity: 0, duration: 0.6 }, 1.2)
      .from(statusRef.value, { y: 60, opacity: 0, duration: 0.5 }, 1.3)

    // 城市名字符级浮现
    if (heroRef.value) {
      const cnEl = heroRef.value.querySelector('.bh-hero-cn')
      if (cnEl) {
        splitInstance = SplitText.create(cnEl as HTMLElement, { type: 'chars' })
        tl.from(splitInstance.chars, { opacity: 0, y: 20, stagger: 0.05, duration: 0.4 }, 1.5)
      }
    }

    return () => { tl.kill(); entranceTl = null }
  })

  // reduced-motion：直接静态显示，立刻 steady
  mm.add('(prefers-reduced-motion: reduce)', () => {
    setSteady()
    return () => {}
  })
}

function startSteady() {
  if (!circleRef.value) return
  // 红块极轻微 breathing + 三角 floaty（仅 no-preference 下；reduce 模式不调用此函数路径动画）
  steadyTl = gsap.timeline({ repeat: -1, yoyo: true })
  steadyTl.to(heroRef.value, { scale: 1.005, duration: 3, ease: 'sine.inOut' })
    .to(triangleRef.value, { y: -8, duration: 2.4, ease: 'sine.inOut' }, 0)
}
```

- [ ] **Step 3: Flip 收束**

加入收束函数：
```ts
async function playFlipDismiss() {
  const dest = document.querySelector<HTMLElement>('[data-flip-id="loader-hero"]')

  // 找不到目标（异常）：直接结束
  if (!dest || !heroRef.value) {
    finishFlip()
    return
  }

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (reduce) {
    // 降级：整屏淡出，不做位置变形
    gsap.to('.bh-loader', { opacity: 0, duration: 0.2, onComplete: finishFlip })
    return
  }

  steadyTl?.kill(); steadyTl = null

  // 装饰元素先飞散/淡出
  const decor = [axisRef.value, circleRef.value, cornerRef.value, megaRef.value, triangleRef.value, squareRef.value, statusRef.value].filter(Boolean)
  await gsap.to(decor, { opacity: 0, scale: 0.9, duration: 0.3, stagger: 0.04, ease: 'power2.in' })

  // 让 loader 背景透出底层草稿页
  gsap.to('.bh-loader', { backgroundColor: 'rgba(250,248,243,0)', duration: 0.4 })

  // 把 loader 红块吸附到草稿页锚点（FLIP fit）
  Flip.fit(heroRef.value, dest, {
    duration: 0.7,
    ease: 'power3.inOut',
    absolute: true,
    scale: true,
    onComplete: () => {
      gsap.to(heroRef.value, {
        opacity: 0,
        duration: 0.2,
        onComplete: finishFlip,
      })
    },
  })
}
```

- [ ] **Step 4: watch phase 驱动动画**

加入 watcher（放在所有函数定义之后）：
```ts
watch(
  () => state.phase,
  async (phase, prev) => {
    if (phase === 'entering' && prev === 'idle') {
      await nextTick()
      playEntrance()
    } else if (phase === 'flipping') {
      await nextTick()
      playFlipDismiss()
    }
  },
)
```

- [ ] **Step 5: 验证构建**

Run（在 `frontend/`）: `npm run build`
Expected: 成功，无类型错误（确认 `gsap/Flip`、`gsap/SplitText` 类型可解析）。

- [ ] **Step 6: 端到端目视 — 完整 Flip**

Run: `npm run dev`，完整走 Home → Discover → 确认生成。
Expected:
- 海报入场有"轴线划下 → 几何件弹入 → 大数字/红块/城市名字符浮现"的分幕动效；
- steady 期间红块轻微呼吸、三角轻微漂浮、状态条随节点更新；
- 第一天装配完成后：装饰件飞散，**红块平滑飞向并贴合草稿页 Hero 锚点位置/尺寸**，随后淡出露出草稿页 Hero，海报卸载；
- 全程无白屏闪烁、无双重 Hero 残影。
> Flip 贴合若有偏差：调 `Flip.fit` 的 `absolute` / `scale` 选项；锚点与红块的内边距/字号越接近，贴合越自然。

- [ ] **Step 7: 目视 reduced-motion 降级**

在系统设置开启"减少动态效果"（macOS：系统设置 → 辅助功能 → 显示 → 减少动态效果），重跑一遍。
Expected: 海报静态出现（无入场动画），收束为整屏淡出（无飞行变形），状态条仍正常更新。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/loader/BauhausLoader.vue
git commit -m "feat(loader): GSAP 入场/steady 动画 + Flip.fit 收束 + reduced-motion 降级"
```

---

## Task 8: 错误与超时降级加固

**Files:**
- Modify: `frontend/src/views/DiscoverView.vue`
- Modify: `frontend/src/components/loader/BauhausLoader.vue`

确保异常路径下 loader 不会"卡在屏幕上"：SSE error / 网络异常已在 Task 5 调 `dismiss()`；本 Task 补一个保险超时，并确保路由意外离开时 loader 复位。

- [ ] **Step 1: 保险超时**

在 `DiscoverView.vue` 的 `confirmAndPlan()` 中，`tripLoader.begin(...)` 之后加一个 90s 看门狗，并在 `complete`/`error`/`catch` 处清除：
```ts
  tripLoader.begin('construction', { /* ...如 Task 5 */ })

  const watchdog = window.setTimeout(() => {
    if (tripLoader.state.phase !== 'idle' && tripLoader.state.phase !== 'flipping') {
      message.warning('生成耗时较长，请耐心等待…')
    }
  }, 90000)
```
在 `complete`（成功切路由前）、`error`、`catch` 三处都加 `window.clearTimeout(watchdog)`。

> 说明：看门狗只提示、不强制撤场（后端可能仍在正常出结果）；真正的失败由 SSE `error` / `catch` 的 `dismiss()` 兜底。

- [ ] **Step 2: 路由卸载兜底**

在 `BauhausLoader.vue` 已有的 `onUnmounted(killAll)` 基础上无需额外处理（loader 是全局常驻，不随路由卸载）。但要防止"用户在 loader 显示期间点浏览器返回"导致状态残留：在 `BauhausLoader.vue` 加一个对 `flipping` 长时间未完成的兜底——若进入 `flipping` 后 1.5s 仍未 `finishFlip`（例如目标锚点意外缺失且未命中 Step3 的 null 分支），强制复位：
```ts
// 放在 playFlipDismiss 内部，函数开头
const safety = window.setTimeout(() => finishFlip(), 1500)
// 并在该函数所有 finishFlip() 调用点之前 clearTimeout(safety)，
// 最稳妥：把 safety 提到模块作用域，finishFlip 包一层本地 wrapper：
```
落地实现（替换 Task 7 Step 3 的 `playFlipDismiss`，加入 safety 清理）：
```ts
let flipSafety: number | null = null
function doFinish() {
  if (flipSafety !== null) { window.clearTimeout(flipSafety); flipSafety = null }
  finishFlip()
}
```
把 `playFlipDismiss` 内所有 `finishFlip` 调用改为 `doFinish`，并在函数开头设 `flipSafety = window.setTimeout(doFinish, 1500)`（reduce 分支与正常分支都覆盖）。同时把 `killAll()` 里补 `if (flipSafety !== null) { window.clearTimeout(flipSafety); flipSafety = null }`。

- [ ] **Step 3: 验证构建**

Run（在 `frontend/`）: `npm run build`
Expected: 成功。

- [ ] **Step 4: 目视错误路径**

Run: `npm run dev`，触发一次失败（最简单：停掉后端 `backend` 进程后点"确认并生成行程"）。
Expected: loader 出现后短时间内因 fetch 失败而 `dismiss()` 撤场，露出发现页并弹 `message.error`；loader 不会永久卡屏。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/DiscoverView.vue frontend/src/components/loader/BauhausLoader.vue
git commit -m "feat(loader): 加超时看门狗与 Flip 安全兜底，防止 loader 卡屏"
```

---

## Task 9: 端到端验收与回归

**Files:** 无（仅验证）

- [ ] **Step 1: 全量测试**

Run（在 `frontend/`）: `npm run test`
Expected: useTripLoader 8 个测试全绿。

- [ ] **Step 2: 类型与构建**

Run: `npm run build`
Expected: vue-tsc + vite build 成功。

- [ ] **Step 3: 正常路径目视清单**

Run: `npm run dev`，完整走 Home → Discover → 选景点/分配 → 确认生成 → 草稿页。逐项确认：
- [ ] 点击生成后立即全屏海报，无延迟白屏
- [ ] 入场分幕动效完整（轴线/几何件/大数字/城市名）
- [ ] 状态条节点文案与百分比随后端推进（不倒退）
- [ ] 路由切到 `/draft/:id` 海报不消失、无 `a-spin`
- [ ] 第一天就绪后红块 Flip 贴合草稿 Hero，平滑无残影
- [ ] 草稿页正常可交互

- [ ] **Step 4: 降级与异常目视清单**
- [ ] reduced-motion 下静态海报 + 淡出收束
- [ ] 后端不可用时 loader graceful 撤场 + 错误提示
- [ ] 慢速网络（Chrome DevTools Slow 3G）下海报不闪烁、状态条持续有反馈

- [ ] **Step 5: 确认无回归**

Run: `grep -rn "PlanProgress" frontend/src/views/DiscoverView.vue`
Expected: 无输出（DiscoverView 已不再使用内联 PlanProgress）。
> `PlanProgress.vue` 组件文件本身保留（未来或其它视图可能复用），仅确认本次改动的视图已切换到全局 loader。

- [ ] **Step 6: 最终提交（若前序均已提交，可跳过）**

```bash
git status
# 如有未提交的验证期微调，统一提交
git commit -am "test(loader): Phase A 端到端验收微调"
```

---

## Phase A 完成后

向用户演示 CONSTRUCTION 海报与 Flip 过渡，收集反馈。确认后进入 **Phase B**：回到 `superpowers:brainstorming` 设计 Poster B（REFINEMENT）构图（见 spec §6），再走一轮 writing-plans 实现 `DraftView.onFinalize` → `Result.vue` 的 refinement loader 接入。

> Phase B 接入提示（供下轮参考）：`Result.vue` 当前 `import ResultHero` 但模板实际用的是**内联** `.result-hero` 红色块（`frontend/src/views/Result.vue:27-52`），Poster B 的 Flip 目标锚点应加在该内联 Hero 上，而非 ResultHero 组件。

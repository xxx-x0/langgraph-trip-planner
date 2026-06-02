# Poster B · REFINEMENT 加载页实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `DraftView`「定稿并保存」→ `Result.vue` SSE 合成（约 60 秒）这段过渡，替换为与 Poster A 同语言、叙事为「校样打磨 / FINAL PROOF」的全屏 Bauhaus 加载海报，复用现有 `useTripLoader` 状态机与 Flip 收束基础设施。

**Architecture:** 在已挂载的全局组件 `BauhausLoader.vue` 内，把 `state.poster === 'construction'` 之外的 `v-else` 占位替换为 REFINEMENT 海报 markup（四区：红横幅 / 日程台账 / 总体建议排版区 / 黑色状态条）。动效全部为**时间驱动的 CSS 循环**（不绑后端进度百分比），仅 Flip 收束沿用 GSAP。状态机与 `LoaderContext` 接口**不改**；`playEntrance` / `playFlipDismiss` 改为按 `state.poster` 分支。接入点：`DraftView.onFinalize` 前置 `begin('refinement', …)`，`Result.vue` 给 `.result-hero` 加 Flip 落点并在 SSE 事件里驱动 `updateProgress` / `markReady` / `dismiss`。

**Tech Stack:** Vue 3 `<script setup>` + TypeScript + Vite；GSAP（core + Flip + SplitText，已在 Phase A 注册）；Vitest 4 + happy-dom + `@vue/test-utils`（`npm run test`）；类型检查 `npm run build`（vue-tsc）。

**设计依据：** [docs/superpowers/specs/2026-06-02-poster-b-refinement-design.md](../specs/2026-06-02-poster-b-refinement-design.md)（已审批，分支 `feat/loading-bauhaus-phaseB`）。

---

## File Structure

| 文件 | 角色 | 改动 |
|---|---|---|
| `frontend/src/components/loader/cityRomanization.ts` | **新建**：城市中文名 → 罗马名映射，未命中返回 `null` | Task 1 |
| `frontend/src/components/loader/__tests__/cityRomanization.test.ts` | **新建**：`romanizeCity` 单测 | Task 1 |
| `frontend/src/components/loader/BauhausLoader.vue` | **修改**：替换 `v-else` 占位为 REFINEMENT markup + 新 ref/computed + 绿/橙/奶油作用域变量 + CSS 循环动画；`playEntrance`/`playFlipDismiss` 按 poster 分支 | Task 2 / Task 3 |
| `frontend/src/components/loader/__tests__/BauhausLoader.test.ts` | **新建**：REFINEMENT 渲染 / 天数自适应 / 状态条 / 英文副标题组件测试 | Task 2 |
| `frontend/src/views/DraftView.vue` | **修改**：`onFinalize` 前置 `tripLoader.begin('refinement', …)` | Task 4 |
| `frontend/src/views/Result.vue` | **修改**：`.result-hero` 加 `data-flip-id`；`startStreaming` 加 `updateProgress`/`markReady`/`dismiss`；import/实例化 `useTripLoader` | Task 5 |

**职责边界：** `cityRomanization.ts` 是纯函数模块，可独立单测；`BauhausLoader.vue` 内 construction 与 refinement 两套 markup 互斥（`v-if`/`v-else`，同一时刻只挂载一套），共享状态机与 Flip 收束逻辑但元素 ref 各自独立。

**测试策略说明（与 spec §11 一致）：** 单元测试覆盖 `cityRomanization`；组件测试覆盖 REFINEMENT 渲染 / 天数自适应 / 状态条文案 / 英文副标题。`DraftView.onFinalize`、`Result.vue` 的 SSE 接线与 `playEntrance`/`playFlipDismiss` 的 GSAP/Flip/matchMedia 分支**不做单元测试**——它们依赖路由、SSE 流、`html2canvas`/`jsPDF`、真实动画时序，在 happy-dom 中无法有意义地断言；这些由 `npm run build` 类型检查（Task 6）+ Chrome DevTools 端到端目视（Task 7）覆盖。这是有意识的取舍，非遗漏。

---

## Task 1: `cityRomanization.ts` 城市罗马名映射（纯函数 + 单测）

**Files:**
- Create: `frontend/src/components/loader/cityRomanization.ts`
- Test: `frontend/src/components/loader/__tests__/cityRomanization.test.ts`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/components/loader/__tests__/cityRomanization.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { romanizeCity } from '@/components/loader/cityRomanization'

describe('romanizeCity', () => {
  it('命中映射表返回大写罗马名', () => {
    expect(romanizeCity('北京')).toBe('BEIJING')
    expect(romanizeCity('上海')).toBe('SHANGHAI')
    expect(romanizeCity('香港')).toBe('HONG KONG')
  })

  it('未命中的中文返回 null（避免重复出中文）', () => {
    expect(romanizeCity('景德镇')).toBeNull()
  })

  it('空串返回 null', () => {
    expect(romanizeCity('')).toBeNull()
  })

  it('纯拉丁字符城市名直接大写', () => {
    expect(romanizeCity('paris')).toBe('PARIS')
    expect(romanizeCity('Tokyo')).toBe('TOKYO')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/loader/__tests__/cityRomanization.test.ts`
Expected: FAIL —— `Failed to resolve import '@/components/loader/cityRomanization'`（模块尚不存在）。

- [ ] **Step 3: 写最小实现**

创建 `frontend/src/components/loader/cityRomanization.ts`：

```ts
/** 城市中文名 → 罗马名（大写）。未命中返回 null，调用方据此省略英文副标题。 */
const MAP: Record<string, string> = {
  北京: 'BEIJING', 上海: 'SHANGHAI', 广州: 'GUANGZHOU', 深圳: 'SHENZHEN',
  成都: 'CHENGDU', 杭州: 'HANGZHOU', 西安: 'XIAN', 重庆: 'CHONGQING',
  南京: 'NANJING', 苏州: 'SUZHOU', 厦门: 'XIAMEN', 三亚: 'SANYA',
  丽江: 'LIJIANG', 桂林: 'GUILIN', 青岛: 'QINGDAO', 武汉: 'WUHAN',
  长沙: 'CHANGSHA', 昆明: 'KUNMING', 大理: 'DALI', 香港: 'HONG KONG',
  // …可按实际服务城市增补
}

export function romanizeCity(city: string): string | null {
  if (!city) return null
  return MAP[city] ?? (/^[\x00-\x7F]+$/.test(city) ? city.toUpperCase() : null)
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/components/loader/__tests__/cityRomanization.test.ts`
Expected: PASS（4 个用例全绿）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/loader/cityRomanization.ts frontend/src/components/loader/__tests__/cityRomanization.test.ts
git commit -m "feat(loader): cityRomanization 城市中文名→罗马名映射（TDD）"
```

---

## Task 2: REFINEMENT 海报 markup + script 增补 + 样式（组件测试驱动）

**Files:**
- Modify: `frontend/src/components/loader/BauhausLoader.vue`
- Test: `frontend/src/components/loader/__tests__/BauhausLoader.test.ts`

> 本任务只新增 refinement 的 markup / computed / ref / 样式；`playEntrance`、`playFlipDismiss` 的分支留到 Task 3。组件渲染测试**不推进 phase**（不调用 `setSteady`/`markReady`），因此不触发 GSAP 入场/收束，Task 2 测试不依赖 Task 3。

- [ ] **Step 1: 写失败的组件测试**

创建 `frontend/src/components/loader/__tests__/BauhausLoader.test.ts`：

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// 渲染测试不触发 GSAP 入场/收束；mock 插件避免 happy-dom 下的副作用。
vi.mock('gsap/Flip', () => ({ Flip: { fit: () => {} } }))
vi.mock('gsap/SplitText', () => ({ SplitText: { create: () => ({ chars: [], revert() {} }) } }))

import BauhausLoader from '@/components/loader/BauhausLoader.vue'
import { useTripLoader } from '@/composables/useTripLoader'

function ctx(over: Record<string, unknown> = {}) {
  return { city: '北京', days: 5, attractionCount: 12, metaLine: '2026-06-10 – 2026-06-14', ...over }
}

describe('BauhausLoader · REFINEMENT', () => {
  beforeEach(() => useTripLoader().reset())

  it('idle 时不渲染海报', () => {
    const w = mount(BauhausLoader)
    expect(w.find('.bh-loader').exists()).toBe(false)
    w.unmount()
  })

  it('refinement begin 后渲染四区，且不渲染 construction 海报', async () => {
    useTripLoader().begin('refinement', ctx())
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.find('.bh-poster--refine').exists()).toBe(true)
    expect(w.find('.pb-banner').exists()).toBe(true)
    expect(w.find('.pb-ledger').exists()).toBe(true)
    expect(w.find('.pb-spread').exists()).toBe(true)
    expect(w.find('.pb-status').exists()).toBe(true)
    expect(w.find('.bh-hero').exists()).toBe(false)
    w.unmount()
  })

  it('台账按真实天数渲染（N=3，无折叠）', async () => {
    useTripLoader().begin('refinement', ctx({ days: 3 }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.findAll('.pb-dayrow')).toHaveLength(3)
    expect(w.find('.pb-dayrow--fold').exists()).toBe(false)
    w.unmount()
  })

  it('N=7 渲染 7 行无折叠', async () => {
    useTripLoader().begin('refinement', ctx({ days: 7 }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.findAll('.pb-dayrow')).toHaveLength(7)
    expect(w.find('.pb-dayrow--fold').exists()).toBe(false)
    w.unmount()
  })

  it('N=12 渲染前 8 行 + 折叠行 +4', async () => {
    useTripLoader().begin('refinement', ctx({ days: 12 }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.findAll('.pb-dayrow')).toHaveLength(9) // 8 行 + 1 折叠行
    const fold = w.find('.pb-dayrow--fold')
    expect(fold.exists()).toBe(true)
    expect(fold.text()).toContain('+4')
    w.unmount()
  })

  it('状态条随 currentMessage 变化；缺省回退 定稿中…', async () => {
    useTripLoader().begin('refinement', ctx())
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.find('.pb-status-lbl').text()).toContain('定稿中')
    useTripLoader().updateProgress('synthesizer', '生成总体建议…', 0)
    await w.vm.$nextTick()
    expect(w.find('.pb-status-lbl').text()).toContain('生成总体建议')
    w.unmount()
  })

  it('城市命中映射显示英文副标题；未命中省略', async () => {
    useTripLoader().begin('refinement', ctx({ city: '北京' }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.find('.pb-banner-en').exists()).toBe(true)
    expect(w.find('.pb-banner-en').text()).toContain('BEIJING')
    w.unmount()

    useTripLoader().reset()
    useTripLoader().begin('refinement', ctx({ city: '景德镇' }))
    const w2 = mount(BauhausLoader)
    await w2.vm.$nextTick()
    expect(w2.find('.pb-banner-en').exists()).toBe(false)
    w2.unmount()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/loader/__tests__/BauhausLoader.test.ts`
Expected: FAIL —— `.bh-poster--refine` / `.pb-banner` 等找不到（当前 `v-else` 仅是空占位 `bh-poster--placeholder`）。

- [ ] **Step 3: 增补 script —— import romanizeCity**

`frontend/src/components/loader/BauhausLoader.vue` 第 53 行下方（紧接 `constructionSteps` 那行 import）新增：

```ts
import { romanizeCity } from './cityRomanization'
```

- [ ] **Step 4: 增补 script —— refinement 元素 ref**

在 `const statusRef = ref<HTMLElement | null>(null)`（第 66 行）下方新增 refinement 专用 ref：

```ts
// refinement 专用 ref（Flip 源 + 收束前淡出的装饰组）
const bannerRef = ref<HTMLElement | null>(null)   // 顶部红横幅 = Flip 源
const ledgerRef = ref<HTMLElement | null>(null)
const spreadRef = ref<HTMLElement | null>(null)
const statusRefB = ref<HTMLElement | null>(null)
const geoRef = ref<HTMLElement | null>(null)
```

- [ ] **Step 5: 增补 script —— refinement computed / 常量 / 工具**

在 `stepIndexLabel` computed（第 81-85 行）下方、`// ===== GSAP 动画句柄与清理 =====` 注释之前新增：

```ts
// ===== REFINEMENT 海报数据 =====
const REFINE_CYCLE = 5      // 绿勾点亮循环周期（秒），与 pbCheck/pbTick 一致
const MAX_LEDGER_ROWS = 8   // 台账最多渲染行数，超出折叠

// refinement 英文副标题：命中映射显示，未命中（中文）返回 null → 模板省略英文行
const cityEnRefine = computed(() => romanizeCity(ctx.value.city))

// 状态条文案：绑定后端真实 SSE step 文案，缺省回退「定稿中…」
const statusTextRefine = computed(() => state.currentMessage || '定稿中…')

const dayCount = computed(() => Math.max(0, ctx.value.days || 0))
const shownDayCount = computed(() => Math.min(dayCount.value, MAX_LEDGER_ROWS))
// 渲染的台账行号 [1..shownDayCount]
const ledgerRows = computed(() =>
  Array.from({ length: shownDayCount.value }, (_, i) => i + 1),
)
// N>8 时折叠的剩余天数（用于「…+N」行）；N<=8 时为 0
const foldedCount = computed(() => Math.max(0, dayCount.value - MAX_LEDGER_ROWS))

// 绿勾逐行点亮的 animation-delay（按行号在一个循环周期内等分）
function rowDelay(i: number): string {
  const n = shownDayCount.value || 1
  return `${((i / n) * REFINE_CYCLE).toFixed(2)}s`
}
```

- [ ] **Step 6: 替换 `v-else` 占位为 REFINEMENT markup**

把 `frontend/src/components/loader/BauhausLoader.vue` 第 42-43 行：

```html
    <!-- REFINEMENT 海报：Phase B 实现，暂留占位 -->
    <div v-else class="bh-poster bh-poster--placeholder"></div>
```

替换为：

```html
    <!-- REFINEMENT 海报：定稿打磨 / FINAL PROOF -->
    <div v-else ref="posterRef" class="bh-poster bh-poster--refine">
      <!-- ① 顶部红横幅（Flip 源） -->
      <div ref="bannerRef" class="pb-banner" data-flip-source="loader-hero">
        <span class="pb-banner-cn">{{ ctx.city }}</span>
        <span v-if="cityEnRefine" class="pb-banner-en">{{ cityEnRefine }} · {{ ctx.days }}日</span>
        <span class="pb-banner-badge">FINAL PROOF</span>
        <div class="pb-crop tl"></div>
        <div class="pb-crop tr"></div>
      </div>

      <!-- ② 左栏 日程校样台账 -->
      <div ref="ledgerRef" class="pb-ledger">
        <div class="pb-ledger-hd">DAYS · 日程校样</div>
        <div
          v-for="(num, i) in ledgerRows"
          :key="num"
          class="pb-dayrow"
          :style="{ '--d': rowDelay(i) }"
        >
          <span class="pb-dayrow-num">{{ String(num).padStart(2, '0') }}</span>
          <span class="pb-dayrow-ln"></span>
          <span class="pb-dayrow-chk"></span>
        </div>
        <div v-if="foldedCount > 0" class="pb-dayrow pb-dayrow--fold">
          <span class="pb-dayrow-num">…</span>
          <span class="pb-fold-label">+{{ foldedCount }}</span>
        </div>
      </div>

      <!-- 几何三件（Poster A 几何件的「归位」回响） -->
      <div ref="geoRef" class="pb-geo">
        <span class="pb-geo-tri"></span>
        <span class="pb-geo-cir"></span>
        <span class="pb-geo-sq"></span>
      </div>

      <!-- ③ 右栏 总体建议排版区 -->
      <div ref="spreadRef" class="pb-spread">
        <div class="pb-spread-hd">
          <span class="pb-spread-t">OVERVIEW · 总体建议</span>
          <span class="pb-mark">✳</span>
        </div>
        <div class="pb-lines">
          <div v-for="n in 6" :key="n" class="pb-line">
            <span class="pb-line-cap"></span>
            <span class="pb-line-bar"></span>
          </div>
        </div>
        <div class="pb-stamp">定稿中<small>FINALIZING</small></div>
        <div class="pb-sweep"></div>
      </div>

      <!-- ④ 底部黑色状态条 -->
      <div ref="statusRefB" class="pb-status">
        <span class="pb-status-lbl">▶ {{ statusTextRefine }}</span>
        <span class="pb-barber"></span>
      </div>
    </div>
```

- [ ] **Step 7: 增补绿/橙/奶油作用域变量**

在 `<style scoped>` 的 `.bh-loader { … }` 规则（第 233-242 行）内，`overflow: hidden;` 之后、`}` 之前新增三个组件作用域 CSS 变量（绿/橙/奶油仅 Poster B 用，不污染全局 token）：

```css
  /* Poster B 扩展色：绿（精修/通过）、橙（旋转校样标）、奶油（排版区底） */
  --bh-green: #0E9F6E;
  --bh-orange: #E8772E;
  --bh-cream: #f1ece0;
```

- [ ] **Step 8: 追加 REFINEMENT 样式**

在 `<style scoped>` 末尾、`@media (max-width: 640px) { … }` 块之后、`</style>` 之前，追加以下完整样式块。静态布局（位置/颜色/边框）在媒体查询之外 → reduce 用户看到**静止**的完整海报；所有循环/入场动画包在 `@media (prefers-reduced-motion: no-preference)` 内：

```css
/* ===== REFINEMENT (Poster B) ===== */
.bh-poster--refine { background: #faf8f3; }

/* ① 顶部红横幅（Flip 源） */
.pb-banner {
  position: absolute; top: 0; left: 0; right: 0; height: 17%;
  background: var(--primary-red); border-bottom: 4px solid var(--foreground);
  color: #fff; display: flex; align-items: center; gap: 18px; padding: 0 5vw; z-index: 6;
}
.pb-banner-cn { font-size: clamp(28px, 4vw, 56px); font-weight: 900; line-height: 1; letter-spacing: -0.02em; }
.pb-banner-en { font-size: clamp(11px, 1vw, 15px); letter-spacing: 0.4em; opacity: 0.92; }
.pb-banner-badge {
  margin-left: auto; font-size: clamp(10px, 0.9vw, 13px); font-weight: 800; letter-spacing: 0.18em;
  border: 2px solid #fff; padding: 4px 12px;
}
.pb-crop { position: absolute; width: 16px; height: 16px; z-index: 7; }
.pb-crop::before, .pb-crop::after { content: ''; position: absolute; background: var(--foreground); }
.pb-crop::before { width: 16px; height: 2px; top: 7px; }
.pb-crop::after { width: 2px; height: 16px; left: 7px; }
.pb-crop.tl { top: 4px; left: 4px; }
.pb-crop.tr { top: 4px; right: 4px; }

/* ② 左栏 日程校样台账 */
.pb-ledger {
  position: absolute; left: 0; top: 17%; width: 37%; bottom: 12%;
  border-right: 3px solid var(--foreground); padding: 2vh 2vw 0; box-sizing: border-box; overflow: hidden;
}
.pb-ledger-hd {
  font-size: clamp(10px, 1vw, 14px); font-weight: 800; letter-spacing: 0.2em; color: var(--foreground);
  border-bottom: 2px solid var(--foreground); padding-bottom: 8px; margin-bottom: 2vh;
}
.pb-dayrow { display: flex; align-items: center; gap: 12px; margin-bottom: clamp(6px, 1.6vh, 16px); }
.pb-dayrow-num { font-size: clamp(14px, 1.7vw, 22px); font-weight: 900; width: 34px; color: var(--foreground); }
.pb-dayrow-ln { flex: 1; height: 8px; background: rgba(18, 18, 18, .12); }
.pb-dayrow-chk {
  position: relative; width: 20px; height: 20px; border: 2px solid var(--foreground); background: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 13px; color: #fff; font-weight: 900; flex: 0 0 auto;
}
.pb-dayrow-chk::after { content: '✓'; position: absolute; opacity: 0; }
.pb-dayrow--fold .pb-dayrow-num { width: auto; }
.pb-fold-label { font-size: clamp(12px, 1.3vw, 16px); font-weight: 800; letter-spacing: 0.1em; color: var(--foreground); opacity: 0.7; }

/* 几何三件 */
.pb-geo { position: absolute; left: 2vw; bottom: 13.5%; display: flex; align-items: flex-end; gap: 14px; z-index: 4; }
.pb-geo-tri {
  width: 0; height: 0; border-left: 15px solid transparent; border-right: 15px solid transparent;
  border-bottom: 26px solid var(--primary-blue); filter: drop-shadow(2px 2px 0 var(--foreground));
}
.pb-geo-cir { width: 26px; height: 26px; border-radius: 50%; background: var(--bh-green); border: 2px solid var(--foreground); box-shadow: 2px 2px 0 var(--foreground); }
.pb-geo-sq { width: 24px; height: 24px; background: var(--primary-yellow); border: 2px solid var(--foreground); box-shadow: 2px 2px 0 var(--foreground); }

/* ③ 右栏 总体建议排版区 */
.pb-spread { position: absolute; left: 37%; right: 0; top: 17%; bottom: 12%; background: var(--bh-cream); overflow: hidden; }
.pb-spread-hd { display: flex; align-items: center; justify-content: space-between; padding: 2vh 2vw 1vh; }
.pb-spread-t { font-size: clamp(10px, 1vw, 14px); font-weight: 800; letter-spacing: 0.2em; color: var(--foreground); }
.pb-mark { width: 28px; height: 28px; color: var(--bh-orange); font-size: 28px; line-height: 28px; text-align: center; font-weight: 900; }
.pb-lines { padding: 1vh 2vw; }
.pb-line { height: 11px; margin-bottom: clamp(6px, 1.6vh, 14px); display: flex; align-items: center; gap: 10px; }
.pb-line-cap { width: 16px; height: 11px; flex: 0 0 auto; }
.pb-line-bar { height: 9px; background: rgba(18, 18, 18, .16); }
.pb-line:nth-child(1) .pb-line-cap { background: var(--foreground); } .pb-line:nth-child(1) .pb-line-bar { width: 88%; }
.pb-line:nth-child(2) .pb-line-cap { background: var(--primary-blue); } .pb-line:nth-child(2) .pb-line-bar { width: 70%; }
.pb-line:nth-child(3) .pb-line-cap { background: var(--bh-green); } .pb-line:nth-child(3) .pb-line-bar { width: 80%; }
.pb-line:nth-child(4) .pb-line-cap { background: var(--primary-yellow); } .pb-line:nth-child(4) .pb-line-bar { width: 62%; }
.pb-line:nth-child(5) .pb-line-cap { background: var(--foreground); } .pb-line:nth-child(5) .pb-line-bar { width: 76%; }
.pb-line:nth-child(6) .pb-line-cap { background: var(--primary-blue); } .pb-line:nth-child(6) .pb-line-bar { width: 54%; }
.pb-sweep {
  position: absolute; top: 0; bottom: 0; width: 42%; left: -55%;
  background: linear-gradient(100deg, transparent, rgba(255, 255, 255, .9) 46%, rgba(14, 159, 110, .35) 56%, transparent);
  transform: skewX(-12deg); pointer-events: none; z-index: 3;
}
.pb-stamp {
  position: absolute; right: 8%; bottom: 16%; transform: rotate(-9deg);
  border: 3px solid var(--bh-green); color: var(--bh-green); padding: 6px 14px;
  font-size: clamp(13px, 1.4vw, 18px); font-weight: 900; letter-spacing: 0.12em; opacity: 0.85; z-index: 4;
}
.pb-stamp small { display: block; font-size: 0.6em; letter-spacing: 0.3em; text-align: center; }

/* ④ 底部黑色状态条 */
.pb-status {
  position: absolute; left: 0; right: 0; bottom: 0; height: 12%; background: var(--foreground); color: #fff;
  display: flex; align-items: center; padding: 0 5vw; gap: 18px; z-index: 6;
}
.pb-status-lbl { font-size: clamp(12px, 1.2vw, 16px); font-weight: 700; letter-spacing: 0.12em; white-space: nowrap; }
.pb-barber {
  flex: 1; height: 10px;
  background: repeating-linear-gradient(45deg, var(--primary-yellow) 0 9px, transparent 9px 18px);
  background-size: 25px 100%; opacity: 0.85;
}

/* 循环 / 入场动画：仅在允许动效时启用（reduce 用户看到静止海报） */
@media (prefers-reduced-motion: no-preference) {
  .pb-banner { animation: pbBannerIn 0.7s cubic-bezier(.16, 1, .3, 1) both; }
  .pb-dayrow-chk { animation: pbCheck 5s infinite; animation-delay: var(--d, 0s); }
  .pb-dayrow-chk::after { animation: pbTick 5s infinite; animation-delay: var(--d, 0s); }
  .pb-mark { animation: pbSpin 6s linear infinite; }
  .pb-sweep { animation: pbSweep 2.4s infinite linear; }
  .pb-stamp { animation: pbStamp 5s infinite; }
  .pb-barber { animation: pbBarber 0.7s infinite linear; }
}

@keyframes pbBannerIn { from { transform: translateY(-100%); } to { transform: translateY(0); } }
@keyframes pbCheck { 0%, 8% { background: #fff; } 14%, 84% { background: var(--bh-green); } 90%, 100% { background: #fff; } }
@keyframes pbTick { 0%, 10% { opacity: 0; } 16%, 84% { opacity: 1; } 90%, 100% { opacity: 0; } }
@keyframes pbSpin { to { transform: rotate(360deg); } }
@keyframes pbSweep { 0% { left: -55%; } 100% { left: 115%; } }
@keyframes pbStamp { 0%, 100% { transform: rotate(-9deg) scale(1); } 50% { transform: rotate(-9deg) scale(1.05); } }
@keyframes pbBarber { from { background-position: 0 0; } to { background-position: 25px 0; } }
```

- [ ] **Step 9: 运行组件测试确认通过**

Run: `cd frontend && npx vitest run src/components/loader/__tests__/BauhausLoader.test.ts`
Expected: PASS（7 个用例全绿）。

- [ ] **Step 10: 提交**

```bash
git add frontend/src/components/loader/BauhausLoader.vue frontend/src/components/loader/__tests__/BauhausLoader.test.ts
git commit -m "feat(loader): Poster B · REFINEMENT 海报 markup + 天数自适应台账 + 时间驱动 CSS 循环"
```

---

## Task 3: `playEntrance` / `playFlipDismiss` 按 poster 分支

**Files:**
- Modify: `frontend/src/components/loader/BauhausLoader.vue`

> 本任务改动 GSAP 入场 / Flip 收束接线，使其按 `state.poster` 选择正确的元素。construction 行为保持不变。由 `npm run build`（Task 6）类型检查 + Task 2 组件测试仍全绿 + Task 7 端到端目视验证（spec §11 把动画分支归入端到端，不做 happy-dom 单测）。

- [ ] **Step 1: 把 `playEntrance` 改名为 `playEntranceConstruction` 并新增 `playEntranceRefinement`**

把第 113 行的函数签名：

```ts
function playEntrance() {
```

改名为：

```ts
function playEntranceConstruction() {
```

函数体保持不变（killAll / matchMedia / 三幕 timeline / reduce 分支均不动）。然后在该函数 `}` 结束后、`function startSteady()` 之前，新增 refinement 入场函数：

```ts
// REFINEMENT 入场为纯 CSS（pbBannerIn 等 keyframes），GSAP 不参与；
// 这里只把状态机从 entering 推进到 steady。reduce 与 no-preference 共用本路径，
// 动/静差异完全由 CSS @media 决定。
function playEntranceRefinement() {
  setSteady()
}
```

- [ ] **Step 2: 让 phase watcher 按 poster 选入场函数**

把第 218-229 行的 watcher：

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

替换为：

```ts
watch(
  () => state.phase,
  async (phase, prev) => {
    if (phase === 'entering' && prev === 'idle') {
      await nextTick()
      if (state.poster === 'refinement') playEntranceRefinement()
      else playEntranceConstruction()
    } else if (phase === 'flipping') {
      await nextTick()
      playFlipDismiss()
    }
  },
)
```

- [ ] **Step 3: 让 `playFlipDismiss` 按 poster 选 Flip 源与装饰组**

把第 171-215 行的整个 `playFlipDismiss` 函数：

```ts
async function playFlipDismiss() {
  // 安全兜底：进入收束后若 2.5s 仍未完成（如目标锚点意外缺失），强制复位。
  // 正常链路 ≈ 装饰淡出(~0.54s)+Flip(0.7s)+淡出(0.2s)≈1.44s，2.5s 留足余量不误杀。
  flipSafety = window.setTimeout(doFinish, 2500)

  const dest = document.querySelector<HTMLElement>('[data-flip-id="loader-hero"]')

  // 找不到目标（异常）：直接结束
  if (!dest || !heroRef.value) {
    doFinish()
    return
  }

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (reduce) {
    // 降级：整屏淡出，不做位置变形
    gsap.to('.bh-loader', { opacity: 0, duration: 0.2, onComplete: doFinish })
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
        onComplete: doFinish,
      })
    },
  })
}
```

替换为（仅把「Flip 源」与「装饰组」按 poster 选择，其余逻辑复用）：

```ts
async function playFlipDismiss() {
  // 安全兜底：进入收束后若 2.5s 仍未完成（如目标锚点意外缺失），强制复位。
  // 正常链路 ≈ 装饰淡出(~0.54s)+Flip(0.7s)+淡出(0.2s)≈1.44s，2.5s 留足余量不误杀。
  flipSafety = window.setTimeout(doFinish, 2500)

  // 按海报选择 Flip 源（顶部红块）与收束前先淡出的装饰组
  const isRefine = state.poster === 'refinement'
  const src = isRefine ? bannerRef.value : heroRef.value
  const decor = (isRefine
    ? [ledgerRef.value, spreadRef.value, statusRefB.value, geoRef.value]
    : [axisRef.value, circleRef.value, cornerRef.value, megaRef.value, triangleRef.value, squareRef.value, statusRef.value]
  ).filter(Boolean)

  const dest = document.querySelector<HTMLElement>('[data-flip-id="loader-hero"]')

  // 找不到目标或源（异常）：直接结束
  if (!dest || !src) {
    doFinish()
    return
  }

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (reduce) {
    // 降级：整屏淡出，不做位置变形
    gsap.to('.bh-loader', { opacity: 0, duration: 0.2, onComplete: doFinish })
    return
  }

  steadyTl?.kill(); steadyTl = null

  // 装饰元素先飞散/淡出
  await gsap.to(decor, { opacity: 0, scale: 0.9, duration: 0.3, stagger: 0.04, ease: 'power2.in' })

  // 让 loader 背景透出底层页面
  gsap.to('.bh-loader', { backgroundColor: 'rgba(250,248,243,0)', duration: 0.4 })

  // 把 loader 红块吸附到目标页锚点（FLIP fit）
  Flip.fit(src, dest, {
    duration: 0.7,
    ease: 'power3.inOut',
    absolute: true,
    scale: true,
    onComplete: () => {
      gsap.to(src, {
        opacity: 0,
        duration: 0.2,
        onComplete: doFinish,
      })
    },
  })
}
```

- [ ] **Step 4: 类型检查 + 既有测试回归**

Run: `cd frontend && npx vue-tsc --noEmit && npx vitest run src/components/loader/__tests__/`
Expected: 类型检查无错误；`cityRomanization` + `BauhausLoader` 组件测试仍全绿（分支改动不触及渲染断言）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/loader/BauhausLoader.vue
git commit -m "feat(loader): playEntrance/playFlipDismiss 按 poster 分支，复用 Flip 收束驱动 Poster B"
```

---

## Task 4: `DraftView.onFinalize` 前置 `begin('refinement', …)`

**Files:**
- Modify: `frontend/src/views/DraftView.vue:128-133`

> `attractionCount` 取「各天 `attractions` 数之和」，与 Poster A（`selected.length`，发现页勾选的唯一景点数）口径一致——每个勾选景点在规划后落到唯一一天，故按天求和等于唯一景点总数。`draft.value` 为 `getDraft` 返回的 `TripDraftPayload`：`days[i]` 是 `DraftDayContext`（含 `attractions: Attraction[]`），骨架阶段即存在；`request.travel_days` / `request.start_date` / `request.end_date` / `city` 均可用。`tripLoader` 已在第 58 行实例化。

- [ ] **Step 1: 改写 `onFinalize`**

把第 128-133 行：

```ts
async function onFinalize() {
  router.push({
    path: '/result',
    query: { streaming: 'true', draft_id: draftId.value },
  })
}
```

替换为：

```ts
async function onFinalize() {
  // 前置拉起全局 Bauhaus 加载海报（REFINEMENT / 定稿打磨）
  const d = draft.value
  if (d) {
    tripLoader.begin('refinement', {
      city: d.city,
      days: d.request.travel_days,
      // 各天景点数之和，与 Poster A（selected.length）口径一致
      attractionCount: (d.days ?? []).reduce(
        (sum: number, day: any) => sum + (day.attractions?.length ?? 0),
        0,
      ),
      metaLine:
        d.request.start_date && d.request.end_date
          ? `${d.request.start_date} – ${d.request.end_date}`
          : undefined,
    })
  }
  router.push({
    path: '/result',
    query: { streaming: 'true', draft_id: draftId.value },
  })
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无类型错误（`draft` 为 `ref<any>`，字段访问不报错；`begin` 接受 `LoaderContext`）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/DraftView.vue
git commit -m "feat(draft): onFinalize 前置 begin('refinement') 拉起 Poster B 加载海报"
```

---

## Task 5: `Result.vue` 接线（Flip 落点 + SSE 驱动状态机）

**Files:**
- Modify: `frontend/src/views/Result.vue`（第 28 行 `.result-hero`；第 144-159 行 import/实例化；第 236-261 行 `startStreaming`）

> `markReady()` 必须在 `tripPlan` 填充、`router.replace('/trip/:id')` 之后、且 `await nextTick()` 之后调用——`.result-hero` 是 `v-if="tripPlan"`，此时才在 DOM 中，Flip 才找得到落点（`/result` 与 `/trip/:id` 复用同一 Result 组件实例，`tripPlan` 不丢）。
>
> **重试路径（spec §9.3）：** `error`/`catch` 已 `dismiss()` 回 idle。`onRetry → startStreaming` 再次进入时，`updateProgress` 在 idle 下只改 message（海报 `v-if` 不渲染，无副作用），`markReady` 从 idle 是 no-op（状态机仅在 entering/steady 生效）——因此重试**不会**重新拉起 Bauhaus 海报，回退到现有 `result-skeleton`，符合设计。无需额外代码。

- [ ] **Step 1: import 并实例化 `useTripLoader`**

第 151 行 `import { saveTripToHistory, getTripDetail, finalizeDraftStream } from '@/services/api'` 下方新增：

```ts
import { useTripLoader } from '@/composables/useTripLoader'
```

第 159 行 `const route = useRoute()` 下方新增：

```ts
const tripLoader = useTripLoader()
```

（`nextTick` 已在第 145 行从 `'vue'` 导入，无需改动。）

- [ ] **Step 2: 给 `.result-hero` 加 Flip 落点**

把第 28 行：

```html
    <div v-if="tripPlan" class="result-hero">
```

替换为：

```html
    <div v-if="tripPlan" class="result-hero" data-flip-id="loader-hero">
```

- [ ] **Step 3: `progress` 分支驱动底部状态条真实文案**

把第 239-242 行：

```ts
      if (event.type === 'progress') {
        progressCount++
        if (progressCount === 1) skeletonStage.value = 'hero'
        else if (progressCount === 2) skeletonStage.value = 'itinerary'
      } else if (event.type === 'complete') {
```

替换为：

```ts
      if (event.type === 'progress') {
        progressCount++
        if (progressCount === 1) skeletonStage.value = 'hero'
        else if (progressCount === 2) skeletonStage.value = 'itinerary'
        // 驱动 Poster B 底部状态条真实 SSE 文案（progress=0：不确定态，不显示百分比）
        tripLoader.updateProgress(event.step, event.message, 0)
      } else if (event.type === 'complete') {
```

- [ ] **Step 4: `complete` 分支在落点就绪后触发 Flip 收束**

把第 243-256 行：

```ts
      } else if (event.type === 'complete') {
        tripPlan.value = event.trip_plan
        skeletonStage.value = 'done'
        // 把 URL 改成 /trip/:id 以便后续分享和刷新；但 tripPlan 已填充，无需重新加载
        if (event.trip_id) {
          await router.replace({ path: `/trip/${event.trip_id}` })
        }
        if (tripPlan.value) {
          await loadAttractionPhotos()
        }
      } else if (event.type === 'error') {
        streamError.value = event.message || '生成失败'
        skeletonStage.value = 'error'
      }
```

替换为：

```ts
      } else if (event.type === 'complete') {
        tripPlan.value = event.trip_plan
        skeletonStage.value = 'done'
        // 把 URL 改成 /trip/:id 以便后续分享和刷新；但 tripPlan 已填充，无需重新加载
        if (event.trip_id) {
          await router.replace({ path: `/trip/${event.trip_id}` })
        }
        if (tripPlan.value) {
          await loadAttractionPhotos()
        }
        // tripPlan 已填充且路由已切换：.result-hero 此刻才在 DOM 中，
        // 等下一帧 DOM 落定后再 markReady()，Flip 才找得到 [data-flip-id="loader-hero"] 落点
        await nextTick()
        tripLoader.markReady()
      } else if (event.type === 'error') {
        streamError.value = event.message || '生成失败'
        skeletonStage.value = 'error'
        tripLoader.dismiss() // 直接撤场，露出 error skeleton + 重试按钮
      }
```

- [ ] **Step 5: `catch` 分支也撤场**

把第 258-261 行：

```ts
  } catch (e: any) {
    streamError.value = e?.message || '连接失败'
    skeletonStage.value = 'error'
  }
```

替换为：

```ts
  } catch (e: any) {
    streamError.value = e?.message || '连接失败'
    skeletonStage.value = 'error'
    tripLoader.dismiss() // 含 finalizeDraftStream 180s fetch 超时：撤场露出 error skeleton
  }
```

- [ ] **Step 6: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/Result.vue
git commit -m "feat(result): .result-hero 加 Flip 落点；SSE 事件驱动 Poster B markReady/dismiss/状态文案"
```

---

## Task 6: 全量测试 + 构建（类型检查）绿灯

**Files:** 无（验证任务）

- [ ] **Step 1: 跑全部前端单元/组件测试**

Run: `cd frontend && npm run test`
Expected: PASS —— `useTripLoader`（Phase A 既有）、`cityRomanization`（Task 1）、`BauhausLoader`（Task 2）全绿。

- [ ] **Step 2: 类型检查 + 生产构建**

Run: `cd frontend && npm run build`
Expected: `vue-tsc` 无类型错误，Vite 构建成功输出 `dist/`。

- [ ] **Step 3: 若有失败，停下修复，不要带病前进**

若 Step 1/2 失败：定位到具体任务回改，重跑该任务的验证步骤，再回到本任务。修复后再次 `npm run test && npm run build` 直至全绿。

---

## Task 7: 端到端目视验证（Chrome DevTools MCP）

**Files:** 无（手动 / agentic 验证；参见 memory `driving-bauhaus-loader-in-browser`）

> 前置：`cd frontend && npm run dev`（:5173）。用「HMR 版本化 URL」手法导入已挂载的 `useTripLoader` 单例实例来驱动海报，避免跑昂贵的 LLM 流程。每步用 `take_screenshot` 留证。

- [ ] **Step 1: 进入应用并取到受控的 loader 单例**

`navigate_page` 到 `http://localhost:5173/`，然后 `evaluate_script`：

```js
const url = performance.getEntriesByType('resource').map(e => e.name)
  .filter(n => n.includes('/composables/useTripLoader.ts')).pop();
const loader = (await import(/* @vite-ignore */ url)).useTripLoader();
window.__loader = loader; // 暂存供后续步骤复用
loader.begin('refinement', { city: '北京', days: 5, attractionCount: 12, metaLine: '2026-06-10 – 2026-06-14' });
return loader.state.phase; // 期望 'entering'
```

`take_screenshot`。期望：全屏 REFINEMENT 海报——红横幅落下、左栏 01–05 台账绿勾逐日点亮、右栏奶油排版区高光斜扫 + ✳ 慢转 + 「定稿中」印章呼吸、底部黑条 barber-pole 滚动。

- [ ] **Step 2: 天数自适应 N=12 折叠**

`evaluate_script`：

```js
window.__loader.reset();
window.__loader.begin('refinement', { city: '上海', days: 12, attractionCount: 30, metaLine: '2026-07-01 – 2026-07-12' });
return document.querySelectorAll('.pb-dayrow').length; // 期望 9（前 8 行 + 折叠行）
```

`take_screenshot`。期望：台账显示 01–08 + 末行「…+4」，纵向不溢出。

- [ ] **Step 3: 真实文案随 updateProgress 切换**

`evaluate_script`：

```js
window.__loader.updateProgress('synthesizer', '生成总体建议…', 0);
return document.querySelector('.pb-status-lbl').textContent; // 期望含「生成总体建议」
```

期望：底部状态条显示「▶ 生成总体建议…」，barber-pole 仍滚动，无百分比数字。

- [ ] **Step 4: Flip 收束（注入临时落点锚点）**

当前页无 `[data-flip-id="loader-hero"]`，先注入临时锚点再 `markReady()`：

```js
const a = document.createElement('div');
a.setAttribute('data-flip-id', 'loader-hero');
a.style.cssText = 'position:fixed;top:0;left:0;right:0;height:80px;background:#D02020;z-index:1;';
document.body.appendChild(a);
window.__loader.markReady();
return window.__loader.state.phase; // 期望 'flipping'
```

约 1.5s 后 `take_screenshot`。期望：装饰组先淡出，红横幅 `Flip.fit` 平滑变形到顶部锚点条，随后整体淡出，海报消失（`phase` 回到 `idle`）。

- [ ] **Step 5: reduced-motion 静态海报**

`navigate_page` 时用 `initScript` 覆盖 `window.matchMedia`（CDP 无 prefers-reduced-motion 开关）使 `prefers-reduced-motion: reduce` 命中：

```js
const mq = window.matchMedia.bind(window);
window.matchMedia = (q) => q.includes('prefers-reduced-motion: reduce')
  ? { matches: true, media: q, addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){}, onchange: null, dispatchEvent(){return false;} }
  : mq(q);
```

导航后重复 Step 1 的 `begin('refinement', …)`。`take_screenshot`。期望：海报四区齐全但**静止**（无横幅落下、无绿勾循环、无斜扫、无 barber-pole 滚动）。再注入锚点 + `markReady()`，期望走 200ms 整屏淡出降级（不做位置变形）。

- [ ] **Step 6: 错误/超时 graceful dismiss**

新导航（清掉 reduce 覆盖）后 `begin('refinement', …)`，再 `evaluate_script`：

```js
window.__loader.dismiss();
return window.__loader.state.phase; // 期望 'idle'
```

期望：海报立即消失，无残留遮罩（模拟 SSE error / 180s 超时路径）。

- [ ] **Step 7: 记录结论**

把目视结论（构图 / 配色 / 节奏 / 收束是否平滑 / reduce 是否静止）回报给用户；如需 v2 微调（行高 clamp 阈值、`…+N` 排版——spec §13 留到本阶段定）则在此迭代。**不另起单测**——目视是该层的验收手段。

---

## 自检（Self-Review，对照 spec）

**1. Spec 覆盖：**
- §3 状态文案绑 `state.currentMessage` + 回退「定稿中…」 → Task 2（`statusTextRefine`）+ Task 5（`updateProgress`）✓
- §3 配色：红/蓝/黄/黑用全局 token，绿/橙（+奶油）作组件作用域变量 → Task 2 Step 7-8 ✓
- §3/§6.5 英文副标题 `romanizeCity`，未命中省略 → Task 1 + Task 2（`cityEnRefine` + `v-if`）✓
- §6 `playEntrance`/`playFlipDismiss` 按 poster 分支；Poster A 不动 → Task 3 ✓
- §8 天数自适应 N 行，N>8 折叠「…+(N-8)」 → Task 2（`ledgerRows`/`foldedCount`）+ 组件测试 N=3/7/12 ✓
- §7 接入点：DraftView `begin`、Result `data-flip-id` + `updateProgress`/`markReady`(nextTick)/`dismiss` → Task 4 + Task 5 ✓
- §9 reduce（CSS `@media` 门控 + Flip reduce 淡出）、error/超时 `dismiss`、重试不复现 → Task 2 Step 8 媒体查询 + Task 5（含重试 no-op 说明）✓
- §11 测试：单测 + 组件测试 + 端到端目视 → Task 1 / Task 2 / Task 6 / Task 7 ✓
- §10 差异（`Flip.fit`、`metaLine`、180s 超时）→ 计划中一致采用 ✓

**2. 占位扫描：** 无 TBD/TODO/「类似上文」；所有代码步骤含完整可粘贴代码与精确命令。

**3. 类型/命名一致性：** `romanizeCity`（Task 1 定义 → Task 2 import）、`cityEnRefine`/`statusTextRefine`/`ledgerRows`/`foldedCount`/`rowDelay`/`REFINE_CYCLE`/`MAX_LEDGER_ROWS`（Task 2 定义 → markup 使用）、ref `bannerRef`/`ledgerRef`/`spreadRef`/`statusRefB`/`geoRef`（Task 2 声明+绑定 → Task 3 在 `playFlipDismiss` 使用）、`playEntranceConstruction`/`playEntranceRefinement`（Task 3 改名+新增 → watcher 调用）、CSS 类名（`.bh-poster--refine`/`.pb-*` markup ↔ 样式 ↔ 测试选择器）均一致。`begin('refinement', …)` 的 `LoaderContext` 字段（`city`/`days`/`attractionCount`/`metaLine`）与 Phase A 接口一致。

---

## 执行交接

计划已落盘。两种执行方式：

1. **Subagent-Driven（推荐）** —— 每个 Task 派发独立 subagent，任务间评审，快速迭代（REQUIRED SUB-SKILL: superpowers:subagent-driven-development）。
2. **Inline 执行** —— 本会话内按 executing-plans 批量执行 + 检查点评审（REQUIRED SUB-SKILL: superpowers:executing-plans）。

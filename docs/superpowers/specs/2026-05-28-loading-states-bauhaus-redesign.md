# 加载页 Bauhaus 重设计（Loading States Bauhaus Redesign）

**日期：** 2026-05-28
**类型：** 前端 UX/UI 重设计
**依赖：** [2026-05-25 Bauhaus 设计系统](./2026-05-25-bauhaus-redesign.md)（color/typography/border tokens 已落地于 `frontend/src/styles/bauhaus-tokens.css`）

## 1. 背景

当前应用中两段长加载体验体验割裂、缺乏设计感：

| 段 | 入口 → 出口 | 实际时长 | 当前实现 | 问题 |
|---|---|---|---|---|
| **A** | DiscoverView (planning phase) → DraftView | ~40s（30s 后端规划 + 10s 第一天 onAssemble） | `PlanProgress.vue` 嵌入视图 → `router.push('/draft/:id')` → `a-spin "加载草稿中"` | 步骤清单跑完后**硬切**路由，草稿页再用通用 `a-spin` 等 10 秒，体验断成三段；与新 Bauhaus 视觉体系割裂 |
| **B** | DraftView (finalize) → Result | ~60s 流式 | `<a-skeleton>` × 3 行 + 文字"AI 正在为你定制行程" | 通用 antd 骨架屏，毫无设计感；与 Bauhaus 体系割裂 |

## 2. 目标 / 非目标

### Goals
- 把两段加载变成**Bauhaus 海报式品牌瞬间**，让等待变成有设计感的过渡而非空白。
- 消除 A 段的"30s 漂亮 → 切页 → 10s 丑陋 spin"断层，让 A 段感知为**一段连续过渡**直到 Draft 页内容可见。
- 加载页与目标页 Hero 通过 **GSAP Flip** 共享元素演变，让切换感知为"演化"而非"替换"。
- 在等待中展示用户行程的元数据（城市、天数、选中景点数、当前后端节点）以避免乏味。

### Non-goals
- 不引入新的后端事件类型或修改 LangGraph 节点结构。
- 不替换 Result 页 SSE 流式填充期间的内部 skeleton 行为（流式 patch 已工作良好）；本次只替换 Draft → Result 之间那段全屏 overlay。
- 不做"实用插页"（让用户在等待时填表）的方案。
- 不重做 DraftView 单天级别的小型加载状态（`dayBusy` 那种局部 spin）。

## 3. 设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 加载页定位 | 品牌瞬间（Bauhaus 海报式过渡） | 用户明确选定 |
| 内容密度 | 几何 + 数据（行程元数据作为海报排版元素） | 30-60s 等待需避免纯抽象乏味，又不引入多幕叙事的后端复杂度 |
| 切换策略 | 共享元素演变（GSAP Flip） | 选项 A 硬切 = 现状；选项 B 简单淡出无承接关系；C 让海报的核心元素演化为目标 Hero，最 Bauhaus |
| 海报数量 | 同设计语言、两个独立构图 | A 讲"构建" / B 讲"打磨"，共享 token，但通过不同构图避免审美疲劳 |
| 组件挂载位置 | 全局 overlay（挂在 `App.vue` 顶层） | 横跨路由切换，吞掉 A 段的 10s 草稿初始化 |
| 加载状态机 | composable `useTripLoader()` 集中管理 | 让 DiscoverView / DraftView / Result.vue 都只调用简单 API，状态机自己处理时序和 Flip |
| 动画库 | GSAP（已通过 `gsap-skills` 引入） | Flip 插件是共享元素动画的标准实现；timeline 适合编排多幕动效；SplitText 用于文字字符级动画 |

## 4. 架构

### 4.1 顶层结构

```
App.vue
├── <RouterView />
└── <BauhausLoader />   ← 新组件，z-index: 1000, position: fixed
                          受 useTripLoader() 状态驱动，默认隐藏
```

### 4.2 状态机 composable

`frontend/src/composables/useTripLoader.ts`

```ts
type Poster = 'construction' | 'refinement'
type LoaderState =
  | { phase: 'idle' }
  | { phase: 'entering', poster: Poster, context: LoaderContext }
  | { phase: 'steady',   poster: Poster, context: LoaderContext, currentNode: string, progress: number }
  | { phase: 'flipping', poster: Poster, context: LoaderContext }

interface LoaderContext {
  city: string                  // 高亮在海报上
  days: number                  // 巨型数字 / Hero 复用
  attractionCount: number       // "12 SPOTS" 黄方块
  weatherSummary?: string       // 可选，海报小角落
  flipTargetId: string          // 默认 'loader-hero'，目标页对应元素的 data-flip-id
}

export function useTripLoader() {
  return {
    begin(poster: Poster, ctx: LoaderContext): void
    updateProgress(node: string, message: string, progress: number): void
    markReady(): void           // 调用方告知"目标页内容已可见"，触发 flip 收束
    dismiss(): Promise<void>    // 用于错误路径直接撤场（无 flip）
  }
}
```

`begin()` 把 loader 从 `idle` 推入 `entering`，开始入场动画；动画到 `steady` 后等候 `markReady()`；触发 flip 后到 `flipping`，动画结束再回 `idle`。

### 4.3 BauhausLoader 组件

`frontend/src/components/loader/BauhausLoader.vue`

- 单文件组件，内部 `<template v-if="state.poster === 'construction'">` 和 `<template v-else-if="state.poster === 'refinement'">` 渲染两套构图。
- 共享：色块/几何 token、Flip 出口元素 `data-flip-id`、底部状态条、入场/退场 timeline 外壳。
- 不直接读取后端 SSE，仅消费 composable 暴露的 `currentNode` / `progress` / `context`。

### 4.4 Flip 目标约定

两个目标页各自定义一个"待变形"元素：

- `DraftView.vue` 的 Hero 区域：`<div class="bh-flip-anchor" data-flip-id="loader-hero">{{ city }} · {{ days }} 日</div>`
- `Result.vue` 的 Hero 区域：同样的 `data-flip-id="loader-hero"`，但放在 ResultHero 红色块内

dismiss 时序（在 `useTripLoader` 内部）：
1. 调用方调 `markReady()`，`state.phase` 切到 `flipping`。
2. BauhausLoader 内的 `watchEffect` 看到 phase 变化，先用 GSAP timeline 把装饰元素（圆/三角/方块/状态条）stagger 0.05 飞散/淡出（300ms）。
3. 装饰退场动画完成后：
   1. 抓取 `state = Flip.getState('[data-flip-id="loader-hero"]')` — 此刻 loader 内的红块仍是唯一匹配。
   2. **同步**移除 loader 自己那个元素的 `data-flip-id` 属性（绑定到一个 reactive `flipDetached` ref 上，模板里 `:data-flip-id="flipDetached ? null : 'loader-hero'"`）。
   3. `await nextTick()`，DOM 已更新，目标页 Hero 的元素变成唯一匹配。
   4. `Flip.from(state, { duration: 0.7, ease: 'power3.inOut', absolute: true, onComplete: () => store.phase = 'idle' })`。
   5. loader 整体 `v-if` 在 phase 回到 idle 时卸载（GSAP 收束已经完成，目标页 Hero 已在最终位置）。

> Flip 的契约是"对同一个 selector 在两次调用之间的布局变化做反向动画"。本设计利用了**两个 DOM 元素共享同一个 selector**这件事——getState 捕获 loader 元素的位置，detach 后 from() 测量到目标元素的位置，于是 Flip 就把视觉差量画出来。这一步对时序敏感，必须按上面 3.1–3.4 的顺序，不能省 `nextTick`。

### 4.5 各视图接入点

| 视图 | 改动 |
|---|---|
| `DiscoverView.vue` | `confirmAndPlan()` 内部不再渲染 `<PlanProgress>`；改为调 `useTripLoader().begin('construction', {...})`；SSE `node_complete` 事件转给 `updateProgress`；`complete` 事件触发 `router.push('/draft/:id')`，但**不**立即 `markReady` — 由 DraftView 接力 |
| `DraftView.vue` | `onMounted` 时如果 `useTripLoader().state.phase !== 'idle'`，说明从 Discover 接力来的 loader 还在；等 `loadDraft + onAssemble(0)` 都 resolved 后调 `markReady()`。不再显示 `<a-spin tip="加载草稿中">`（被 loader 覆盖了） |
| `DraftView.vue` 的 `onFinalize` | 调 `useTripLoader().begin('refinement', {...})`，然后 `router.push('/result?streaming=true&draft_id=...')` |
| `Result.vue` | `onMounted` 时如果 loader phase 不是 idle，等 SSE 流式拿到 `tripPlan` 首个非空对象后调 `markReady()`。期间隐藏当前 `result-skeleton` div |
| `App.vue` | 在 `<router-view>` 同级新增 `<BauhausLoader />` |

## 5. Poster A · CONSTRUCTION

详细 mockup：`.superpowers/brainstorm/51605-1779963574/content/02-poster-a-construction.html`（本次会话生成）

### 构图（白底 + Bauhaus tokens）
- **左上**：64px 黄圆（`--primary-yellow`）+ 内圈缺口黑色 ring，CSS animation 旋转
- **右上**：黑色 corner-tag，文案 `CONSTRUCTING · <step>/<total>`
- **中左**：巨型黑色数字 = `days`，font-size 280px，font-weight 900，letter-spacing -0.06em
- **中右**：**Flip target**。红色块（`--primary-red`） + 8px 偏移黑色硬阴影。内含：
  - `city` 中文 42px 900
  - `city` 英文大写 14px letter-spacing 0.42em
  - 横向白色分隔线
  - "SUMMER · 2026" 小字 12px letter-spacing 0.14em
- **左下**：蓝色三角（`--primary-blue`），轻微旋转 15°，drop-shadow 3px 3px 0
- **右下**：88px 黄方块，内含 `attractionCount`（大字 36px）+ "SPOTS" 小字
- **底部**：黑色状态条，左侧 `▶ <currentNode label>`，中间黄色进度条，右侧 `<progress>%`
- **背景元素**：38% 处一条贯穿的 2px 黑色垂直轴线

### 动效（5 幕，GSAP timeline）
1. **SCAFFOLD** (0–0.6s) — 垂直轴线从顶部 drawSVG 划下（或 scaleY from 0），白底亮起
2. **SHAPES IN** (0.6–1.6s) — 黄圆从上空 drop + back.out 回弹；蓝三角旋转入场；黄方块从右下滑入；GSAP stagger 0.1
3. **DATA REVEAL** (1.6–3.4s) — 巨型 `days` 从 0.6→1 scale + back.out；红块从右滑入；`city` 用 SplitText 字符级 stagger 浮现；`attractionCount` 数字从 0 ticker 滚到目标值
4. **STEADY** (3.4 – N s) — 黄圆持续 CSS rotate；状态条根据 `currentNode` / `progress` 更新；红块极轻微 breathing（scale 1 → 1.005 → 1，3s loop）；三角 floaty drift
5. **LOCK & FLIP** (N – N+1.0s) — 装饰元素 stagger 0.05 飞散/淡出（300ms），同时抓取 Flip state；nextTick 后 Flip.from 把红色块 + 巨型数字一起搬到 Draft Hero（700ms power3.inOut）

## 6. Poster B · REFINEMENT（待实现阶段细化）

由于用户希望先看到 A 段实现效果再决定 B 的细节，本节只定下硬约束，具体构图与 Flip 目标的匹配在实现时再细化：

- **同设计语言**：复用同一套 Bauhaus tokens（颜色、字体、边框、阴影），目标是让用户感觉是"同一个产品的另一个时刻"。
- **不同构图叙事**：从"构建（拼装）"切到"打磨（精细化）"。候选视觉语言：
  - 网格背景（暗示日程表/排版尺）
  - 多个细长水平 bar 逐行填充（暗示每一天的行程被精雕）
  - 红色块的位置 / 形态变化（例如从居中变成顶部 banner，预示 Result 页 Hero 是顶部红条）
- **同一 Flip 目标 id**：`loader-hero`。这样 BauhausLoader / useTripLoader 不需要为两段加载分别管理 selector。
- **Result 页 ResultHero 必须保留一个 `data-flip-id="loader-hero"` 的红色色块容器**（当前 Result.vue 的 hero-content 已经在红色容器内，需要在合适位置加上 data 属性）。
- 实现这一段时再单独画一张 mockup 给用户确认构图。

## 7. 降级与边界

### 7.1 reduced-motion
GSAP 用 `gsap.matchMedia()` 包装动画块，对 `(prefers-reduced-motion: reduce)` 用户：
- 跳过所有几何元素的入场/退场动画，直接显示静态海报
- Flip 收束改为 200ms opacity 淡出 + 目标页 opacity 淡入（不做位置变换）
- 状态条仍正常更新（信息可达性）

### 7.2 SSE 错误 / 超时
- DiscoverView 或 Result.vue 监听到 SSE error 事件 → 调 `useTripLoader().dismiss()` 直接撤场（无 Flip），现有的 error UI 接管
- 设一个保险 timeout：90s 还没收到 `complete` 事件 → 自动 dismiss + 显示"耗时较长"提示但允许继续等待
- 网络断开导致 SSE 中断 → 同样 dismiss，配 antd `message.error`

### 7.3 用户主动取消
- 加载页右上角 corner-tag 旁加一个小型关闭按钮（hover 才显现，避免误触）→ 调 `dismiss()` + cancel SSE 请求（需 backend AbortController 配合，但这是次要优化，初版可省）

### 7.4 路由切换时机
- A 段：SSE `complete` 事件返回 `draft_id` 后**立即** `router.push`，loader 保持显示；目标页 Hero 占位元素需在 Vue mount 时立即存在（无条件渲染骨架，等数据填进来）
- 不能等 Draft 数据全 ready 再切路由 — 那样 loader 卡在 Discover 上、用户看不到草稿页内容的反馈

## 8. 测试策略

- **单元测试**（`backend` 无关，全在 `frontend`）：
  - `useTripLoader` 状态机：begin/updateProgress/markReady/dismiss 的 phase 迁移正确
  - 在错误路径下 phase 能从任意状态回 idle
- **组件测试**（Vitest + Vue Test Utils）：
  - BauhausLoader 渲染两套海报时 DOM 结构正确
  - context 字段缺失时不崩
  - reduced-motion 媒体查询模拟下不执行 GSAP 入场 timeline
- **端到端目视**（手动）：
  - 完整跑一次"Discover → Draft → Result"，观察两段 Flip 收束流畅度
  - 慢速 3G 模拟下 loader 不闪烁
  - 错误路径（断网中途）loader 能 graceful dismiss

## 9. 实现步骤（高层）

1. 安装 GSAP（**当前 frontend/package.json 未安装**：`npm install gsap`）+ 在 main.ts 注册 Flip 插件、SplitText 插件
2. 写 `useTripLoader` composable + 单元测试
3. 写 `BauhausLoader.vue` 框架（不含 GSAP，先用 CSS 渐变模拟入场）+ 组件测试
4. 接入 `App.vue`
5. 改 `DiscoverView.vue`：移除 `<PlanProgress>`，调 `useTripLoader`
6. 改 `DraftView.vue`：注入 `data-flip-id` 元素 + 移除 `a-spin` + 接力 markReady
7. 加入 Poster A 的 GSAP timeline（入场 + steady + flip）
8. 改 `DraftView.onFinalize` + `Result.vue` 类似接入
9. 实现 Poster B 构图（独立单独 PR，回到 brainstorm 跟用户确认构图）
10. 加 reduced-motion / 错误降级
11. 端到端目视验证、灯节点更新流畅度

## 10. 留待实现阶段决定的细节

- 黄方块 "12 SPOTS" 是否在 Flip 组里一起搬到 Draft Hero（设计上可以放，但 Draft Hero 当前没那个位置）
- 状态条文案的中文映射（每个 LangGraph 节点的对应短语）建议复用 `PlanProgress.vue` 现有的 `steps` 配置
- 进度条百分比的计算公式（按节点完成数 / 总节点数？还是用 SSE 事件里的 progress 字段？）
- Poster B 详细构图（见 §6，留到下一轮 brainstorm）

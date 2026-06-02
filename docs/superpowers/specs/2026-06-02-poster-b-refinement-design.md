# Poster B · REFINEMENT 详细设计（定稿打磨 / FINAL PROOF）

**日期：** 2026-06-02
**类型：** 前端 UX/UI 重设计（加载页 Poster B 构图实现）
**父 spec：** [2026-05-28 加载页 Bauhaus 重设计](./2026-05-28-loading-states-bauhaus-redesign.md) —— 本文档落实其 §6「Poster B · REFINEMENT（待实现阶段细化）」与 §9 步骤 9「Poster B 独立 PR，回到 brainstorm 跟用户确认构图」。
**前置：** Phase A（Poster A · CONSTRUCTION + 状态机 + Flip 基础设施）已实现并合并。

---

## 1. 背景与定位

加载体验「B 段」：`DraftView` 点击「定稿并保存」(`onFinalize`) → `Result.vue` SSE 流式合成，约 **60 秒**。当前该段用通用 `<a-skeleton>` × 3 行 + 文字「AI 正在为你定制行程」，与 Bauhaus 体系割裂。

本段要替换为与 Poster A 同设计语言、但叙事不同的全屏 Bauhaus 海报：**Poster A 讲「拼装 construction」，Poster B 讲「校样打磨 refinement」**——草稿已成形，正在做最后的精修定稿。

**已确认的视觉方案**（用户已审批）：印刷厂「终校样张 / FINAL PROOF」。
mockup：`.superpowers/brainstorm/49110-1780383286/content/poster-b-final-proof.html`（本文档 §4 内联其构图，以防 brainstorm 目录被清理）。

## 2. 目标 / 非目标

### Goals
- 用 Poster A 同一套 Bauhaus tokens（红/蓝/黄/黑 + 边框 + 硬阴影），新增**绿 + 橙**两色承载「精修通过 / 运动焦点」语义，做出一张「同一产品的另一个时刻」的海报。
- 全程动效为**时间驱动的循环**，不绑后端进度百分比（后端 finalize 只发 3 个粗事件，中间静默 ~60s）。
- 复用 Phase A 的状态机 `useTripLoader` 与 Flip 收束基础设施：海报顶部红色横幅在收束时平滑变形成 Result 页顶部红色 Hero 条。

### Non-goals
- **不改** `useTripLoader.ts` 的状态机与 `LoaderContext` 接口（现有字段够用）。
- **不引入**新的后端事件类型，不改 LangGraph / finalize 端点。
- **不绑定**任何真实进度百分比到动画（用户明确决策）。
- **不动** Poster A（CONSTRUCTION）的构图与动效。
- **不修** Poster A 已知遗留的 `cityEn = city.toUpperCase()` 中文重复 bug（见 §10，本段用新方案 `romanizeCity()` 规避，但不回头改 A）。

## 3. 设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 视觉方案 | 印刷厂「终校样张 / FINAL PROOF」 | 用户从 3 个方向中授权我选定并审批；叙事「校样打磨」最贴合 refinement |
| 动效模型 | **时间驱动 CSS 循环** + 仅 Flip 收束用 GSAP | 后端无逐节点进度事件；用户决策「做动画给加载感即可，不绑百分比」 |
| 配色扩展 | 在红/蓝/黄/黑基础上加 **绿 `#0E9F6E`**（精修/通过）+ **橙 `#E8772E`**（旋转校样标焦点） | 用户授权「可用红蓝黄以外的颜色」；绿与 A 的暖色系区分，专表「通过」 |
| 配色落地 | 红/蓝/黄/黑复用现有全局 token（`--primary-red/blue/yellow`、`--foreground`）；绿/橙先**作组件作用域 CSS 变量**定义在 `BauhausLoader` 内 | mockup 里的 `#D02020` 等是独立渲染用的硬编码，入应用必须走设计系统变量保持一致；绿/橙暂仅 Poster B 使用，不污染全局 token，将来复用再提升 |
| 底部状态条文案 | **绑定后端真实 SSE step 文案**（`整理行程… / 生成总体建议… / 写入历史…`），缺省回退 `定稿中…` | 后端 finalize 本就发这 3 段中文 message；显示真实文案比 mockup 里的 CSS 假循环更诚实。barber-pole 斜纹仍为不确定态、**不显示百分比** |
| 英文城市副标题 | 内置 `romanizeCity()` 小映射表，命中显示、未命中**优雅省略**英文行 | 中文 `toUpperCase()` 无效会重复出中文（即 A 的遗留 bug）；映射表保住双语印刷质感，又不冒乱码音译 |
| 海报组件结构 | 复用单文件 `BauhausLoader.vue`，替换其 `v-else` 占位为 REFINEMENT markup；`playEntrance` / `playFlipDismiss` 改为**按 `state.poster` 分支** | 现有这两个函数写死了 construction 的 ref，必须分支才能驱动 B 的不同元素 |

## 4. 视觉构图

整体：一张自包含的 `aspect-ratio` 海报，纸底 `--paper`，4px 黑边 + `12px 12px 0` 硬阴影。四区布局：

- **① 顶部红色横幅（Flip 源）** —— `--primary-red` 底，下沿黑色粗边。左侧城市中文（如「北京」900 字重）+ 英文副标题（`BEIJING · 5日`，由 `romanizeCity()` 提供，未命中则省英文）+ 右侧 `FINAL PROOF` 描边徽标。四角**裁切定位十字**（印刷感）。**收束时此横幅 `Flip.fit` 到 Result 顶部红 Hero 条。**
- **② 左栏「日程校样」台账** —— 标题 `DAYS · 日程校样`；按真实天数渲染 `01…N` 行，每行右侧一个方框对勾，绿色 `--bh-green` **逐日点亮**（CSS 循环，非真实进度，见 §8 天数自适应）。台账底部沉着排列**蓝三角 / 绿圆 / 黄方**——Poster A 几何件的「归位」回响。
- **③ 右栏奶油色「总体建议」排版区** —— 标题 `OVERVIEW · 总体建议` + 旋转的**橙色 `✳` 校样标**；下方 6 行带色块首字的正文条；一道**高光斜扫**反复掠过（打磨/抛光）；右下旋转 -9° 的绿色 **「定稿中 / FINALIZING」印章**在呼吸。
- **④ 底部黑色状态条** —— 左侧 `▶ <当前 SSE step 文案>`（绑定 `state.currentMessage`）；右侧黄色 **barber-pole 斜纹**表「进行中」，不显示百分比。

## 5. 动效模型

**入场 + steady 全部用 CSS keyframes 循环**（时间驱动），GSAP 只参与 Flip 收束：

| 动效 | 实现 | 说明 |
|---|---|---|
| 横幅落下入场 | CSS `pbBannerIn`（一次性） | 海报挂载即播 |
| 绿勾逐日点亮 | CSS 循环，按行 stagger delay（delay 按真实天数计算） | 装饰，非进度 |
| 高光斜扫 | CSS `pbSweep` 循环 | 打磨/抛光暗示 |
| `✳` 校样标慢转 | CSS `pbSpin` 循环 | 橙色焦点 |
| 「定稿中」印章呼吸 | CSS `pbStamp` 循环 | scale 微动 |
| barber-pole 斜纹 | CSS `pbBarber` 循环 | 不确定态进行中 |
| 底部文案 | 绑定 `state.currentMessage`（非动画切换） | 随真实 SSE step 变 |
| **Flip 收束** | **GSAP `Flip.fit`**（仅此一处用 GSAP） | 见 §6 |

> 与 mockup 的唯一差异：mockup 底部文案是 CSS 三段假循环；落地改为绑定真实 SSE step 文案（§3）。其余动效与 mockup 一致。

## 6. 组件架构与改动

### 6.1 `BauhausLoader.vue`
1. **模板**：`v-else class="bh-poster--placeholder"` 占位（当前第 43 行）替换为 REFINEMENT 海报 markup（§4 四区）。construction 分支 `v-if="state.poster === 'construction'"` 不变。
2. **新增 ref**（绑定 refinement 元素，供 Flip 收束用）：
   - `bannerRef` → 顶部红横幅（**Flip 源**）
   - `ledgerRef` / `spreadRef` / `statusRefB` / `geoRef` → 收束前先淡出的装饰组
   - （只有一套海报会 mount，construction 的 ref 在 refinement 下为 null，反之亦然）
3. **`playEntrance()` 分支**：抽出现有函数体为 `playEntranceConstruction()`；新增 `playEntranceRefinement()`。后者无需 GSAP timeline——入场是 CSS，函数体只在下一帧调用 `setSteady()` 推进状态机（reduce 模式同样调用，差异纯由 CSS `@media` 处理）。`watch(phase)` 里 `entering` → 按 `state.poster` 选其一。
4. **`playFlipDismiss()` 分支**：保留共享的安全兜底计时器（2500ms）、reduce 淡出降级、`Flip.fit` 主体；仅把「Flip 源」和「装饰组」按 poster 选择：
   ```ts
   const isRefine = state.poster === 'refinement'
   const src   = isRefine ? bannerRef.value : heroRef.value
   const decor = (isRefine
     ? [ledgerRef.value, spreadRef.value, statusRefB.value, geoRef.value]
     : [axisRef.value, circleRef.value, cornerRef.value, megaRef.value, triangleRef.value, squareRef.value, statusRef.value]
   ).filter(Boolean)
   ```
   其余（查 `[data-flip-id="loader-hero"]`、装饰 stagger 淡出、`Flip.fit(src, dest, {duration:0.7, ease:'power3.inOut', absolute:true, scale:true})`、淡出后 `doFinish()`）完全复用。
5. **`cityEn`**：refinement 海报不用 `ctx.value.city.toUpperCase()`，改用 `romanizeCity(ctx.value.city)`，返回 `null` 时模板 `v-if` 省略英文行。
6. **样式**：`.bh-loader { --bh-green:#0E9F6E; --bh-orange:#E8772E; }` 组件作用域定义绿/橙；其余颜色用现有全局 token。所有 CSS 循环动画包在 `@media (prefers-reduced-motion: no-preference)` 内。

### 6.2 新文件 `frontend/src/components/loader/cityRomanization.ts`
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
（纯拉丁字符的城市名直接大写；中文未命中映射则返回 null 省略，避免重复出中文。）

## 7. 数据流与接入点

| 位置 | 改动 |
|---|---|
| `DraftView.onFinalize` | 在 `router.push('/result?...')` **之前**加 `tripLoader.begin('refinement', { city: draft.value.city, days: draft.value.request.travel_days, attractionCount: <各天景点数之和>, metaLine: \`${start_date} – ${end_date}\` })` |
| `Result.vue` 模板 | 给 `.result-hero`（第 28 行 `v-if="tripPlan"` 的红块）加 `data-flip-id="loader-hero"`，作为 Flip 落点 |
| `Result.vue startStreaming` `progress` 分支 | 加 `tripLoader.updateProgress(event.step, event.message, 0)`，驱动底部状态条真实文案 |
| `Result.vue startStreaming` `complete` 分支 | 在 `tripPlan.value = …`（及既有 `router.replace`）之后，`await nextTick(); tripLoader.markReady()`——`.result-hero` 此时才在 DOM 中，Flip 才找得到落点（依赖 `/result` 与 `/trip/:id` 复用同一 Result 实例、`tripPlan` 不丢；测试中验证）。确保 `nextTick` 已 import |
| `Result.vue` `error` 分支 + `catch` | 加 `tripLoader.dismiss()` 直接撤场，露出 error skeleton |

`LoaderContext` 不变：`days` 驱动台账行数，`metaLine` 显示日期区间，`city` 经 `romanizeCity` 得英文副标题。

## 8. 天数自适应

mockup 写死 5 行。落地按真实 `ctx.days` 渲染 `01…N`：
- 绿勾点亮的 CSS `animation-delay` 按 N 计算（等分一个循环周期）。
- 行高用 `clamp()` 随 N 收缩；**N > 8 时只渲染前 8 行 + 末行显示 `…+(N-8)`** 防纵向溢出。
- 几何三件（三角/圆/方）与天数无关，固定 1 组。

## 9. 降级与边界

### 9.1 reduced-motion
- 所有 CSS 循环动画包在 `@media (prefers-reduced-motion: no-preference)`：reduce 用户看到**静态海报**（横幅/台账/排版/状态条都在，仅不动）。
- Flip 收束：复用 `playFlipDismiss` 已有的 reduce 分支——`window.matchMedia('(prefers-reduced-motion: reduce)')` 命中则 `.bh-loader` 200ms opacity 淡出，不做位置变形。
- `playEntranceRefinement` 在 reduce 下仍调 `setSteady()`，状态机正常推进。

### 9.2 SSE 错误 / 超时
- finalize SSE `error` 事件或 `catch`（含 `finalizeDraftStream` 默认 **180000ms** fetch 超时）→ `tripLoader.dismiss()` 撤场，Result 现有 error skeleton + 重试按钮接管。
- **不另设独立看门狗**：骑在既有 180s fetch 超时上即可（**更正父 spec §7.2 的 90s 表述**，以实际代码为准）。

### 9.3 重试路径
- `onRetry` → `startStreaming()` 时 loader 已 `dismiss` 回 idle，**不重新拉起 Bauhaus 海报**（重建 context 成本高、收益低）；回退到现有 `result-skeleton`。Poster B 只在首次 finalize 过渡时出现。

### 9.4 与父 spec 非目标的澄清
父 spec 非目标提到「不替换 Result 页 SSE 流式填充期间的内部 skeleton」，指的是**主行程图逐节点 streaming patch**那条流；本段替换的是 **finalize 那 60s 的全屏等待**（父 spec §1 表格「B 段」明确列为重设计对象）。loader overlay（z-index 2000）覆盖在 `result-skeleton` 之上；skeleton 保留作为 reduce/重试路径的底层。

## 10. 与父 spec / 现状的差异澄清（内部一致性）

父 spec §4 当年是实现前草图，与实际落地代码有出入，本 spec 一律**以实际代码为准**：

| 项 | 父 spec 草图 | 实际代码（本 spec 依据） |
|---|---|---|
| `LoaderContext` 字段 | `weatherSummary?` / `flipTargetId` | `metaLine?`，无 `flipTargetId`（Flip id 固定 `loader-hero`） |
| Flip 机制 | `Flip.getState` + detach + `Flip.from` | `Flip.fit(source, dest)`（`BauhausLoader.vue` `playFlipDismiss`） |
| 超时看门狗 | 90s | 180s（`finalizeDraftStream` fetch timeout） |
| Poster A `cityEn` | —— | `city.toUpperCase()` 对中文重复出中文（已知遗留 bug，本段不修，B 用 `romanizeCity` 规避） |

## 11. 测试策略

- **单元测试**（Vitest）：
  - `cityRomanization.ts`：命中映射、未命中中文返回 null、纯拉丁大写。
  - `useTripLoader` 状态机迁移已有 Phase A 覆盖，无新增（接口不变）。
- **组件测试**（Vitest + Vue Test Utils）：
  - `state.poster === 'refinement'` 时渲染 REFINEMENT 海报 DOM（横幅/台账/排版/状态条齐全）。
  - 天数自适应：`days` = 3 / 7 / 12 时台账行数与 `…+N` 折叠正确。
  - `context` 字段缺失时不崩（沿用 ctx 兜底 computed）。
  - 底部状态条随 `state.currentMessage` 变化；缺省显示 `定稿中…`。
- **端到端目视**（手动 / Chrome DevTools MCP）：
  - 用 memory「driving-bauhaus-loader-in-browser」记的 HMR 版本化 URL 手法，`begin('refinement', …)` → `markReady()` 驱动真实 Flip 收束（Result 页需有 `[data-flip-id="loader-hero"]`，或注入临时锚点）。
  - reduce 模式（`initScript` 覆盖 `matchMedia`）下海报静止、收束走淡出。
  - 断网/错误中途 loader 能 graceful dismiss。

## 12. 实现步骤（高层）

1. 新建 `cityRomanization.ts` + 单测。
2. `BauhausLoader.vue`：替换 `v-else` 为 REFINEMENT markup + 新 ref + 绿/橙作用域变量 + CSS 循环动画（reduce 媒体查询门控）。
3. `BauhausLoader.vue`：`playEntrance` / `playFlipDismiss` 按 `state.poster` 分支；`cityEn` 改用 `romanizeCity`。
4. `DraftView.onFinalize`：前置 `tripLoader.begin('refinement', …)`。
5. `Result.vue`：`.result-hero` 加 `data-flip-id`；`startStreaming` 加 `updateProgress` / `markReady`(nextTick) / `dismiss`。
6. 组件测试 + 天数自适应测试。
7. 端到端目视（含 reduce、错误路径）。

## 13. 留待实现阶段决定的细节

- `attractionCount` 取值口径：`draft.days[*]` 每天景点数之和 vs 去重后的唯一景点数——实现时取与 Poster A 一致的口径。
- `romanizeCity` 映射表的初始城市清单可按后端实际高频城市增补（不影响架构）。
- 台账 `…+N` 折叠的具体排版微调（行高 clamp 阈值）留到目视阶段调。

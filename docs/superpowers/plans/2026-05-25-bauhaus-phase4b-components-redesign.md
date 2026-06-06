# 包豪斯风格重新设计 - 阶段 4B：内容组件改造

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造所有内容组件，应用包豪斯风格

**Architecture:** 统一所有卡片、按钮、输入框的包豪斯样式

**Tech Stack:** Vue 3, TypeScript, 包豪斯样式系统

**Design Spec:** `docs/superpowers/specs/2026-05-25-bauhaus-redesign.md`

**依赖：** 阶段 1-4A 已完成

---

## 需要改造的组件列表

### Result 页面组件（5 个）
1. `frontend/src/components/result/TabOverview.vue` - 行程概览
2. `frontend/src/components/result/TabItinerary.vue` - 每日行程
3. `frontend/src/components/result/TabBudget.vue` - 预算明细
4. `frontend/src/components/result/TabMap.vue` - 地图
5. `frontend/src/components/result/TabWeather.vue` - 天气

### 通用组件（4 个）
6. `frontend/src/components/AttractionCard.vue` - 景点卡片
7. `frontend/src/components/HotelCard.vue` - 酒店卡片
8. `frontend/src/components/DayTimeline.vue` - 每日时间线
9. `frontend/src/components/SelectableAttractionCard.vue` - 可选景点卡片

### Draft 页面组件（1 个）
10. `frontend/src/components/draft/DayCard.vue` - 骨架确认页的日卡片

### 其他页面（2 个）
11. `frontend/src/views/DiscoverView.vue` - 发现页
12. `frontend/src/views/MyTrips.vue` - 我的行程页

---

## 包豪斯样式规范（统一应用）

### 卡片样式
```css
.bauhaus-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-6);
  position: relative;
}
```

### 按钮样式
```css
.bauhaus-btn {
  border: var(--border-main) solid var(--border);
  box-shadow: 3px 3px 0px 0px var(--border);
  font-weight: var(--font-black);
  text-transform: uppercase;
}
```

### 标题样式
```css
.bauhaus-title {
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
```

---

### Task 1: 改造 Result 页面的 5 个 Tab 组件

**Files:**
- Modify: `frontend/src/components/result/TabOverview.vue`
- Modify: `frontend/src/components/result/TabItinerary.vue`
- Modify: `frontend/src/components/result/TabBudget.vue`
- Modify: `frontend/src/components/result/TabMap.vue`
- Modify: `frontend/src/components/result/TabWeather.vue`

- [ ] **Step 1: 改造 TabOverview.vue**

统一样式：
- 所有卡片添加粗边框和硬阴影
- 标题全大写、粗体
- 按钮使用包豪斯样式

```vue
<style scoped>
/* 统一卡片样式 */
.overview-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-6);
  margin-bottom: var(--space-6);
}

.card-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-4);
  color: var(--foreground);
}

/* 统计项 */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-4);
}

.stat-box {
  background: var(--background);
  border: var(--border-2) solid var(--border);
  padding: var(--space-4);
  text-align: center;
}

.stat-value {
  font-size: var(--text-4xl);
  font-weight: var(--font-black);
  color: var(--primary-blue);
}

.stat-label {
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  text-transform: uppercase;
  margin-top: var(--space-2);
}
</style>
```

- [ ] **Step 2: 改造 TabItinerary.vue**

每日行程卡片：
- 日期标题使用彩色背景（红/蓝/黄循环）
- 景点卡片统一包豪斯样式
- 时间线使用几何图标

```vue
<style scoped>
/* 日期卡片 */
.day-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  margin-bottom: var(--space-8);
  overflow: hidden;
}

.day-header {
  padding: var(--space-4) var(--space-6);
  border-bottom: var(--border-main) solid var(--border);
}

.day-header:nth-child(3n+1) {
  background: var(--primary-red);
  color: var(--white);
}

.day-header:nth-child(3n+2) {
  background: var(--primary-blue);
  color: var(--white);
}

.day-header:nth-child(3n+3) {
  background: var(--primary-yellow);
  color: var(--foreground);
}

.day-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
}

/* 景点列表 */
.attractions-list {
  padding: var(--space-6);
}

.attraction-item {
  background: var(--background);
  border: var(--border-2) solid var(--border);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
  position: relative;
}

.attraction-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  background: var(--primary-blue);
}
</style>
```

- [ ] **Step 3: 改造 TabBudget.vue**

预算明细表格：
- 表格使用粗边框
- 表头使用黄色背景
- 总计行使用蓝色背景

```vue
<style scoped>
.budget-table {
  width: 100%;
  border-collapse: collapse;
  border: var(--border-main) solid var(--border);
}

.budget-table th {
  background: var(--primary-yellow);
  border: var(--border-2) solid var(--border);
  padding: var(--space-3);
  font-weight: var(--font-black);
  text-transform: uppercase;
  text-align: left;
}

.budget-table td {
  border: var(--border-2) solid var(--border);
  padding: var(--space-3);
}

.budget-table tr:hover {
  background: var(--background);
}

.total-row {
  background: var(--primary-blue);
  color: var(--white);
  font-weight: var(--font-black);
}
</style>
```

- [ ] **Step 4: 改造 TabMap.vue 和 TabWeather.vue**

地图和天气组件：
- 容器使用粗边框
- 标题使用包豪斯样式

```vue
<style scoped>
.map-container,
.weather-container {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-6);
}

.section-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-4);
}
</style>
```

- [ ] **Step 5: 提交 Result Tab 组件**

```bash
git add frontend/src/components/result/
git commit -m "feat(bauhaus): 改造 Result 页面所有 Tab 组件

- TabOverview: 统一卡片和统计项样式
- TabItinerary: 彩色日期标题 + 包豪斯景点卡片
- TabBudget: 粗边框表格 + 彩色表头
- TabMap/TabWeather: 统一容器样式
- 所有组件应用包豪斯设计系统"
```

---

### Task 2: 改造通用卡片组件

**Files:**
- Modify: `frontend/src/components/AttractionCard.vue`
- Modify: `frontend/src/components/HotelCard.vue`
- Modify: `frontend/src/components/DayTimeline.vue`
- Modify: `frontend/src/components/SelectableAttractionCard.vue`

- [ ] **Step 1: 改造 AttractionCard.vue**

```vue
<style scoped>
.attraction-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-4);
  position: relative;
  transition: all var(--transition-fast);
}

.attraction-card:hover {
  transform: translateY(-2px);
  box-shadow: 6px 6px 0px 0px var(--border);
}

/* 右上角装饰 */
.attraction-card::after {
  content: '';
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--primary-red);
}

.attraction-name {
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-2);
}
</style>
```

- [ ] **Step 2: 改造 HotelCard.vue**

```vue
<style scoped>
.hotel-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-4);
  position: relative;
}

.hotel-card::after {
  content: '';
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
  background: var(--primary-blue);
}

.hotel-name {
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  margin-bottom: var(--space-2);
}
</style>
```

- [ ] **Step 3: 改造 DayTimeline.vue 和 SelectableAttractionCard.vue**

应用相同的包豪斯样式原则。

- [ ] **Step 4: 提交通用组件**

```bash
git add frontend/src/components/AttractionCard.vue frontend/src/components/HotelCard.vue frontend/src/components/DayTimeline.vue frontend/src/components/SelectableAttractionCard.vue
git commit -m "feat(bauhaus): 改造通用卡片组件

- AttractionCard: 粗边框 + 红色装饰
- HotelCard: 粗边框 + 蓝色装饰
- DayTimeline: 包豪斯时间线样式
- SelectableAttractionCard: 可选状态包豪斯化
- 统一悬停效果"
```

---

### Task 3: 改造 Draft 和其他页面

**Files:**
- Modify: `frontend/src/components/draft/DayCard.vue`
- Modify: `frontend/src/views/DiscoverView.vue`
- Modify: `frontend/src/views/MyTrips.vue`

- [ ] **Step 1: 改造 DayCard.vue（骨架确认页）**

```vue
<style scoped>
.day-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  margin-bottom: var(--space-6);
}

.day-header {
  background: var(--primary-yellow);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-4);
}

.day-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
}
</style>
```

- [ ] **Step 2: 改造 DiscoverView.vue（发现页）**

根据设计规范 4.2：
- 黄色顶栏
- 白色内容区
- 蓝色底栏

- [ ] **Step 3: 改造 MyTrips.vue（我的行程页）**

根据设计规范 4.4：
- 三色马赛克顶部
- 白色列表区
- 行程卡片带彩色左边框

- [ ] **Step 4: 提交所有更改**

```bash
git add frontend/src/components/draft/ frontend/src/views/DiscoverView.vue frontend/src/views/MyTrips.vue
git commit -m "feat(bauhaus): 改造 Draft、Discover 和 MyTrips 页面

- DayCard: 黄色标题 + 包豪斯卡片
- DiscoverView: 黄色顶栏 + 蓝色底栏
- MyTrips: 三色马赛克 + 彩色边框卡片
- 完成所有页面的包豪斯风格统一"
```

---

## 验证清单

- [ ] **启动开发服务器**
  ```bash
  cd frontend && npm run dev
  ```

- [ ] **测试完整流程**
  1. 首页填写表单 → 提交
  2. 发现页选择景点
  3. 骨架确认页查看
  4. 结果页查看所有 Tab
  5. 我的行程页查看历史

- [ ] **检查所有组件**
  - 所有卡片都有粗边框和硬阴影
  - 所有标题都是全大写、粗体
  - 所有按钮都是包豪斯样式
  - 颜色使用三原色（红/蓝/黄）

---

## 预计工作量

- Task 1: 5 个 Tab 组件 - 约 30 分钟
- Task 2: 4 个通用组件 - 约 20 分钟
- Task 3: 3 个页面 - 约 30 分钟

**总计：约 1.5 小时**

建议分批执行，每完成一个 Task 就提交并测试。

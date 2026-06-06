# 包豪斯风格重新设计 - 阶段 4A：结果页改造

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造 Result.vue，应用包豪斯风格设计

**Architecture:** 红色 Hero + 黄色统计 + 白色内容，使用包豪斯组件和样式

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, 包豪斯组件

**Design Spec:** `docs/superpowers/specs/2026-05-25-bauhaus-redesign.md` - 4.3 结果页

**依赖：** 阶段 1-3 已完成

---

## 设计要求总结

**布局结构：**
1. **红色 Hero 区域** - 行程标题 + 操作按钮（200px 高）
2. **黄色统计区域** - 4 个统计项（80px 高）
3. **Tab 导航** - 包豪斯按钮样式
4. **白色内容区** - 所有卡片带粗边框和硬阴影

---

### Task 1: 改造 Hero 区域和统计区域

**Files:**
- Modify: `frontend/src/views/Result.vue`

- [ ] **Step 1: 备份原文件**

```bash
cp frontend/src/views/Result.vue frontend/src/views/Result.vue.backup
```

- [ ] **Step 2: 修改 Hero 区域为红色背景**

在 template 中找到 Hero 区域，修改为：

```vue
<!-- Hero 区域 - 红色背景 -->
<div class="result-hero">
  <div class="hero-content">
    <h1 class="hero-title">{{ tripData?.title || '您的行程规划' }}</h1>
    <div class="hero-actions">
      <button class="hero-btn" @click="handleSave">
        💾 保存行程
      </button>
      <button class="hero-btn" @click="handleEdit">
        ✏️ 编辑
      </button>
      <button class="hero-btn" @click="handleExport">
        📥 导出
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: 添加统计数据区域（黄色背景）**

在 Hero 区域后添加：

```vue
<!-- 统计数据区 - 黄色背景 -->
<div class="stats-section">
  <div class="stat-item">
    <div class="stat-value">{{ tripData?.days || 0 }}</div>
    <div class="stat-label">天数</div>
  </div>
  <div class="stat-divider"></div>
  <div class="stat-item">
    <div class="stat-value">{{ tripData?.attractions?.length || 0 }}</div>
    <div class="stat-label">景点数</div>
  </div>
  <div class="stat-divider"></div>
  <div class="stat-item">
    <div class="stat-value">¥{{ tripData?.budget || 0 }}</div>
    <div class="stat-label">预算</div>
  </div>
  <div class="stat-divider"></div>
  <div class="stat-item">
    <div class="stat-value">{{ transportLabel }}</div>
    <div class="stat-label">交通方式</div>
  </div>
</div>
```

- [ ] **Step 4: 添加 Hero 和统计区域样式**

```vue
<style scoped>
/* Hero 区域 - 红色背景 */
.result-hero {
  background: var(--primary-red);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-12) var(--space-6);
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.hero-content {
  max-width: 1200px;
  width: 100%;
  text-align: center;
}

.hero-title {
  color: var(--white);
  font-size: var(--text-6xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-6);
  text-shadow: 4px 4px 0px rgba(0, 0, 0, 0.2);
}

.hero-actions {
  display: flex;
  gap: var(--space-4);
  justify-content: center;
  flex-wrap: wrap;
}

.hero-btn {
  background: transparent;
  color: var(--white);
  border: var(--border-main) solid var(--white);
  padding: 12px 32px;
  font-family: var(--font-family);
  font-weight: var(--font-black);
  font-size: var(--text-base);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 4px 4px 0px 0px var(--white);
}

.hero-btn:hover {
  background: var(--white);
  color: var(--primary-red);
}

.hero-btn:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

/* 统计数据区 - 黄色背景 */
.stats-section {
  background: var(--primary-yellow);
  border-bottom: var(--border-main) solid var(--border);
  display: flex;
  height: 80px;
  align-items: center;
  justify-content: center;
}

.stat-item {
  flex: 1;
  text-align: center;
  padding: var(--space-4);
}

.stat-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-black);
  color: var(--foreground);
  margin-bottom: var(--space-1);
}

.stat-label {
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  color: var(--foreground);
  text-transform: uppercase;
}

.stat-divider {
  width: var(--border-main);
  height: 60%;
  background: var(--border);
}

/* 移动端适配 */
@media (max-width: 640px) {
  .result-hero {
    min-height: 150px;
    padding: var(--space-8) var(--space-4);
  }
  
  .hero-title {
    font-size: var(--text-3xl);
  }
  
  .hero-btn {
    padding: 10px 24px;
    font-size: var(--text-sm);
  }
  
  .stats-section {
    flex-wrap: wrap;
    height: auto;
  }
  
  .stat-item {
    flex: 0 0 50%;
    border-bottom: var(--border-2) solid var(--border);
  }
  
  .stat-divider {
    display: none;
  }
}
</style>
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/Result.vue
git commit -m "feat(bauhaus): 改造 Result 页面 Hero 和统计区域

- 红色 Hero 区域（行程标题 + 操作按钮）
- 黄色统计数据区（天数、景点数、预算、交通）
- 白色边框按钮
- 移动端适配"
```

---

### Task 2: 改造 Tab 导航

**Files:**
- Modify: `frontend/src/views/Result.vue`

- [ ] **Step 1: 修改 Tab 导航样式**

找到 Tab 导航部分，应用包豪斯样式：

```vue
<style scoped>
/* Tab 导航 */
.result-tabs {
  background: var(--white);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-4) var(--space-6);
}

:deep(.ant-tabs-nav) {
  margin-bottom: 0 !important;
}

:deep(.ant-tabs-tab) {
  background: var(--white) !important;
  border: var(--border-main) solid var(--border) !important;
  border-radius: 0 !important;
  margin-right: var(--space-2) !important;
  padding: 12px 24px !important;
  font-weight: var(--font-black) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
  box-shadow: 3px 3px 0px 0px var(--border) !important;
  transition: all var(--transition-fast) !important;
}

:deep(.ant-tabs-tab:hover) {
  background: var(--primary-yellow) !important;
  transform: translate(-1px, -1px);
  box-shadow: 4px 4px 0px 0px var(--border) !important;
}

:deep(.ant-tabs-tab-active) {
  background: var(--primary-blue) !important;
  color: var(--white) !important;
}

:deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--white) !important;
}

:deep(.ant-tabs-ink-bar) {
  display: none !important;
}

/* 移动端 Tab 导航 */
@media (max-width: 640px) {
  .result-tabs {
    padding: var(--space-3) var(--space-4);
    overflow-x: auto;
  }
  
  :deep(.ant-tabs-tab) {
    padding: 10px 16px !important;
    font-size: var(--text-sm) !important;
  }
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/Result.vue
git commit -m "feat(bauhaus): 改造 Result 页面 Tab 导航

- 包豪斯按钮样式（粗边框、硬阴影、方形）
- 激活状态使用蓝色背景
- 悬停效果（黄色背景）
- 移动端可横向滚动"
```

---

### Task 3: 改造内容区卡片样式

**Files:**
- Modify: `frontend/src/views/Result.vue`

- [ ] **Step 1: 添加内容区基础样式**

```vue
<style scoped>
/* 内容区 */
.result-content {
  background: var(--background);
  padding: var(--space-8) var(--space-6);
  min-height: calc(100vh - 200px - 80px - 64px);
}

.content-container {
  max-width: 1200px;
  margin: 0 auto;
}

/* 所有卡片统一样式 */
:deep(.ant-card) {
  background: var(--white) !important;
  border: var(--border-main) solid var(--border) !important;
  border-radius: 0 !important;
  box-shadow: var(--shadow-main) !important;
  margin-bottom: var(--space-6) !important;
}

:deep(.ant-card-head) {
  border-bottom: var(--border-main) solid var(--border) !important;
  background: transparent !important;
}

:deep(.ant-card-head-title) {
  font-weight: var(--font-black) !important;
  text-transform: uppercase !important;
  font-size: var(--text-xl) !important;
}

/* 景点卡片装饰 */
.attraction-card {
  position: relative;
}

.attraction-card::after {
  content: '';
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
  border-radius: var(--radius-full);
}

.attraction-card:nth-child(3n+1)::after {
  background: var(--primary-red);
}

.attraction-card:nth-child(3n+2)::after {
  background: var(--primary-blue);
}

.attraction-card:nth-child(3n+3)::after {
  background: var(--primary-yellow);
}

/* 移动端内容区 */
@media (max-width: 640px) {
  .result-content {
    padding: var(--space-4);
  }
  
  :deep(.ant-card) {
    margin-bottom: var(--space-4) !important;
  }
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/Result.vue
git commit -m "feat(bauhaus): 改造 Result 页面内容区卡片

- 所有卡片使用粗边框和硬阴影
- 景点卡片带彩色装饰（红/蓝/黄循环）
- 统一卡片标题样式（全大写、粗体）
- 移动端适配"
```

---

## 验证清单

完成所有任务后，进行以下验证：

- [ ] **启动开发服务器并测试**
  ```bash
  cd frontend && npm run dev
  ```

- [ ] **在浏览器中验证**
  - 从首页提交表单，进入结果页
  - 检查红色 Hero 区域
  - 检查黄色统计数据区
  - 检查 Tab 导航样式
  - 检查内容区卡片样式
  - 测试移动端响应式

- [ ] **所有更改已提交**
  ```bash
  git status
  ```

---

## 下一步

阶段 4A 完成后，可以继续：
- **阶段 4B：发现页改造** - DiscoverView.vue
- **阶段 4C：我的行程页改造** - MyTrips.vue

# 包豪斯风格重新设计 - 阶段 1：基础设施

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立包豪斯设计系统的基础设施，包括设计 token、基础样式和 Ant Design 覆盖

**Architecture:** 创建独立的 CSS 文件定义设计 token 和全局样式，通过 CSS 变量实现主题系统，使用深度选择器覆盖 Ant Design 组件样式

**Tech Stack:** CSS3 (CSS Variables), Vue 3, Ant Design Vue

**Design Spec:** `docs/superpowers/specs/2026-05-25-bauhaus-redesign.md`

---

### Task 1: 创建设计 Token 文件

**Files:**
- Create: `frontend/src/styles/bauhaus-tokens.css`

- [ ] **Step 1: 创建 bauhaus-tokens.css 文件并定义颜色系统**

```css
/* frontend/src/styles/bauhaus-tokens.css */

/* ============================================
   包豪斯设计系统 - Design Tokens
   ============================================ */

:root {
  /* ========== 颜色系统 ========== */
  
  /* 包豪斯三原色 */
  --primary-red: #D02020;
  --primary-blue: #1040C0;
  --primary-yellow: #F0C020;
  
  /* 基础色 */
  --background: #F0F0F0;
  --foreground: #121212;
  --border: #121212;
  --muted: #E0E0E0;
  --white: #FFFFFF;
}
```

- [ ] **Step 2: 添加排版系统 token**

```css
  /* ========== 排版系统 ========== */
  
  /* 字体家族 */
  --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC",
    sans-serif;
  
  /* 字体大小 */
  --text-xs: 11px;
  --text-sm: 12px;
  --text-base: 14px;
  --text-md: 15px;
  --text-lg: 16px;
  --text-xl: 18px;
  --text-2xl: 20px;
  --text-3xl: 24px;
  --text-4xl: 32px;
  --text-5xl: 40px;
  --text-6xl: 48px;
  --text-7xl: 56px;
  --text-8xl: 72px;
  
  /* 字重 */
  --font-normal: 400;
  --font-medium: 500;
  --font-bold: 700;
  --font-black: 900;
  
  /* 行高 */
  --leading-tight: 1.1;
  --leading-normal: 1.5;
  --leading-relaxed: 1.7;
```

- [ ] **Step 3: 添加边框、圆角和阴影 token**

```css
  /* ========== 边框与圆角 ========== */
  
  /* 圆角 */
  --radius-none: 0px;
  --radius-full: 9999px;
  
  /* 边框宽度 */
  --border-1: 1px;
  --border-2: 2px;
  --border-3: 3px;
  --border-4: 4px;
  
  /* ========== 阴影系统 ========== */
  
  /* 硬偏移阴影（无模糊） */
  --shadow-sm: 3px 3px 0px 0px var(--border);
  --shadow-md: 4px 4px 0px 0px var(--border);
  --shadow-lg: 6px 6px 0px 0px var(--border);
  --shadow-xl: 8px 8px 0px 0px var(--border);
```

- [ ] **Step 4: 添加间距和过渡 token**

```css
  /* ========== 间距系统 ========== */
  
  --space-0: 0px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;
  
  /* ========== 过渡动画 ========== */
  
  --transition-fast: 0.15s ease-out;
  --transition-normal: 0.2s ease-out;
  --transition-slow: 0.3s ease-out;
  
  /* ========== Z-index ========== */
  
  --z-base: 0;
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-modal: 300;
  --z-tooltip: 400;
}
```

- [ ] **Step 5: 添加移动端响应式 token**

```css
/* ========== 响应式断点 ========== */

@media (max-width: 640px) {
  :root {
    /* 移动端调整 */
    --text-4xl: 32px;
    --text-6xl: 40px;
    --text-8xl: 48px;
    
    --border-main: var(--border-2);
    --shadow-main: var(--shadow-md);
  }
}

@media (min-width: 641px) and (max-width: 1024px) {
  :root {
    /* 平板调整 */
    --text-4xl: 36px;
    --text-6xl: 48px;
    --text-8xl: 60px;
    
    --border-main: var(--border-3);
    --shadow-main: var(--shadow-lg);
  }
}

@media (min-width: 1025px) {
  :root {
    /* 桌面端 */
    --border-main: var(--border-4);
    --shadow-main: var(--shadow-xl);
  }
}
```

- [ ] **Step 6: 验证文件创建成功**

Run: `ls -la frontend/src/styles/bauhaus-tokens.css`
Expected: 文件存在且大小 > 0

- [ ] **Step 7: 提交**

```bash
git add frontend/src/styles/bauhaus-tokens.css
git commit -m "feat(bauhaus): 添加设计 token 系统

- 定义包豪斯三原色（红/蓝/黄）
- 定义排版系统（字体、字号、字重、行高）
- 定义边框、圆角和硬阴影
- 定义间距和过渡动画
- 添加响应式断点调整"
```

### Task 2: 创建基础组件样式文件

**Files:**
- Create: `frontend/src/styles/bauhaus-components.css`

- [ ] **Step 1: 创建文件并添加按钮基础样式**

```css
/* frontend/src/styles/bauhaus-components.css */

/* ============================================
   包豪斯组件样式
   ============================================ */

/* ========== 按钮样式 ========== */

.bauhaus-btn {
  padding: 12px 32px;
  border: var(--border-main) solid var(--border);
  font-family: var(--font-family);
  font-weight: var(--font-black);
  font-size: var(--text-base);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all var(--transition-normal);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}

.bauhaus-btn:hover {
  opacity: 0.9;
}

.bauhaus-btn:active {
  transform: translate(2px, 2px);
  box-shadow: none;
  transition: all 0.1s ease-out;
}

.bauhaus-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

- [ ] **Step 2: 添加按钮颜色变体**

```css
/* 按钮颜色变体 */

.bauhaus-btn-primary {
  background: var(--primary-red);
  color: var(--white);
  box-shadow: var(--shadow-md);
}

.bauhaus-btn-secondary {
  background: var(--primary-blue);
  color: var(--white);
  box-shadow: var(--shadow-md);
}

.bauhaus-btn-yellow {
  background: var(--primary-yellow);
  color: var(--foreground);
  box-shadow: var(--shadow-md);
}

.bauhaus-btn-outline {
  background: var(--white);
  color: var(--foreground);
  box-shadow: var(--shadow-md);
}
```

- [ ] **Step 3: 添加按钮形状变体**

```css
/* 按钮形状变体 */

.bauhaus-btn-square {
  border-radius: var(--radius-none);
}

.bauhaus-btn-pill {
  border-radius: var(--radius-full);
}
```

- [ ] **Step 4: 添加卡片样式**

```css
/* ========== 卡片样式 ========== */

.bauhaus-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-6);
  position: relative;
  transition: transform var(--transition-normal);
}

.bauhaus-card:hover {
  transform: translateY(-2px);
}

/* 卡片几何装饰 */
.bauhaus-card::after {
  content: '';
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
}

.bauhaus-card.decoration-circle::after {
  border-radius: var(--radius-full);
}

.bauhaus-card.decoration-square::after {
  border-radius: var(--radius-none);
}

.bauhaus-card.decoration-red::after {
  background: var(--primary-red);
}

.bauhaus-card.decoration-blue::after {
  background: var(--primary-blue);
}

.bauhaus-card.decoration-yellow::after {
  background: var(--primary-yellow);
}
```

- [ ] **Step 5: 添加输入框样式**

```css
/* ========== 输入框样式 ========== */

.bauhaus-input {
  width: 100%;
  padding: 12px 16px;
  border: var(--border-main) solid var(--border);
  border-radius: var(--radius-none);
  background: var(--white);
  font-family: var(--font-family);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  transition: all var(--transition-fast);
}

.bauhaus-input:hover {
  border-color: var(--primary-blue);
}

.bauhaus-input:focus {
  outline: none;
  border-color: var(--primary-blue);
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1);
}

.bauhaus-input::placeholder {
  color: var(--muted);
}

/* 文本域 */
.bauhaus-textarea {
  width: 100%;
  padding: 12px 16px;
  border: var(--border-main) solid var(--border);
  border-radius: var(--radius-none);
  background: var(--white);
  font-family: var(--font-family);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  transition: all var(--transition-fast);
  resize: vertical;
  min-height: 100px;
}

.bauhaus-textarea:hover {
  border-color: var(--primary-blue);
}

.bauhaus-textarea:focus {
  outline: none;
  border-color: var(--primary-blue);
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1);
}
```

- [ ] **Step 6: 添加移动端响应式调整**

```css
/* ========== 移动端响应式 ========== */

@media (max-width: 640px) {
  .bauhaus-btn {
    padding: 10px 24px;
    font-size: var(--text-sm);
  }
  
  .bauhaus-card {
    padding: var(--space-4);
  }
  
  .bauhaus-input,
  .bauhaus-textarea {
    padding: 10px 14px;
  }
}
```

- [ ] **Step 7: 验证文件创建成功**

Run: `ls -la frontend/src/styles/bauhaus-components.css`
Expected: 文件存在且大小 > 0

- [ ] **Step 8: 提交**

```bash
git add frontend/src/styles/bauhaus-components.css
git commit -m "feat(bauhaus): 添加基础组件样式

- 添加按钮样式（颜色变体、形状变体）
- 添加卡片样式（带几何装饰）
- 添加输入框和文本域样式
- 添加移动端响应式调整"
```

### Task 3: 创建 Ant Design 覆盖样式

**Files:**
- Create: `frontend/src/styles/bauhaus-antd-override.css`

- [ ] **Step 1: 创建文件并添加全局 Ant Design 覆盖**

```css
/* frontend/src/styles/bauhaus-antd-override.css */

/* ============================================
   Ant Design 组件包豪斯风格覆盖
   ============================================ */

/* ========== 全局覆盖 ========== */

.ant-btn {
  border-radius: var(--radius-none) !important;
  font-weight: var(--font-black) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
}

.ant-btn-primary {
  background: var(--primary-red) !important;
  border-color: var(--border) !important;
  border-width: var(--border-main) !important;
  box-shadow: var(--shadow-md) !important;
}

.ant-btn-primary:hover {
  background: var(--primary-red) !important;
  opacity: 0.9;
}

.ant-btn-primary:active {
  transform: translate(2px, 2px);
  box-shadow: none !important;
}
```

- [ ] **Step 2: 添加 DatePicker 覆盖**

```css
/* ========== DatePicker 覆盖 ========== */

.ant-picker {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  box-shadow: none !important;
  font-family: var(--font-family) !important;
}

.ant-picker:hover {
  border-color: var(--primary-blue) !important;
}

.ant-picker-focused {
  border-color: var(--primary-blue) !important;
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1) !important;
}

.ant-picker-dropdown {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  box-shadow: var(--shadow-main) !important;
}

.ant-picker-cell-in-view.ant-picker-cell-selected .ant-picker-cell-inner {
  background: var(--primary-blue) !important;
  border-radius: var(--radius-none) !important;
}

.ant-picker-cell-in-view.ant-picker-cell-today .ant-picker-cell-inner::before {
  border: 2px solid var(--primary-yellow) !important;
  border-radius: var(--radius-none) !important;
}
```

- [ ] **Step 3: 添加 Select 覆盖**

```css
/* ========== Select 覆盖 ========== */

.ant-select-selector {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  box-shadow: none !important;
  font-family: var(--font-family) !important;
}

.ant-select:hover .ant-select-selector {
  border-color: var(--primary-blue) !important;
}

.ant-select-focused .ant-select-selector {
  border-color: var(--primary-blue) !important;
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1) !important;
}

.ant-select-dropdown {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  box-shadow: var(--shadow-main) !important;
}

.ant-select-item-option-selected {
  background: var(--primary-blue) !important;
  color: var(--white) !important;
  font-weight: var(--font-bold) !important;
}

.ant-select-item-option-active {
  background: rgba(16, 64, 192, 0.1) !important;
}
```

- [ ] **Step 4: 添加 Checkbox 覆盖**

```css
/* ========== Checkbox 覆盖 ========== */

.ant-checkbox-wrapper {
  font-family: var(--font-family) !important;
  font-weight: var(--font-medium) !important;
}

.ant-checkbox-inner {
  border: var(--border-2) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  width: 20px !important;
  height: 20px !important;
}

.ant-checkbox-checked .ant-checkbox-inner {
  background: var(--primary-blue) !important;
  border-color: var(--border) !important;
}

.ant-checkbox-checked::after {
  border: var(--border-2) solid var(--primary-blue) !important;
  border-radius: var(--radius-none) !important;
}
```

- [ ] **Step 5: 添加 Input 覆盖**

```css
/* ========== Input 覆盖 ========== */

.ant-input {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  font-family: var(--font-family) !important;
  font-weight: var(--font-medium) !important;
}

.ant-input:hover {
  border-color: var(--primary-blue) !important;
}

.ant-input:focus {
  border-color: var(--primary-blue) !important;
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1) !important;
}

.ant-input-number {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
}

.ant-input-number:hover {
  border-color: var(--primary-blue) !important;
}

.ant-input-number-focused {
  border-color: var(--primary-blue) !important;
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1) !important;
}
```

- [ ] **Step 6: 添加 Progress 覆盖**

```css
/* ========== Progress 覆盖 ========== */

.ant-progress-bg {
  background: var(--primary-blue) !important;
  border-radius: var(--radius-none) !important;
}

.ant-progress-inner {
  background: var(--muted) !important;
  border-radius: var(--radius-none) !important;
  border: var(--border-2) solid var(--border) !important;
}
```

- [ ] **Step 7: 添加 Card 覆盖**

```css
/* ========== Card 覆盖 ========== */

.ant-card {
  border: var(--border-main) solid var(--border) !important;
  border-radius: var(--radius-none) !important;
  box-shadow: var(--shadow-main) !important;
}

.ant-card-head {
  border-bottom: var(--border-main) solid var(--border) !important;
  font-weight: var(--font-black) !important;
  text-transform: uppercase !important;
}
```

- [ ] **Step 8: 添加移动端响应式调整**

```css
/* ========== 移动端响应式 ========== */

@media (max-width: 640px) {
  .ant-picker,
  .ant-select-selector,
  .ant-input,
  .ant-input-number,
  .ant-card {
    border-width: var(--border-2) !important;
  }
  
  .ant-picker-dropdown,
  .ant-select-dropdown {
    border-width: var(--border-3) !important;
    box-shadow: var(--shadow-lg) !important;
  }
}
```

- [ ] **Step 9: 验证文件创建成功**

Run: `ls -la frontend/src/styles/bauhaus-antd-override.css`
Expected: 文件存在且大小 > 0

- [ ] **Step 10: 提交**

```bash
git add frontend/src/styles/bauhaus-antd-override.css
git commit -m "feat(bauhaus): 添加 Ant Design 组件覆盖样式

- 覆盖 Button、DatePicker、Select 样式
- 覆盖 Checkbox、Input、InputNumber 样式
- 覆盖 Progress、Card 样式
- 所有组件使用包豪斯风格（粗边框、硬阴影、方形）
- 添加移动端响应式调整"
```

## 文件结构

**新建文件：**
- `frontend/src/styles/bauhaus-tokens.css` - 设计 token（颜色、字体、间距等）
- `frontend/src/styles/bauhaus-components.css` - 基础组件样式类
- `frontend/src/styles/bauhaus-antd-override.css` - Ant Design 组件覆盖
- `frontend/src/styles/bauhaus-utilities.css` - 工具类

**修改文件：**
- `frontend/src/main.ts` - 引入新的样式文件
- `frontend/src/App.vue` - 移除旧的紫色渐变样式

---


### Task 4: 创建工具类样式

**Files:**
- Create: `frontend/src/styles/bauhaus-utilities.css`

- [ ] **Step 1: 创建文件并添加排版工具类**

```css
/* frontend/src/styles/bauhaus-utilities.css */

/* ============================================
   包豪斯工具类
   ============================================ */

/* ========== 排版工具类 ========== */

.bauhaus-title {
  font-family: var(--font-family);
  font-weight: var(--font-black);
  line-height: var(--leading-tight);
  text-transform: uppercase;
  letter-spacing: -0.02em;
}

.bauhaus-title-xl {
  font-size: var(--text-8xl);
}

.bauhaus-title-lg {
  font-size: var(--text-6xl);
}

.bauhaus-title-md {
  font-size: var(--text-4xl);
}

.bauhaus-title-sm {
  font-size: var(--text-2xl);
}

.bauhaus-text {
  font-family: var(--font-family);
  line-height: var(--leading-normal);
}
```

- [ ] **Step 2: 添加布局工具类**

```css
/* ========== 布局工具类 ========== */

.bauhaus-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--space-4);
}

.bauhaus-section {
  padding: var(--space-16) 0;
}

.bauhaus-grid {
  display: grid;
  gap: var(--space-6);
}

.bauhaus-grid-2 {
  grid-template-columns: repeat(2, 1fr);
}

.bauhaus-grid-3 {
  grid-template-columns: repeat(3, 1fr);
}

.bauhaus-flex {
  display: flex;
  gap: var(--space-4);
}

.bauhaus-flex-center {
  display: flex;
  align-items: center;
  justify-content: center;
}

.bauhaus-flex-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
```

- [ ] **Step 3: 添加背景色和边框工具类**

```css
/* ========== 背景色工具类 ========== */

.bg-red {
  background: var(--primary-red);
  color: var(--white);
}

.bg-blue {
  background: var(--primary-blue);
  color: var(--white);
}

.bg-yellow {
  background: var(--primary-yellow);
  color: var(--foreground);
}

.bg-white {
  background: var(--white);
  color: var(--foreground);
}

/* ========== 边框工具类 ========== */

.border-main {
  border: var(--border-main) solid var(--border);
}

.border-top {
  border-top: var(--border-main) solid var(--border);
}

.border-bottom {
  border-bottom: var(--border-main) solid var(--border);
}

.shadow-main {
  box-shadow: var(--shadow-main);
}
```

- [ ] **Step 4: 添加几何装饰工具类**

```css
/* ========== 几何装饰工具类 ========== */

.geometric-circle {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  border: var(--border-3) solid var(--border);
}

.geometric-square {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-none);
  border: var(--border-3) solid var(--border);
}
```

- [ ] **Step 5: 添加移动端响应式**

```css
/* ========== 移动端响应式 ========== */

@media (max-width: 640px) {
  .bauhaus-grid-2,
  .bauhaus-grid-3 {
    grid-template-columns: 1fr;
  }
  
  .bauhaus-title-xl {
    font-size: var(--text-4xl);
  }
  
  .hide-mobile {
    display: none;
  }
}
```

- [ ] **Step 6: 验证并提交**

Run: `ls -la frontend/src/styles/bauhaus-utilities.css`
Expected: 文件存在

```bash
git add frontend/src/styles/bauhaus-utilities.css
git commit -m "feat(bauhaus): 添加工具类样式"
```


### Task 5: 在 main.ts 中引入样式文件

**Files:**
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: 读取当前 main.ts 文件**

Run: `cat frontend/src/main.ts`
Expected: 看到当前的导入语句

- [ ] **Step 2: 在 main.ts 中添加包豪斯样式导入**

在现有的样式导入之后，添加以下导入语句：

```typescript
// 包豪斯设计系统样式
import './styles/bauhaus-tokens.css'
import './styles/bauhaus-components.css'
import './styles/bauhaus-antd-override.css'
import './styles/bauhaus-utilities.css'
```

- [ ] **Step 3: 验证导入顺序正确**

确保导入顺序为：
1. bauhaus-tokens.css（最先，定义变量）
2. bauhaus-components.css
3. bauhaus-antd-override.css
4. bauhaus-utilities.css（最后，工具类优先级最高）

- [ ] **Step 4: 启动开发服务器测试**

Run: `cd frontend && npm run dev`
Expected: 服务器正常启动，无 CSS 错误

- [ ] **Step 5: 在浏览器中验证样式加载**

打开浏览器开发者工具 → Network → 筛选 CSS
Expected: 看到 4 个包豪斯 CSS 文件加载成功

- [ ] **Step 6: 提交**

```bash
git add frontend/src/main.ts
git commit -m "feat(bauhaus): 在 main.ts 中引入包豪斯样式系统

- 引入 bauhaus-tokens.css
- 引入 bauhaus-components.css
- 引入 bauhaus-antd-override.css
- 引入 bauhaus-utilities.css"
```

### Task 6: 更新 App.vue 移除旧样式

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 读取当前 App.vue 文件**

Run: `cat frontend/src/App.vue`
Expected: 看到当前的样式定义

- [ ] **Step 2: 移除旧的紫色渐变样式**

在 `<style>` 标签中，移除或注释掉任何紫色渐变相关的样式，例如：
- `background: linear-gradient(...)`
- 任何包含紫色的颜色定义

- [ ] **Step 3: 添加包豪斯全局样式**

在 `<style>` 标签中添加：

```css
/* 全局包豪斯样式 */
body {
  font-family: var(--font-family);
  color: var(--foreground);
  background: var(--background);
  margin: 0;
  padding: 0;
}

* {
  box-sizing: border-box;
}

#app {
  min-height: 100vh;
}
```

- [ ] **Step 4: 验证样式应用**

Run: `cd frontend && npm run dev`
打开浏览器，检查：
- 背景色是否变为灰白色 (#F0F0F0)
- 字体是否使用系统字体
- 紫色渐变是否已移除

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.vue
git commit -m "feat(bauhaus): 更新 App.vue 应用包豪斯全局样式

- 移除旧的紫色渐变背景
- 应用包豪斯设计 token
- 设置全局字体和背景色"
```

---

## 验证清单

完成所有任务后，进行以下验证：

- [ ] **所有 CSS 文件已创建**
  ```bash
  ls -la frontend/src/styles/bauhaus-*.css
  ```
  Expected: 看到 4 个文件

- [ ] **样式文件已在 main.ts 中引入**
  ```bash
  grep "bauhaus" frontend/src/main.ts
  ```
  Expected: 看到 4 行导入语句

- [ ] **开发服务器正常运行**
  ```bash
  cd frontend && npm run dev
  ```
  Expected: 无错误，服务器在 5173 端口运行

- [ ] **浏览器中样式正常加载**
  - 打开 http://localhost:5173
  - 检查开发者工具 → Network → CSS
  - Expected: 4 个包豪斯 CSS 文件状态为 200

- [ ] **CSS 变量可用**
  - 打开浏览器开发者工具 → Elements → :root
  - Expected: 看到所有 CSS 变量（--primary-red, --primary-blue 等）

- [ ] **Ant Design 组件样式已覆盖**
  - 在页面中找到任何 Ant Design 组件（按钮、输入框等）
  - Expected: 组件有粗黑边框和方形样式

- [ ] **所有更改已提交**
  ```bash
  git status
  ```
  Expected: working tree clean

---

## 下一步

阶段 1 完成后，可以继续：
- **阶段 2：核心组件** - 创建 BauhausButton、BauhausCard 等 Vue 组件
- **阶段 3：首页重构** - 重写 Home.vue 应用包豪斯风格
- **阶段 4：其他页面改造** - 改造 DiscoverView、Result、MyTrips
- **阶段 5：细节优化** - 优化动画、性能和可访问性


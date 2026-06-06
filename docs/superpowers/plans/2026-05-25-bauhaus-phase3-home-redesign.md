# 包豪斯风格重新设计 - 阶段 3：首页重构

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完全重写 Home.vue，应用包豪斯风格设计

**Architecture:** 整页蓝色背景 + 浮动色块表单卡片，使用阶段 2 创建的包豪斯组件

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue (已覆盖样式), 包豪斯组件

**Design Spec:** `docs/superpowers/specs/2026-05-25-bauhaus-redesign.md` - 4.1 首页

**依赖：** 阶段 1（基础设施）+ 阶段 2（核心组件）已完成

---

## 设计要求总结

**整体布局：**
- 整页蓝色背景 (#1040C0)
- 顶部：超大标题"智能旅行助手"（白色，72px，font-weight: 900）
- 副标题和热门城市快选（白色文字）
- 几何装饰：黄色圆形、红色方形点缀

**表单卡片（4 个）：**
1. **黄色卡片** - 目的地与日期
2. **白色卡片** - 偏好设置
3. **红色卡片** - 预算与同伴
4. **白色卡片** - 额外要求

**提交按钮：**
- 黄色背景 + 黑色文字 + 4px 黑边框 + 硬阴影
- 文字：🚀 开始探索景点

---

### Task 1: 重写 Home.vue - 整体结构和样式

**Files:**
- Modify: `frontend/src/views/Home.vue`

- [ ] **Step 1: 备份原文件**

```bash
cp frontend/src/views/Home.vue frontend/src/views/Home.vue.backup
```

- [ ] **Step 2: 重写 template - 顶部 Hero 区域**

```vue
<template>
  <div class="bauhaus-home">
    <!-- 蓝色背景 Hero 区域 -->
    <div class="hero-section">
      <!-- 几何装饰 -->
      <GeometricDecoration
        shape="circle"
        color="yellow"
        :size="80"
        class="decoration decoration-1"
      />
      <GeometricDecoration
        shape="square"
        color="red"
        :size="60"
        class="decoration decoration-2"
      />
      <GeometricDecoration
        shape="circle"
        color="yellow"
        :size="40"
        class="decoration decoration-3"
      />
      
      <!-- Hero 内容 -->
      <div class="hero-content">
        <h1 class="bauhaus-title bauhaus-title-xl hero-title">
          智能旅行助手
        </h1>
        <p class="hero-subtitle">
          基于 AI 的个性化旅行规划，让每一次出行都完美无忧
        </p>
        
        <!-- 热门城市快选 -->
        <div class="hot-cities">
          <span class="hot-label">🔥 热门目的地</span>
          <div class="city-pills">
            <button
              v-for="city in hotCities"
              :key="city.name"
              class="city-pill"
              :class="{ active: formData.city === city.name }"
              @click="selectCity(city.name)"
            >
              {{ city.emoji }} {{ city.name }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 表单区域 -->
    <div class="form-section">
      <a-form
        :model="formData"
        layout="vertical"
        @finish="handleSubmit"
      >
        <!-- 4 个表单卡片将在后续步骤添加 -->
      </a-form>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 添加 script setup**

保留原有的逻辑，只需导入包豪斯组件：

```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs, { Dayjs } from 'dayjs'
import GeometricDecoration from '@/components/bauhaus/GeometricDecoration.vue'

// 保留原有的所有逻辑代码
// ...
</script>
```

- [ ] **Step 4: 添加样式 - 蓝色背景和 Hero 区域**

```vue
<style scoped>
.bauhaus-home {
  min-height: 100vh;
  background: var(--primary-blue);
  padding: var(--space-8) var(--space-4);
}

/* Hero 区域 */
.hero-section {
  position: relative;
  max-width: 1200px;
  margin: 0 auto var(--space-16);
  text-align: center;
}

/* 几何装饰定位 */
.decoration {
  position: absolute;
  z-index: 1;
}

.decoration-1 {
  top: -40px;
  left: 10%;
}

.decoration-2 {
  top: 100px;
  right: 15%;
}

.decoration-3 {
  bottom: -20px;
  left: 20%;
}

/* Hero 内容 */
.hero-content {
  position: relative;
  z-index: 2;
}

.hero-title {
  color: var(--white);
  margin-bottom: var(--space-4);
  text-shadow: 4px 4px 0px rgba(0, 0, 0, 0.2);
}

.hero-subtitle {
  color: var(--white);
  font-size: var(--text-xl);
  font-weight: var(--font-medium);
  margin-bottom: var(--space-8);
  opacity: 0.95;
}

/* 热门城市 */
.hot-cities {
  display: inline-block;
  background: rgba(255, 255, 255, 0.1);
  border: var(--border-main) solid var(--white);
  padding: var(--space-4);
  backdrop-filter: blur(10px);
}

.hot-label {
  color: var(--white);
  font-weight: var(--font-bold);
  font-size: var(--text-base);
  display: block;
  margin-bottom: var(--space-3);
}

.city-pills {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.city-pill {
  background: var(--white);
  color: var(--foreground);
  border: var(--border-2) solid var(--foreground);
  padding: 8px 16px;
  font-weight: var(--font-bold);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.city-pill:hover {
  background: var(--primary-yellow);
  transform: translateY(-2px);
}

.city-pill.active {
  background: var(--primary-yellow);
  box-shadow: var(--shadow-md);
}

/* 表单区域 */
.form-section {
  max-width: 900px;
  margin: 0 auto;
}

/* 移动端适配 */
@media (max-width: 640px) {
  .bauhaus-home {
    padding: var(--space-4) var(--space-2);
  }
  
  .hero-title {
    font-size: var(--text-4xl) !important;
  }
  
  .hero-subtitle {
    font-size: var(--text-base);
  }
  
  .decoration {
    display: none;
  }
  
  .city-pills {
    justify-content: center;
  }
}
</style>
```

- [ ] **Step 5: 验证并提交**

```bash
git add frontend/src/views/Home.vue
git commit -m "feat(bauhaus): 重写 Home.vue - Hero 区域

- 整页蓝色背景
- 超大标题（白色，72px）
- 几何装饰（黄色圆形、红色方形）
- 热门城市快选
- 移动端适配"
```

---

### Task 2: 添加表单卡片 1 - 目的地与日期（黄色）

**Files:**
- Modify: `frontend/src/views/Home.vue`

- [ ] **Step 1: 在 form 内添加卡片 1**

```vue
<!-- 卡片 1: 目的地与日期 - 黄色背景 -->
<div class="form-card card-yellow">
  <div class="card-decoration decoration-circle decoration-red"></div>
  <h3 class="card-title">📍 目的地与日期</h3>
  
  <a-row :gutter="16">
    <a-col :xs="24" :md="12">
      <a-form-item name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
        <template #label>
          <span class="form-label">目的地城市</span>
        </template>
        <a-input
          v-model:value="formData.city"
          placeholder="例如: 北京"
          size="large"
        />
      </a-form-item>
    </a-col>
    
    <a-col :xs="12" :md="6">
      <a-form-item name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
        <template #label>
          <span class="form-label">开始日期</span>
        </template>
        <a-date-picker
          v-model:value="formData.start_date"
          style="width: 100%"
          size="large"
        />
      </a-form-item>
    </a-col>
    
    <a-col :xs="12" :md="6">
      <a-form-item name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
        <template #label>
          <span class="form-label">结束日期</span>
        </template>
        <a-date-picker
          v-model:value="formData.end_date"
          style="width: 100%"
          size="large"
        />
      </a-form-item>
    </a-col>
  </a-row>
  
  <div class="days-display">
    <span class="days-label">旅行天数：</span>
    <span class="days-value">{{ formData.travel_days }}</span>
    <span class="days-unit">天</span>
  </div>
</div>
```

- [ ] **Step 2: 添加卡片样式**

```vue
<style scoped>
/* 表单卡片基础样式 */
.form-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-6);
  margin-bottom: var(--space-6);
  position: relative;
}

/* 黄色卡片 */
.card-yellow {
  background: var(--primary-yellow);
}

/* 红色卡片 */
.card-red {
  background: var(--primary-red);
}

.card-red .card-title,
.card-red .form-label {
  color: var(--white);
}

/* 卡片装饰 */
.card-decoration {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
}

.decoration-circle {
  border-radius: var(--radius-full);
}

.decoration-square {
  border-radius: var(--radius-none);
}

.decoration-red {
  background: var(--primary-red);
}

.decoration-blue {
  background: var(--primary-blue);
}

.decoration-yellow {
  background: var(--primary-yellow);
}

/* 卡片标题 */
.card-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-4);
  color: var(--foreground);
}

/* 表单标签 */
.form-label {
  font-weight: var(--font-bold);
  font-size: var(--text-base);
  color: var(--foreground);
}

/* 天数显示 */
.days-display {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  padding: var(--space-3);
  text-align: center;
  margin-top: var(--space-4);
}

.days-label {
  font-weight: var(--font-bold);
  margin-right: var(--space-2);
}

.days-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-black);
  color: var(--primary-blue);
  margin: 0 var(--space-1);
}

.days-unit {
  font-weight: var(--font-bold);
}

/* 移动端适配 */
@media (max-width: 640px) {
  .form-card {
    padding: var(--space-4);
    margin-bottom: var(--space-4);
  }
  
  .card-title {
    font-size: var(--text-lg);
  }
}
</style>
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/Home.vue
git commit -m "feat(bauhaus): 添加表单卡片 1 - 目的地与日期

- 黄色背景卡片
- 红色圆形装饰
- 城市、日期输入框
- 天数显示"
```

---

### Task 3: 添加表单卡片 2-4 和提交按钮

**Files:**
- Modify: `frontend/src/views/Home.vue`

- [ ] **Step 1: 添加卡片 2 - 偏好设置（白色）**

```vue
<!-- 卡片 2: 偏好设置 - 白色背景 -->
<div class="form-card">
  <div class="card-decoration decoration-square decoration-blue"></div>
  <h3 class="card-title">⚙️ 偏好设置</h3>
  
  <a-row :gutter="16">
    <a-col :xs="24" :md="12">
      <a-form-item name="transport_mode">
        <template #label>
          <span class="form-label">交通方式</span>
        </template>
        <a-select
          v-model:value="formData.transport_mode"
          size="large"
        >
          <a-select-option value="driving">🚗 自驾</a-select-option>
          <a-select-option value="transit">🚇 公共交通</a-select-option>
          <a-select-option value="walking">🚶 步行</a-select-option>
        </a-select>
      </a-form-item>
    </a-col>
    
    <a-col :xs="24" :md="12">
      <a-form-item name="accommodation_preference">
        <template #label>
          <span class="form-label">住宿偏好</span>
        </template>
        <a-select
          v-model:value="formData.accommodation_preference"
          size="large"
        >
          <a-select-option value="luxury">🏨 豪华酒店</a-select-option>
          <a-select-option value="comfort">🏩 舒适酒店</a-select-option>
          <a-select-option value="budget">🏠 经济型</a-select-option>
        </a-select>
      </a-form-item>
    </a-col>
  </a-row>
  
  <!-- 其他偏好字段... -->
</div>
```

- [ ] **Step 2: 添加卡片 3 - 预算与同伴（红色）**

```vue
<!-- 卡片 3: 预算与同伴 - 红色背景 -->
<div class="form-card card-red">
  <div class="card-decoration decoration-circle decoration-yellow"></div>
  <h3 class="card-title">💰 预算与同伴</h3>
  
  <a-row :gutter="16">
    <a-col :xs="24" :md="8">
      <a-form-item name="budget_max">
        <template #label>
          <span class="form-label">预算上限（元）</span>
        </template>
        <a-input-number
          v-model:value="formData.budget_max"
          :min="0"
          :step="100"
          style="width: 100%"
          size="large"
        />
      </a-form-item>
    </a-col>
    
    <a-col :xs="12" :md="8">
      <a-form-item name="num_people">
        <template #label>
          <span class="form-label">出行人数</span>
        </template>
        <a-input-number
          v-model:value="formData.num_people"
          :min="1"
          :max="20"
          style="width: 100%"
          size="large"
        />
      </a-form-item>
    </a-col>
    
    <a-col :xs="12" :md="8">
      <a-form-item name="companion_type">
        <template #label>
          <span class="form-label">同伴类型</span>
        </template>
        <a-select
          v-model:value="formData.companion_type"
          size="large"
        >
          <a-select-option value="solo">🧍 独自</a-select-option>
          <a-select-option value="couple">💑 情侣</a-select-option>
          <a-select-option value="family">👨‍👩‍👧‍👦 家庭</a-select-option>
          <a-select-option value="friends">👥 朋友</a-select-option>
        </a-select>
      </a-form-item>
    </a-col>
  </a-row>
</div>
```

- [ ] **Step 3: 添加卡片 4 - 额外要求（白色）**

```vue
<!-- 卡片 4: 额外要求 - 白色背景 -->
<div class="form-card">
  <div class="card-decoration decoration-square decoration-red"></div>
  <h3 class="card-title">💬 额外要求</h3>
  
  <a-form-item name="additional_requirements">
    <a-textarea
      v-model:value="formData.additional_requirements"
      placeholder="告诉我们您的特殊需求或偏好..."
      :rows="4"
      size="large"
    />
  </a-form-item>
</div>
```

- [ ] **Step 4: 添加提交按钮**

```vue
<!-- 提交按钮 -->
<div class="submit-section">
  <button
    type="submit"
    class="bauhaus-btn bauhaus-btn-yellow bauhaus-btn-square submit-btn"
    :disabled="loading"
  >
    <span v-if="!loading">🚀 开始探索景点</span>
    <span v-else>⏳ 规划中...</span>
  </button>
</div>
```

- [ ] **Step 5: 添加提交按钮样式**

```vue
<style scoped>
.submit-section {
  text-align: center;
  margin-top: var(--space-8);
}

.submit-btn {
  min-width: 300px;
  padding: 16px 48px;
  font-size: var(--text-lg);
}

@media (max-width: 640px) {
  .submit-btn {
    min-width: 100%;
  }
}
</style>
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/Home.vue
git commit -m "feat(bauhaus): 添加表单卡片 2-4 和提交按钮

- 卡片 2: 偏好设置（白色 + 蓝色方形装饰）
- 卡片 3: 预算与同伴（红色 + 黄色圆形装饰）
- 卡片 4: 额外要求（白色 + 红色方形装饰）
- 提交按钮（黄色 + 黑色文字）"
```

---

## 验证清单

完成所有任务后，进行以下验证：

- [ ] **启动开发服务器**
  ```bash
  cd frontend && npm run dev
  ```

- [ ] **在浏览器中验证**
  - 打开 http://localhost:5173
  - 检查整页蓝色背景
  - 检查超大白色标题
  - 检查几何装饰是否显示
  - 检查 4 个表单卡片颜色正确
  - 检查卡片装饰（右上角小圆形/方形）
  - 检查提交按钮样式
  - 测试移动端响应式

- [ ] **功能测试**
  - 选择热门城市
  - 填写表单
  - 提交表单
  - 验证表单验证规则

- [ ] **所有更改已提交**
  ```bash
  git status
  ```
  Expected: working tree clean

---

## 下一步

阶段 3 完成后，可以继续：
- **阶段 4：其他页面改造** - 改造 DiscoverView、Result、MyTrips
- **阶段 5：细节优化** - 优化动画、性能和可访问性

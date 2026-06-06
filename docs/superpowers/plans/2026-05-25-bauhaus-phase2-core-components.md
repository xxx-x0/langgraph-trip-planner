# 包豪斯风格重新设计 - 阶段 2：核心组件

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建包豪斯风格的 Vue 组件，供后续页面重构使用

**Architecture:** 创建独立的 Vue 组件封装包豪斯样式，使用 Composition API，支持 props 配置变体

**Tech Stack:** Vue 3 (Composition API), TypeScript

**Design Spec:** `docs/superpowers/specs/2026-05-25-bauhaus-redesign.md`

**依赖：** 阶段 1（基础设施）已完成

---

## 文件结构

**新建文件：**
- `frontend/src/components/bauhaus/BauhausButton.vue` - 按钮组件
- `frontend/src/components/bauhaus/BauhausCard.vue` - 卡片组件
- `frontend/src/components/bauhaus/BauhausInput.vue` - 输入框组件
- `frontend/src/components/bauhaus/GeometricDecoration.vue` - 几何装饰组件

---

### Task 1: 创建 BauhausButton 组件

**Files:**
- Create: `frontend/src/components/bauhaus/BauhausButton.vue`

- [ ] **Step 1: 创建组件文件并定义 props**

```vue
<script setup lang="ts">
interface Props {
  variant?: 'primary' | 'secondary' | 'yellow' | 'outline'
  shape?: 'square' | 'pill'
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  shape: 'square',
  disabled: false
})
</script>
```

- [ ] **Step 2: 添加模板**

```vue
<template>
  <button
    class="bauhaus-btn"
    :class="[
      `bauhaus-btn-${variant}`,
      `bauhaus-btn-${shape}`
    ]"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>
```

- [ ] **Step 3: 添加样式（使用已定义的 CSS 类）**

```vue
<style scoped>
/* 组件使用全局定义的 bauhaus-btn 样式类 */
/* 无需额外样式，所有样式已在 bauhaus-components.css 中定义 */
</style>
```

- [ ] **Step 4: 验证组件**

Run: `ls -la frontend/src/components/bauhaus/BauhausButton.vue`
Expected: 文件存在

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/bauhaus/BauhausButton.vue
git commit -m "feat(bauhaus): 添加 BauhausButton 组件

- 支持 4 种颜色变体（primary/secondary/yellow/outline）
- 支持 2 种形状变体（square/pill）
- 支持 disabled 状态"
```

---

### Task 2: 创建 BauhausCard 组件

**Files:**
- Create: `frontend/src/components/bauhaus/BauhausCard.vue`

- [ ] **Step 1: 创建组件文件并定义 props**

```vue
<script setup lang="ts">
interface Props {
  decoration?: 'circle' | 'square' | 'none'
  accentColor?: 'red' | 'blue' | 'yellow'
}

const props = withDefaults(defineProps<Props>(), {
  decoration: 'circle',
  accentColor: 'blue'
})
</script>
```

- [ ] **Step 2: 添加模板**

```vue
<template>
  <div
    class="bauhaus-card"
    :class="[
      decoration !== 'none' ? `decoration-${decoration}` : '',
      decoration !== 'none' ? `decoration-${accentColor}` : ''
    ]"
  >
    <slot />
  </div>
</template>
```

- [ ] **Step 3: 添加样式**

```vue
<style scoped>
/* 组件使用全局定义的 bauhaus-card 样式类 */
</style>
```

- [ ] **Step 4: 验证并提交**

```bash
git add frontend/src/components/bauhaus/BauhausCard.vue
git commit -m "feat(bauhaus): 添加 BauhausCard 组件

- 支持几何装饰（circle/square/none）
- 支持装饰颜色（red/blue/yellow）
- 带悬停效果"
```

---

### Task 3: 创建 BauhausInput 组件

**Files:**
- Create: `frontend/src/components/bauhaus/BauhausInput.vue`

- [ ] **Step 1: 创建组件文件并定义 props**

```vue
<script setup lang="ts">
interface Props {
  modelValue: string
  placeholder?: string
  disabled?: boolean
  type?: 'text' | 'number' | 'email'
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '',
  disabled: false,
  type: 'text'
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>
```

- [ ] **Step 2: 添加模板**

```vue
<template>
  <input
    class="bauhaus-input"
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="handleInput"
  />
</template>
```

- [ ] **Step 3: 添加样式**

```vue
<style scoped>
/* 组件使用全局定义的 bauhaus-input 样式类 */
</style>
```

- [ ] **Step 4: 验证并提交**

```bash
git add frontend/src/components/bauhaus/BauhausInput.vue
git commit -m "feat(bauhaus): 添加 BauhausInput 组件

- 支持 v-model 双向绑定
- 支持 type、placeholder、disabled 属性
- 带 hover 和 focus 状态"
```

---

### Task 4: 创建 GeometricDecoration 组件

**Files:**
- Create: `frontend/src/components/bauhaus/GeometricDecoration.vue`

- [ ] **Step 1: 创建组件文件并定义 props**

```vue
<script setup lang="ts">
interface Props {
  shape: 'circle' | 'square'
  color: 'red' | 'blue' | 'yellow'
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 40
})
</script>
```

- [ ] **Step 2: 添加模板**

```vue
<template>
  <div
    :class="`geometric-${shape}`"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      background: `var(--primary-${color})`
    }"
  />
</template>
```

- [ ] **Step 3: 添加样式**

```vue
<style scoped>
/* 组件使用全局定义的 geometric-* 样式类 */
</style>
```

- [ ] **Step 4: 验证并提交**

```bash
git add frontend/src/components/bauhaus/GeometricDecoration.vue
git commit -m "feat(bauhaus): 添加 GeometricDecoration 组件

- 支持 circle 和 square 形状
- 支持三原色（red/blue/yellow）
- 支持自定义尺寸"
```

---

## 验证清单

完成所有任务后，进行以下验证：

- [ ] **所有组件文件已创建**
  ```bash
  ls -la frontend/src/components/bauhaus/
  ```
  Expected: 看到 4 个 .vue 文件

- [ ] **所有更改已提交**
  ```bash
  git status
  ```
  Expected: working tree clean

- [ ] **组件可以正常导入**
  ```bash
  grep -r "BauhausButton" frontend/src/components/bauhaus/
  ```
  Expected: 找到组件定义

---

## 下一步

阶段 2 完成后，继续：
- **阶段 3：首页重构** - 重写 Home.vue 应用包豪斯风格

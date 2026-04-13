<template>
  <div class="plan-progress">
    <div class="progress-title">
      <span class="progress-icon animate-spin">✨</span>
      <span>AI 正在为您规划行程...</span>
    </div>
    <div class="progress-steps">
      <div
        v-for="(step, index) in steps"
        :key="step.key"
        class="progress-step"
        :class="{
          completed: isCompleted(step.key),
          active: isActive(step.key),
          pending: isPending(step.key),
        }"
      >
        <div class="step-indicator">
          <span v-if="isCompleted(step.key)" class="step-check">✓</span>
          <span v-else-if="isActive(step.key)" class="step-pulse"></span>
          <span v-else class="step-dot"></span>
        </div>
        <div v-if="index < steps.length - 1" class="step-line" :class="{ filled: isCompleted(step.key) }"></div>
        <div class="step-content">
          <span class="step-label">{{ step.label }}</span>
          <span v-if="isActive(step.key)" class="step-status">进行中...</span>
          <span v-else-if="isCompleted(step.key)" class="step-status done">已完成</span>
        </div>
      </div>
    </div>
    <div v-if="currentMessage" class="progress-message">
      {{ currentMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  currentNode: string
  currentMessage?: string
}>()

const steps = [
  { key: 'search_attraction', label: '搜索景点' },
  { key: 'search_hotel', label: '搜索酒店' },
  { key: 'search_restaurant', label: '搜索餐厅' },
  { key: 'search_weather', label: '查询天气' },
  { key: 'generate_plan', label: '生成行程' },
]

const stepOrder = steps.map((s) => s.key)

const currentIndex = computed(() => {
  return stepOrder.indexOf(props.currentNode)
})

const isCompleted = (key: string): boolean => {
  const idx = stepOrder.indexOf(key)
  return idx < currentIndex.value
}

const isActive = (key: string): boolean => {
  return key === props.currentNode
}

const isPending = (key: string): boolean => {
  const idx = stepOrder.indexOf(key)
  return idx > currentIndex.value
}
</script>

<style scoped>
.plan-progress {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  box-shadow: var(--shadow-elevated);
  border: 1px solid var(--color-border-light);
  max-width: 600px;
  margin: 0 auto;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-6);
}

.progress-icon {
  font-size: var(--font-size-2xl);
}

.progress-steps {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.progress-step {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  position: relative;
}

.step-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.step-check {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-circle);
  background: var(--color-success);
  color: var(--color-text-inverse);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-sm);
}

.step-pulse {
  display: block;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-circle);
  background: var(--color-primary);
  position: relative;
}

.step-pulse::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: var(--radius-circle);
  border: 2px solid var(--color-primary);
  animation: pulse 2s ease-in-out infinite;
}

.step-dot {
  display: block;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-circle);
  background: var(--color-bg-tertiary);
  border: 2px solid var(--color-border);
}

.step-line {
  position: absolute;
  left: 13px;
  top: 28px;
  width: 2px;
  height: calc(100% - 12px);
  background: var(--color-border);
  z-index: 0;
}

.step-line.filled {
  background: var(--color-success);
}

.progress-step:last-child .step-line {
  display: none;
}

.step-content {
  padding: 4px 0 var(--space-4);
  min-width: 0;
}

.step-label {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.progress-step.pending .step-label {
  color: var(--color-text-disabled);
}

.step-status {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  margin-top: 2px;
}

.step-status.done {
  color: var(--color-success);
}

.progress-message {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-primary-bg);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  line-height: var(--line-height-relaxed);
}

@media (max-width: 480px) {
  .plan-progress {
    padding: var(--space-4);
  }

  .progress-title {
    font-size: var(--font-size-lg);
  }
}
</style>

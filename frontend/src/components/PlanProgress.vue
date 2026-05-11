<template>
  <div class="plan-progress">
    <div class="progress-title">
      <span class="progress-icon animate-spin">✨</span>
      <span>AI 正在为您规划行程...</span>
    </div>

    <div class="progress-steps">
      <template v-for="(step, index) in steps" :key="step.key">
        <div
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
      </template>
    </div>

    <div v-if="currentMessage" class="progress-message">
      <span class="message-dot"></span>
      {{ currentMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  currentNode: string
  currentMessage?: string
  completedNodes?: Set<string>
  steps?: Array<{ key: string; label: string }>
  nodeMapping?: Record<string, string>
}>(), {
  steps: () => [
    { key: 'web_search_attractions', label: '🔍 搜索景点攻略' },
    { key: 'search_hotel', label: '🏨 搜索酒店' },
    { key: 'search_weather', label: '🌤️ 查询天气' },
    { key: 'gather_search', label: '🔗 汇总搜索结果' },
    { key: 'cluster_attractions', label: '📊 景点聚类分析' },
    { key: 'search_food', label: '🍜 搜索美食' },
    { key: 'plan_route', label: '🗺️ 规划路线' },
    { key: 'macro_planner', label: '🏗️ 编排行程骨架' },
    { key: 'day_plan_subgraph', label: '📝 生成每日行程' },
    { key: 'reduce_assemble', label: '🔧 合并行程数据' },
    { key: 'global_synthesizer', label: '💡 生成全局建议' },
  ],
  nodeMapping: () => ({
    extract_attractions: 'web_search_attractions',
    geocode_attractions: 'web_search_attractions',
  }),
})

const stepOrder = computed(() => props.steps.map((s) => s.key))

const nodeToStepKey = computed(() => props.nodeMapping)

const effectiveNode = computed(() => {
  return nodeToStepKey.value[props.currentNode] || props.currentNode
})

const isCompleted = (key: string): boolean => {
  if (props.completedNodes && props.completedNodes.size > 0) {
    if (props.completedNodes.has(key)) return true
    const mapped = Object.entries(nodeToStepKey.value)
      .filter(([_, v]) => v === key)
    if (mapped.some(([k]) => props.completedNodes!.has(k))) return true
    return false
  }
  const idx = stepOrder.value.indexOf(effectiveNode.value)
  if (idx <= 0) return false
  return stepOrder.value.indexOf(key) < idx
}

const isActive = (key: string): boolean => {
  if (key === effectiveNode.value) return true
  const intermediates = Object.entries(nodeToStepKey.value)
    .filter(([_, v]) => v === key)
    .map(([k]) => k)
  return intermediates.includes(props.currentNode)
}

const isPending = (key: string): boolean => {
  return !isCompleted(key) && !isActive(key)
}
</script>

<style scoped>
.plan-progress {
  background: #ffffff;
  border-radius: 16px;
  padding: 24px;
  box-shadow: rgba(0, 0, 0, 0.04) 0px 8px 24px, rgba(102, 126, 234, 0.08) 0px 16px 48px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  max-width: 600px;
  margin: 0 auto;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 24px;
}

.progress-icon {
  font-size: 20px;
}

.progress-steps {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.progress-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
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
  border-radius: 50%;
  background: #52c41a;
  color: #fff;
  font-weight: 700;
  font-size: 12px;
}

.step-pulse {
  display: block;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #667eea;
  position: relative;
}

.step-pulse::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid #667eea;
  animation: pulse 2s ease-in-out infinite;
}

.step-dot {
  display: block;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #eeeef5;
  border: 2px solid rgba(0, 0, 0, 0.08);
}

.step-line {
  position: absolute;
  left: 13px;
  top: 28px;
  width: 2px;
  height: calc(100% - 12px);
  background: rgba(0, 0, 0, 0.08);
  z-index: 0;
}

.step-line.filled {
  background: #52c41a;
}

.progress-step:last-child .step-line {
  display: none;
}

.step-content {
  padding: 4px 0 16px;
  min-width: 0;
}

.step-label {
  font-size: 14px;
  font-weight: 500;
  color: #1a1a2e;
}

.progress-step.pending .step-label {
  color: #b8b8c8;
}

.step-status {
  display: block;
  font-size: 11px;
  color: #667eea;
  margin-top: 2px;
}

.step-status.done {
  color: #52c41a;
}

.progress-message {
  margin-top: 16px;
  padding: 10px 16px;
  background: #f0f3ff;
  border-radius: 8px;
  font-size: 13px;
  color: #667eea;
  line-height: 1.6;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.message-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #667eea;
  margin-top: 7px;
  flex-shrink: 0;
  animation: pulse 1.5s ease-in-out infinite;
}

@media (max-width: 480px) {
  .plan-progress {
    padding: 16px;
  }

  .progress-title {
    font-size: 16px;
  }

  .step-label {
    font-size: 13px;
  }
}
</style>

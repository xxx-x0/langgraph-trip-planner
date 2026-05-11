<template>
  <div class="tab-overview">
    <!-- 旅行建议 -->
    <div class="glass-card" v-if="tripPlan.overall_suggestions">
      <div class="card-header">
        <span class="card-icon">💡</span>
        <span class="card-title">旅行建议</span>
      </div>
      <div class="card-body">
        <div class="suggestions-content" v-html="renderedSuggestions"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import type { TripPlan } from '@/types'

const props = defineProps<{
  tripPlan: TripPlan
}>()

marked.setOptions({
  breaks: true,
  gfm: true,
})

const renderedSuggestions = computed(() => {
  if (!props.tripPlan.overall_suggestions) return ''
  return marked.parse(props.tripPlan.overall_suggestions) as string
})
</script>

<style scoped>
.tab-overview {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  animation: fadeInUp var(--transition-normal);
}

.glass-card {
  background: var(--color-glass-bg);
  backdrop-filter: blur(var(--blur-glass));
  -webkit-backdrop-filter: blur(var(--blur-glass));
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-gradient);
  color: #fff;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
}

.card-icon {
  font-size: var(--font-size-lg);
}

.card-body {
  padding: var(--space-4);
}

.suggestions-content {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  line-height: var(--line-height-relaxed);
}

:deep(.suggestions-content h1),
:deep(.suggestions-content h2),
:deep(.suggestions-content h3),
:deep(.suggestions-content h4) {
  margin: var(--space-4) 0 var(--space-2);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
}

:deep(.suggestions-content h2) {
  font-size: var(--font-size-lg);
  padding-bottom: var(--space-1);
  border-bottom: 1px solid var(--color-border-light);
}

:deep(.suggestions-content h3) {
  font-size: var(--font-size-md);
}

:deep(.suggestions-content p) {
  margin: var(--space-2) 0;
}

:deep(.suggestions-content ul),
:deep(.suggestions-content ol) {
  margin: var(--space-2) 0;
  padding-left: var(--space-5);
}

:deep(.suggestions-content li) {
  margin: var(--space-1) 0;
}

:deep(.suggestions-content strong) {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
}

:deep(.suggestions-content code) {
  background: var(--color-bg-secondary);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  font-size: 0.9em;
}

:deep(.suggestions-content blockquote) {
  border-left: 3px solid var(--color-primary);
  padding-left: var(--space-3);
  margin: var(--space-3) 0;
  color: var(--color-text-secondary);
}
</style>

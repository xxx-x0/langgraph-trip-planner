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

/* Bauhaus card styling */
.glass-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-6);
  background: var(--primary-red);
  color: var(--white);
  border-bottom: var(--border-main) solid var(--border);
}

.card-title {
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.card-icon {
  font-size: var(--text-2xl);
}

.card-body {
  padding: var(--space-6);
}

.suggestions-content {
  font-size: var(--text-base);
  color: var(--foreground);
  line-height: var(--line-height-relaxed);
}

:deep(.suggestions-content h1),
:deep(.suggestions-content h2),
:deep(.suggestions-content h3),
:deep(.suggestions-content h4) {
  margin: var(--space-4) 0 var(--space-2);
  color: var(--foreground);
  font-weight: var(--font-black);
  text-transform: uppercase;
}

:deep(.suggestions-content h2) {
  font-size: var(--text-xl);
  padding-bottom: var(--space-2);
  border-bottom: var(--border-2) solid var(--border);
}

:deep(.suggestions-content h3) {
  font-size: var(--text-lg);
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
  color: var(--foreground);
  font-weight: var(--font-bold);
}

:deep(.suggestions-content code) {
  background: var(--background);
  padding: 2px 6px;
  border: 1px solid var(--border);
  font-size: 0.9em;
}

:deep(.suggestions-content blockquote) {
  border-left: 4px solid var(--primary-blue);
  padding-left: var(--space-3);
  margin: var(--space-3) 0;
  color: var(--muted-foreground);
  background: var(--background);
  padding: var(--space-3);
}
</style>

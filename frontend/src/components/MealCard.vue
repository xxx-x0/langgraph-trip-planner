<template>
  <div class="meal-card" :class="[`source-${meal.source || 'default'}`]">
    <div class="meal-header">
      <span class="meal-type-badge">{{ getMealLabel(meal.type) }}</span>
      <span v-if="meal.cuisine" class="meal-cuisine-tag">{{ meal.cuisine }}</span>
      <span v-if="meal.source === 'nearby'" class="source-badge nearby">📍 附近</span>
      <span v-else-if="meal.source === 'popular'" class="source-badge popular">🔥 热门</span>
    </div>
    <div class="meal-name">{{ meal.name }}</div>
    <div class="meal-details">
      <span v-if="meal.rating" class="detail-item">
        <span class="detail-star">★</span>{{ meal.rating }}
      </span>
      <span v-if="meal.avg_cost" class="detail-item price">¥{{ meal.avg_cost }}/人</span>
      <span v-if="meal.distance" class="detail-item">📏 {{ meal.distance }}</span>
    </div>
    <div v-if="meal.address" class="meal-address">📍 {{ meal.address }}</div>
    <div v-if="meal.description" class="meal-desc">{{ meal.description }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Meal } from '@/types'

defineProps<{
  meal: Meal
}>()

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  }
  return labels[type] || type
}
</script>

<style>
.meal-card {
  background: #ffffff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: rgba(0, 0, 0, 0.02) 0px 0px 0px 1px, rgba(0, 0, 0, 0.04) 0px 2px 6px, rgba(102, 126, 234, 0.06) 0px 4px 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.meal-card:hover {
  box-shadow: rgba(0, 0, 0, 0.02) 0px 0px 0px 1px, rgba(0, 0, 0, 0.06) 0px 4px 12px, rgba(102, 126, 234, 0.1) 0px 8px 24px;
  transform: translateY(-2px);
}

.meal-card.source-nearby {
  border-left: 3px solid #67c23a;
}

.meal-card.source-popular {
  border-left: 3px solid #f56c6c;
}
</style>

<style scoped>
.meal-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}

.meal-type-badge {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: 9999px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: #ffffff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.meal-cuisine-tag {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: 9999px;
  font-size: var(--font-size-xs);
  color: #faad14;
  background: #fffbe6;
  border: 1px solid rgba(250, 173, 20, 0.2);
}

.source-badge {
  display: inline-block;
  padding: 1px var(--space-2);
  border-radius: 9999px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.source-badge.nearby {
  color: #67c23a;
  background: #f6ffed;
}

.source-badge.popular {
  color: #f56c6c;
  background: #fff2f0;
}

.meal-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.meal-details {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.detail-star {
  color: #faad14;
}

.detail-item.price {
  color: #faad14;
  font-weight: var(--font-weight-medium);
}

.meal-address {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meal-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.7;
}
</style>

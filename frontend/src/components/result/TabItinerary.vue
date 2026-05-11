<template>
  <div class="tab-itinerary">
    <div class="glass-card">
      <div class="card-header">
        <span class="card-icon">📅</span>
        <span class="card-title">每日行程</span>
      </div>
      <div class="itinerary-body">
        <a-collapse v-model:activeKey="localActiveDays" accordion>
          <a-collapse-panel v-for="(day, index) in tripPlan.days" :key="index" :id="`day-${index}`">
            <template #header>
              <div class="day-header">
                <span class="day-title">第{{ day.day_index + 1 }}天</span>
                <span class="day-date">{{ day.date }}</span>
              </div>
            </template>

            <div class="day-info">
              <div class="info-row">
                <span class="label">📝 行程描述:</span>
                <span class="value">{{ day.description }}</span>
              </div>
              <div class="info-row">
                <span class="label">🚗 交通方式:</span>
                <span class="value">{{ day.transportation }}</span>
              </div>
              <div class="info-row">
                <span class="label">🏨 住宿:</span>
                <span class="value">{{ day.accommodation }}</span>
              </div>
            </div>

            <a-divider orientation="left">⏰ 日程时间轴</a-divider>
            <DayTimeline :day="day" />

            <a-divider orientation="left">🎯 景点安排</a-divider>
            <div class="attractions-grid">
              <div v-for="(item, attrIdx) in day.attractions" :key="item.name + attrIdx" class="attraction-wrapper">
                <div v-if="editMode" class="attraction-actions">
                  <a-button size="small" @click="$emit('moveAttraction', day.day_index, attrIdx, 'up')" :disabled="attrIdx === 0">↑</a-button>
                  <a-button size="small" @click="$emit('moveAttraction', day.day_index, attrIdx, 'down')" :disabled="attrIdx === day.attractions.length - 1">↓</a-button>
                  <a-button size="small" danger @click="$emit('deleteAttraction', day.day_index, attrIdx)">删除</a-button>
                </div>
                <AttractionCard
                  :attraction="item"
                  :global-index="getAttractionGlobalIndex(day.day_index, attrIdx)"
                  :edit-mode="editMode"
                  :photo-url="attractionPhotos[item.name]"
                />
              </div>
            </div>

            <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
            <HotelCard v-if="day.hotel" :hotel="day.hotel" />

            <a-divider orientation="left">🍽️ 餐饮安排</a-divider>
            <div class="meals-section">
              <div v-if="day.meals.filter(m => m.source === 'nearby').length > 0" class="meals-group">
                <div class="meals-group-title">📍 景点周边餐厅</div>
                <div class="meals-grid">
                  <MealCard v-for="meal in day.meals.filter(m => m.source === 'nearby')" :key="meal.type + meal.name" :meal="meal" />
                </div>
              </div>
              <div v-if="day.meals.filter(m => m.source === 'popular').length > 0" class="meals-group">
                <div class="meals-group-title">🔥 城市热门餐厅</div>
                <div class="meals-grid">
                  <MealCard v-for="meal in day.meals.filter(m => m.source === 'popular')" :key="meal.type + meal.name" :meal="meal" />
                </div>
              </div>
              <div v-if="day.meals.filter(m => !m.source || (m.source !== 'nearby' && m.source !== 'popular')).length > 0" class="meals-group">
                <div class="meals-group-title">🍽️ 餐饮推荐</div>
                <div class="meals-grid">
                  <MealCard v-for="meal in day.meals.filter(m => !m.source || (m.source !== 'nearby' && m.source !== 'popular'))" :key="meal.type + meal.name" :meal="meal" />
                </div>
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TripPlan } from '@/types'
import DayTimeline from '@/components/DayTimeline.vue'
import AttractionCard from '@/components/AttractionCard.vue'
import HotelCard from '@/components/HotelCard.vue'
import MealCard from '@/components/MealCard.vue'

const props = defineProps<{
  tripPlan: TripPlan
  editMode: boolean
  attractionPhotos: Record<string, string>
  activeDays: number[]
}>()

const emit = defineEmits<{
  'update:activeDays': [value: number[]]
  deleteAttraction: [dayIndex: number, attrIndex: number]
  moveAttraction: [dayIndex: number, attrIndex: number, direction: 'up' | 'down']
}>()

const localActiveDays = computed({
  get: () => props.activeDays,
  set: (val) => emit('update:activeDays', val)
})

const getAttractionGlobalIndex = (dayIndex: number, attrIndex: number): number => {
  if (!props.tripPlan) return attrIndex + 1
  let count = 0
  for (const day of props.tripPlan.days) {
    if (day.day_index >= dayIndex) break
    count += day.attractions?.length || 0
  }
  return count + attrIndex + 1
}
</script>

<style scoped>
.tab-itinerary {
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
  padding: var(--space-4) var(--space-5);
  background: var(--color-gradient);
  color: #fff;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.card-icon {
  font-size: var(--font-size-xl);
}

.itinerary-body {
  padding: var(--space-5);
}

:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-border) !important;
  border-radius: var(--radius-md) !important;
  overflow: hidden;
}

:deep(.ant-collapse-header) {
  background: var(--color-bg-secondary) !important;
  padding: var(--space-4) var(--space-5) !important;
  font-weight: var(--font-weight-semibold);
}

:deep(.ant-collapse-content) {
  border-top: 1px solid var(--color-border-light) !important;
}

:deep(.ant-collapse-content-box) {
  padding: var(--space-5);
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.day-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.day-date {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.day-info {
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.info-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.info-row:last-child { margin-bottom: 0; }

.info-row .label {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  min-width: 100px;
}

.info-row .value {
  color: var(--color-text-primary);
  flex: 1;
}

.attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.attraction-wrapper {
  display: flex;
  flex-direction: column;
}

.attraction-actions {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.meals-section { margin-top: var(--space-2); }
.meals-group { margin-bottom: var(--space-4); }
.meals-group:last-child { margin-bottom: 0; }

.meals-group-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-3);
  padding-left: var(--space-1);
}

.meals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-3);
}

@media (max-width: 768px) {
  .attractions-grid,
  .meals-grid {
    grid-template-columns: 1fr;
  }
}
</style>

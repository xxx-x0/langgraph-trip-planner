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
              <div class="day-header" :class="`day-color-${index % 3}`">
                <div class="day-badge">
                  <span class="day-number">{{ day.day_index + 1 }}</span>
                </div>
                <div class="day-info-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                </div>
              </div>
            </template>

            <!-- 每日信息 - 1+2 布局：描述占满 + 交通住宿横排 -->
            <div class="day-info-grid">
              <div class="info-card info-card-blue info-card-wide">
                <div class="info-card-icon">📝</div>
                <div class="info-card-content">
                  <div class="info-card-label">行程描述</div>
                  <div class="info-card-value">{{ day.description }}</div>
                </div>
              </div>
              <div class="info-row-pair">
                <div class="info-card info-card-yellow">
                  <div class="info-card-icon">🚗</div>
                  <div class="info-card-content">
                    <div class="info-card-label">交通方式</div>
                    <div class="info-card-value">{{ day.transportation }}</div>
                  </div>
                </div>
                <div class="info-card info-card-red">
                  <div class="info-card-icon">🏨</div>
                  <div class="info-card-content">
                    <div class="info-card-label">住宿</div>
                    <div class="info-card-value">{{ day.accommodation }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 日程时间轴 -->
            <div class="section-block section-block-blue">
              <div class="section-block-title">⏰ 日程时间轴</div>
              <div class="section-block-content">
                <DayTimeline :day="day" />
              </div>
            </div>

            <!-- 景点安排 -->
            <div class="section-block section-block-red">
              <div class="section-block-title">🎯 景点安排</div>
              <div class="section-block-content">
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
              </div>
            </div>

            <!-- 住宿推荐 -->
            <div v-if="day.hotel" class="section-block section-block-yellow">
              <div class="section-block-title">🏨 住宿推荐</div>
              <div class="section-block-content">
                <HotelCard :hotel="day.hotel" />
              </div>
            </div>

            <!-- 餐饮安排 -->
            <div class="section-block section-block-red">
              <div class="section-block-title">🍽️ 餐饮安排</div>
              <div class="section-block-content">
                <div class="meals-section">
                  <div v-if="day.meals.filter(m => m.source === 'nearby').length > 0" class="meals-group">
                    <div class="meals-group-title meals-group-title-blue">📍 景点周边餐厅</div>
                    <div class="meals-grid">
                      <MealCard v-for="meal in day.meals.filter(m => m.source === 'nearby')" :key="meal.type + meal.name" :meal="meal" />
                    </div>
                  </div>
                  <div v-if="day.meals.filter(m => m.source === 'popular').length > 0" class="meals-group">
                    <div class="meals-group-title meals-group-title-red">🔥 城市热门餐厅</div>
                    <div class="meals-grid">
                      <MealCard v-for="meal in day.meals.filter(m => m.source === 'popular')" :key="meal.type + meal.name" :meal="meal" />
                    </div>
                  </div>
                  <div v-if="day.meals.filter(m => !m.source || (m.source !== 'nearby' && m.source !== 'popular')).length > 0" class="meals-group">
                    <div class="meals-group-title meals-group-title-yellow">🍽️ 餐饮推荐</div>
                    <div class="meals-grid">
                      <MealCard v-for="meal in day.meals.filter(m => !m.source || (m.source !== 'nearby' && m.source !== 'popular'))" :key="meal.type + meal.name" :meal="meal" />
                    </div>
                  </div>
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
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  background: var(--primary-red);
  color: var(--white);
  border-bottom: var(--border-main) solid var(--border);
  position: relative;
}

/* 头部右侧装饰 */
.card-header::after {
  content: '';
  position: absolute;
  right: 24px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  background: var(--primary-yellow);
  border: 3px solid var(--border);
  border-radius: 50%;
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

.itinerary-body {
  padding: var(--space-6);
  background: var(--background);
}

/* Collapse 重置 */
:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: var(--space-6);
  border: var(--border-main) solid var(--border) !important;
  border-radius: 0 !important;
  overflow: hidden;
  box-shadow: var(--shadow-main);
}

:deep(.ant-collapse-item-active) {
  /* 展开时降低阴影避免与内部叠加 */
  box-shadow: 4px 4px 0px 0px var(--border);
}

:deep(.ant-collapse-header) {
  padding: 0 !important;
  background: transparent !important;
  border-bottom: var(--border-main) solid var(--border) !important;
}

:deep(.ant-collapse-content) {
  border-top: none !important;
  background: var(--white) !important;
}

:deep(.ant-collapse-content-box) {
  padding: var(--space-6) !important;
}

/* 隐藏默认箭头 */
:deep(.ant-collapse-expand-icon) {
  align-self: center;
  padding-right: var(--space-4) !important;
}

:deep(.ant-collapse-arrow) {
  color: var(--foreground) !important;
  font-size: 18px !important;
  font-weight: 900 !important;
}

/* 彩色日期头部 */
.day-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  width: 100%;
  padding: var(--space-4) var(--space-6);
  transition: all 0.15s ease-out;
}

.day-header.day-color-0 {
  background: var(--primary-red);
  color: var(--white);
}

.day-header.day-color-1 {
  background: var(--primary-blue);
  color: var(--white);
}

.day-header.day-color-2 {
  background: var(--primary-yellow);
  color: var(--foreground);
}

/* 日期编号徽章 */
.day-badge {
  width: 56px;
  height: 56px;
  background: var(--white);
  border: 3px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 3px 3px 0px 0px var(--border);
  flex-shrink: 0;
}

.day-number {
  font-size: 28px;
  font-weight: var(--font-black);
  color: var(--foreground);
  line-height: 1;
}

.day-info-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.day-title {
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  line-height: 1.1;
}

.day-date {
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
  opacity: 0.9;
  letter-spacing: 0.03em;
}

/* 每日信息卡片 - 1+2 布局 */
.day-info-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.info-row-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.info-card {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 3px solid var(--border);
  transition: background 0.15s ease-out;
}

.info-card-wide {
  align-items: center;
}

.info-card-blue {
  background: var(--primary-blue);
  color: var(--white);
}

.info-card-yellow {
  background: var(--primary-yellow);
  color: var(--foreground);
}

.info-card-red {
  background: var(--primary-red);
  color: var(--white);
}

.info-card-icon {
  font-size: 24px;
  width: 40px;
  height: 40px;
  background: var(--white);
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.info-card-content {
  flex: 1;
  min-width: 0;
}

.info-card-label {
  font-size: 11px;
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  opacity: 0.9;
  margin-bottom: 4px;
}

.info-card-value {
  font-size: 14px;
  font-weight: var(--font-bold);
  line-height: 1.5;
  word-break: break-word;
}

/* Section 块 - 简洁边框，无阴影 */
.section-block {
  margin-bottom: var(--space-5);
  border: 3px solid var(--border);
  background: var(--white);
  overflow: hidden;
}

.section-block-title {
  padding: var(--space-3) var(--space-4);
  font-size: 16px;
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-bottom: 3px solid var(--border);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.section-block-blue .section-block-title {
  background: var(--primary-blue);
  color: var(--white);
}

.section-block-red .section-block-title {
  background: var(--primary-red);
  color: var(--white);
}

.section-block-yellow .section-block-title {
  background: var(--primary-yellow);
  color: var(--foreground);
}

.section-block-content {
  padding: var(--space-4);
  background: var(--white);
}

/* 内部嵌套的卡片降级阴影 - 避免阴影叠加 */
.section-block-content :deep(.attraction-card),
.section-block-content :deep(.hotel-card),
.section-block-content :deep(.meal-card),
.section-block-content :deep(.day-timeline) {
  box-shadow: none !important;
  border-width: 2px !important;
}

.section-block-content :deep(.attraction-card:hover),
.section-block-content :deep(.hotel-card:hover),
.section-block-content :deep(.meal-card:hover) {
  box-shadow: 3px 3px 0px 0px var(--border) !important;
  transform: translate(-1px, -1px);
}

/* 景点网格 */
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
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

:deep(.attraction-actions .ant-btn) {
  border: 2px solid var(--border) !important;
  border-radius: 0 !important;
  font-weight: var(--font-black) !important;
  background: var(--white) !important;
  box-shadow: none !important;
  transition: background 0.15s ease-out;
}

:deep(.attraction-actions .ant-btn:hover) {
  background: var(--primary-yellow) !important;
}

:deep(.attraction-actions .ant-btn-dangerous) {
  background: var(--primary-red) !important;
  color: var(--white) !important;
}

:deep(.attraction-actions .ant-btn-dangerous:hover) {
  background: var(--foreground) !important;
}

/* 餐饮分组 - 简洁边框，无外层阴影 */
.meals-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.meals-group {
  background: var(--white);
  border: 2px solid var(--border);
  overflow: hidden;
}

.meals-group-title {
  font-size: 14px;
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: var(--space-2) var(--space-3);
  border-bottom: 2px solid var(--border);
}

.meals-group-title-blue {
  background: var(--primary-blue);
  color: var(--white);
}

.meals-group-title-red {
  background: var(--primary-red);
  color: var(--white);
}

.meals-group-title-yellow {
  background: var(--primary-yellow);
  color: var(--foreground);
}

.meals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-3);
  padding: var(--space-3);
}

@media (max-width: 768px) {
  .info-row-pair {
    grid-template-columns: 1fr;
  }

  .attractions-grid,
  .meals-grid {
    grid-template-columns: 1fr;
  }

  .day-badge {
    width: 48px;
    height: 48px;
  }

  .day-number {
    font-size: 22px;
  }

  .day-header {
    padding: var(--space-3) var(--space-4);
  }

  .card-header::after {
    display: none;
  }
}
</style>

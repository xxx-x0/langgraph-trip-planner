<template>
  <div class="tab-itinerary">
    <div class="glass-card">
      <div class="card-header">
        <span class="card-icon">📅</span>
        <span class="card-title">每日行程</span>
      </div>
      <div class="itinerary-body">
        <a-collapse v-model:activeKey="localActiveDays" :accordion="!expanded">
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
              <details class="info-card info-card-blue info-card-wide" :open="expanded"><summary>当天安排说明</summary>
                <div class="info-card-icon">📝</div>
                <div class="info-card-content">
                  <div class="info-card-label">今天怎么逛</div>
                  <div class="info-card-value">{{ day.description_source === 'itinerary_facts_v1' ? day.description : '旧版说明尚未核对，请以行程数据为参考。' }}</div>
                </div>
              </details>
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

            <p v-if="day.pending_confirmations?.length">下一步：{{ day.pending_confirmations[0] }}</p>
            <details v-if="day.pending_confirmations?.length" :open="expanded">
              <summary>出发前还要确认 {{ day.pending_confirmations.length }} 项</summary>
              <ul><li v-for="item in day.pending_confirmations" :key="item">{{ item }}</li></ul>
            </details>
            <!-- 日程时间轴 -->
            <div class="section-block section-block-blue">
              <div class="section-block-title">⏰ 日程时间轴</div>
              <div class="section-block-content">
                <DayTimeline :day="day" />
                <div v-if="day.meal_warnings?.length" role="alert">
                  <p v-for="warning in day.meal_warnings" :key="warning">⚠️ {{ warning }}</p>
                </div>
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
              <div class="section-block-title">{{ day.overnight_stay === false ? '🏨 酒店位置参考（不计新增住宿）' : '🏨 住宿推荐' }}</div>
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
  expanded?: boolean
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
  get: () => props.expanded ? props.tripPlan.days.map((_, index) => index) : props.activeDays,
  set: (val: string | number | Array<string | number> | undefined) => {
    if (props.expanded) return
    const keys = val == null ? [] : Array.isArray(val) ? val : [val]
    emit('update:activeDays', keys.map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < props.tripPlan.days.length))
  }
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
.tab-itinerary { color: var(--color-text-primary); }
.glass-card { background: var(--color-bg-primary); border: 1px solid var(--color-border); border-radius: 18px; overflow: hidden; }
.card-header { padding: 24px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--color-border); }
.card-icon { display: none; }.card-title { font-size: 24px; font-weight: 500; }
.itinerary-body { padding: 12px 24px 24px; }
:deep(.ant-collapse) { background: transparent; border: 0; }:deep(.ant-collapse-item) { border-bottom: 1px solid var(--color-border); }:deep(.ant-collapse-content) { background: transparent; border: 0; }:deep(.ant-collapse-content-box) { padding: 8px 0 24px !important; }:deep(.ant-collapse-header) { align-items: center !important; padding: 16px 0 !important; }
.day-header { display: flex; align-items: center; gap: 14px; }.day-badge { width: 40px; height: 40px; display: grid; place-items: center; background: var(--color-bg-secondary); color: var(--color-primary); border-radius: 12px; font-size: 20px; }.day-info-header { display: flex; gap: 12px; align-items: baseline; }.day-title { font-size: 16px; font-weight: 500; }.day-date { color: var(--color-text-secondary); font-size: 12px; }
.day-info-grid { display: flex; flex-direction: column; gap: 12px; margin-bottom: 18px; }.info-row-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; order: -1; }.info-card { padding: 16px; background: var(--color-bg-secondary); color: var(--color-text-primary); border-radius: 12px; min-width: 0; }.info-card-icon { display: none; }.info-card-label { font-size: 11px; color: var(--color-text-secondary); margin-bottom: 8px; }.info-card-value { font-size: 13px; line-height: 1.85; overflow-wrap: anywhere; }.info-card-wide .info-card-content { margin-top: 14px; }.info-card-wide .info-card-label { display: none; }
details { font-size: 13px; line-height: 1.85; color: var(--color-text-secondary); }summary { cursor: pointer; color: var(--color-primary); }details ul { padding-left: 20px; } .itinerary-body p { font-size: 13px; line-height: 1.8; }
.section-block { margin-top: 24px; }.section-block-title { font-size: 16px; font-weight: 500; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); margin-bottom: 16px; }.section-block-content { min-width: 0; }
.attractions-grid,.meals-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(min(100%,290px),1fr)); gap: 16px; }.attraction-wrapper { min-width: 0; }.attraction-actions { display: flex; gap: 6px; margin-bottom: 8px; }.meals-group { margin-bottom: 20px; }.meals-group-title { color: var(--color-text-secondary); font-size: 12px; margin-bottom: 12px; }
@media(max-width:600px) { .card-header { padding: 20px 18px; }.itinerary-body { padding: 8px 16px 18px; }.info-row-pair { grid-template-columns: 1fr; }.day-info-header { flex-wrap: wrap; gap: 4px 12px; } }

:deep(.day-timeline) { padding: 0; border: 0; background: transparent; box-shadow: none; }
:deep(.timeline-header) { border: 0; padding-bottom: 4px; }
:deep(.timeline-title) { font-size: 13px; font-weight: 400; color: var(--color-text-secondary); }
:deep(.tl-card:not(.travel)) { border: 1px solid var(--color-border); border-radius: 12px; background: var(--color-bg-secondary); }
:deep(.tl-card:hover) { box-shadow: none; }
:deep(.tl-card-header) { flex-wrap: wrap; }
:deep(.tl-name) { overflow-wrap: anywhere; }
:deep(.tl-card-detail) { line-height: 1.8; }

:deep(.hotel-card),:deep(.attraction-card),:deep(.meal-card) { border: 1px solid var(--color-border); border-radius: 14px; background: var(--color-bg-secondary); box-shadow: none; }
:deep(.hotel-card:hover),:deep(.attraction-card:hover),:deep(.meal-card:hover) { transform: none; box-shadow: none; }
:deep(.hotel-card::after),:deep(.attraction-card::after) { display: none; }
:deep(.hotel-name) { white-space: normal; text-transform: none; letter-spacing: 0; line-height: 1.6; }
:deep(.meal-address) { white-space: normal; line-height: 1.8; }
</style>

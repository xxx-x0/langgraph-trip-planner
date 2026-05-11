<template>
  <div class="day-timeline">
    <div class="timeline-header">
      <span class="timeline-title">⏰ 时间安排</span>
      <span class="timeline-summary">
        {{ timelineItems.length }}项活动 · {{ formatTimeRange }}
      </span>
    </div>
    <div class="timeline-list">
      <div
        v-for="(item, idx) in timelineItems"
        :key="idx"
        class="tl-row"
        :class="item.type"
        @click="$emit('itemClick', item)"
      >
        <div class="tl-time">
          <span class="tl-time-start">{{ item.startTime }}</span>
          <span class="tl-time-end">{{ item.endTime }}</span>
        </div>
        <div class="tl-connector">
          <div class="tl-dot" :class="item.type"></div>
          <div v-if="idx < timelineItems.length - 1" class="tl-line"></div>
        </div>
        <div class="tl-card" :class="item.type">
          <div class="tl-card-header">
            <span class="tl-icon">{{ getIcon(item.type) }}</span>
            <span class="tl-name">{{ item.name }}</span>
            <span v-if="item.cost" class="tl-cost">¥{{ item.cost }}</span>
          </div>
          <div class="tl-card-meta">
            <span class="tl-duration">{{ item.duration }}分钟</span>
            <span v-if="item.mode" class="tl-mode">· {{ getModeIcon(item.mode) }} {{ item.mode }}</span>
            <span v-if="item.distance" class="tl-distance">· 📏 {{ item.distance }}</span>
          </div>
          <div v-if="item.detail" class="tl-card-detail">{{ item.detail }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DayPlan } from '@/types'

interface TimelineItem {
  type: 'attraction' | 'meal' | 'hotel' | 'travel'
  name: string
  startTime: string
  endTime: string
  startMinutes: number
  endMinutes: number
  duration: number
  cost?: number
  detail?: string
  mode?: string
  distance?: string
}

const props = defineProps<{
  day: DayPlan
}>()

defineEmits<{
  itemClick: [item: TimelineItem]
}>()

const BASE_START_HOUR = 6

function findRouteSegment(routeSegs: any[], from: string, to: string) {
  return routeSegs.find(s => s.from_name === from && s.to_name === to)
    || routeSegs.find(s =>
      (s.from_name.includes(from) || from.includes(s.from_name)) &&
      (s.to_name.includes(to) || to.includes(s.to_name))
    )
    || routeSegs.find(s => s.from_name.includes(from) || from.includes(s.from_name))
}

// 首先计算原始的时间线项目（不使用 timeRange）
const rawTimelineItems = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = []
  const day = props.day

  if (!day) return items

  let currentMinutes = 8 * 60

  const hotelName = day.hotel?.name || '酒店'
  const attractions = day.attractions || []
  const meals = day.meals || []
  const routeSegs = day.route_segments || []

  const breakfast = meals.find(m => m.type === 'breakfast')
  if (breakfast) {
    const route = findRouteSegment(routeSegs, hotelName, breakfast.name)
    const travelMin = route ? parseDuration(route.duration) : 15
    const detail = route?.detail || '前往早餐地点'
    const mode = route?.mode
    const distance = route?.distance
    items.push(makeItem('travel', `${hotelName} → ${breakfast.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
    currentMinutes += travelMin

    const dur = 45
    items.push(makeItem('meal', breakfast.name, currentMinutes, dur, breakfast.estimated_cost, breakfast.cuisine))
    currentMinutes += dur
  }

  for (let i = 0; i < attractions.length; i++) {
    const attr = attractions[i]

    if (i === 0 && breakfast) {
      const route = findRouteSegment(routeSegs, breakfast.name, attr.name)
      const travelMin = route ? parseDuration(route.duration) : 20
      const detail = route?.detail || `前往${attr.name}`
      const mode = route?.mode
      const distance = route?.distance
      items.push(makeItem('travel', `${breakfast.name} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
      currentMinutes += travelMin
    } else if (i > 0) {
      const prevAttr = attractions[i - 1]
      const route = findRouteSegment(routeSegs, prevAttr.name, attr.name)
      const travelMin = route ? parseDuration(route.duration) : 25
      const detail = route?.detail || `从${prevAttr.name}前往${attr.name}`
      const mode = route?.mode
      const distance = route?.distance
      items.push(makeItem('travel', `${prevAttr.name} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
      currentMinutes += travelMin
    } else {
      const route = findRouteSegment(routeSegs, hotelName, attr.name)
      const travelMin = route ? parseDuration(route.duration) : 30
      const detail = route?.detail || '从酒店出发'
      const mode = route?.mode
      const distance = route?.distance
      items.push(makeItem('travel', `${hotelName} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
      currentMinutes += travelMin
    }

    const visitDur = attr.visit_duration || 120
    items.push(makeItem('attraction', attr.name, currentMinutes, visitDur, attr.ticket_price, attr.description?.slice(0, 60)))
    currentMinutes += visitDur

    if (i === Math.floor(attractions.length / 2) - 1 || (attractions.length === 1 && i === 0)) {
      const lunch = meals.find(m => m.type === 'lunch')
      if (lunch) {
        const travelMin = 15
        items.push(makeItem('travel', `前往午餐`, currentMinutes, travelMin, undefined, '前往餐厅'))
        currentMinutes += travelMin
        const dur = 60
        items.push(makeItem('meal', lunch.name, currentMinutes, dur, lunch.estimated_cost, lunch.cuisine))
        currentMinutes += dur
      }
    }
  }

  const dinner = meals.find(m => m.type === 'dinner')
  if (dinner) {
    const lastAttr = attractions[attractions.length - 1]
    const route = lastAttr ? findRouteSegment(routeSegs, lastAttr.name, dinner.name) : undefined
    const travelToDinner = route ? parseDuration(route.duration) : 20
    const detail = route?.detail || '前往餐厅'
    const mode = route?.mode
    const distance = route?.distance
    items.push(makeItem('travel', lastAttr ? `${lastAttr.name} → ${dinner.name}` : '前往晚餐', currentMinutes, travelToDinner, undefined, detail, mode, distance))
    currentMinutes += travelToDinner

    const dur = 90
    items.push(makeItem('meal', dinner.name, currentMinutes, dur, dinner.estimated_cost, dinner.cuisine))
    currentMinutes += dur
  }

  const lastItem = attractions[attractions.length - 1]
  const routeBack = findRouteSegment(routeSegs, lastItem?.name || '', hotelName)
  const travelBack = routeBack ? parseDuration(routeBack.duration) : 20
  const backDetail = routeBack?.detail || '结束一天行程，返回酒店'
  const backMode = routeBack?.mode
  const backDistance = routeBack?.distance
  items.push(makeItem('travel', '返回酒店', currentMinutes, travelBack, undefined, backDetail, backMode, backDistance))
  currentMinutes += travelBack

  if (day.hotel) {
    items.push(makeItem('hotel', day.hotel.name, currentMinutes, 30, day.hotel.estimated_cost, day.hotel.address))
  }

  return items
})

// 基于原始项目计算时间范围
const timeRange = computed(() => {
  const items = rawTimelineItems.value
  if (items.length === 0) {
    const startHour = 7
    const endHour = 22
    return { 
      start: startHour * 60, 
      end: endHour * 60, 
      total: (endHour - startHour) * 60,
      startHour,
      endHour,
    }
  }

  let minStart = items[0].startMinutes
  let maxEnd = items[items.length - 1].endMinutes

  const paddingBefore = 30
  const paddingAfter = 60

  minStart = Math.max(minStart - paddingBefore, BASE_START_HOUR * 60)
  maxEnd = maxEnd + paddingAfter

  const startHour = Math.floor(minStart / 60)
  const endHour = Math.ceil(maxEnd / 60)

  return {
    start: startHour * 60,
    end: endHour * 60,
    total: (endHour - startHour) * 60,
    startHour,
    endHour,
  }
})

// 最终的时间线项目，基于 timeRange 调整时间
const timelineItems = computed<TimelineItem[]>(() => {
  const items = rawTimelineItems.value
  if (items.length === 0) return items
  
  const range = timeRange.value
  const offset = range.start + 30 - items[0].startMinutes
  
  if (offset === 0) return items
  
  // 调整所有项目的时间
  return items.map(item => ({
    ...item,
    startMinutes: item.startMinutes + offset,
    endMinutes: item.endMinutes + offset,
    startTime: formatTime(item.startMinutes + offset),
    endTime: formatTime(item.endMinutes + offset),
  }))
})

const formatTimeRange = computed(() => {
  const r = timeRange.value
  return `${formatTime(r.start)} - ${formatTime(r.end)}`
})

function makeItem(type: TimelineItem['type'], name: string, startMin: number, dur: number, cost?: number, detail?: string, mode?: string, distance?: string): TimelineItem {
  return {
    type,
    name,
    startTime: formatTime(startMin),
    endTime: formatTime(startMin + dur),
    startMinutes: startMin,
    endMinutes: startMin + dur,
    duration: dur,
    cost,
    detail,
    mode,
    distance,
  }
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

function parseDuration(durStr?: string): number {
  if (!durStr) return 25
  const match = durStr.match(/(\d+)/)
  return match ? Math.max(parseInt(match[1]), 10) : 25
}

function getIcon(type: string): string {
  const map: Record<string, string> = {
    attraction: '🎯',
    meal: '🍽️',
    hotel: '🏨',
    travel: '🚗',
  }
  return map[type] || '📍'
}

function getModeIcon(mode: string): string {
  const map: Record<string, string> = {
    '地铁': '🚇', '公交': '🚌', '步行': '🚶', '驾车': '🚗', '出租车': '🚕', '骑行': '🚲',
  }
  return map[mode] || '🚗'
}
</script>

<style scoped>
.day-timeline {
  background: var(--color-bg-secondary, #fafbfc);
  border-radius: var(--radius-md, 12px);
  padding: var(--space-4, 16px);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4, 16px);
}

.timeline-title {
  font-size: var(--font-size-md, 15px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #1a1a2e);
}

.timeline-summary {
  font-size: var(--font-size-xs, 12px);
  color: var(--color-text-tertiary, #999);
}

.timeline-list {
  display: flex;
  flex-direction: column;
}

.tl-row {
  display: grid;
  grid-template-columns: 72px 24px 1fr;
  gap: 0 var(--space-2, 8px);
  cursor: pointer;
}

.tl-row:hover .tl-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* Time column */
.tl-time {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  padding-top: 10px;
  gap: 2px;
}

.tl-time-start {
  font-size: var(--font-size-sm, 13px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #333);
  line-height: 1;
}

.tl-time-end {
  font-size: 11px;
  color: var(--color-text-tertiary, #aaa);
  line-height: 1;
}

.tl-row.travel .tl-time-start {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-tertiary, #aaa);
}

.tl-row.travel .tl-time-end {
  font-size: 10px;
}

/* Connector column */
.tl-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

.tl-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 12px;
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px var(--color-primary, #667eea);
  background: var(--color-primary, #667eea);
  z-index: 1;
}

.tl-dot.attraction {
  background: #1677ff;
  box-shadow: 0 0 0 2px #1677ff;
}

.tl-dot.meal {
  background: #fa8c16;
  box-shadow: 0 0 0 2px #fa8c16;
}

.tl-dot.hotel {
  background: #52c41a;
  box-shadow: 0 0 0 2px #52c41a;
}

.tl-dot.travel {
  width: 8px;
  height: 8px;
  background: var(--color-text-disabled, #ccc);
  box-shadow: 0 0 0 2px var(--color-text-disabled, #ccc);
}

.tl-line {
  width: 2px;
  flex: 1;
  background: var(--color-border-light, #e8e8e8);
  min-height: 8px;
}

.tl-row.travel .tl-line {
  border-left: 2px dashed var(--color-border-light, #ddd);
  background: transparent;
  width: 0;
}

/* Card column */
.tl-card {
  border-radius: var(--radius-sm, 8px);
  padding: var(--space-3, 12px);
  margin-bottom: var(--space-3, 12px);
  transition: box-shadow 0.2s ease;
}

.tl-card.attraction {
  background: linear-gradient(135deg, #e6f4ff, #bae0ff);
  border-left: 3px solid #1677ff;
}

.tl-card.meal {
  background: linear-gradient(135deg, #fff7e6, #ffe7ba);
  border-left: 3px solid #fa8c16;
}

.tl-card.hotel {
  background: linear-gradient(135deg, #f6ffed, #d9f7be);
  border-left: 3px solid #52c41a;
}

.tl-card.travel {
  background: transparent;
  border-left: 2px dashed var(--color-border, #ddd);
  padding: var(--space-1, 4px) var(--space-2, 8px);
  margin-bottom: var(--space-2, 8px);
}

.tl-card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2, 6px);
}

.tl-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.tl-name {
  font-size: var(--font-size-sm, 13px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #333);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-cost {
  font-size: var(--font-size-xs, 12px);
  font-weight: var(--font-weight-semibold, 600);
  color: #fa8c16;
  flex-shrink: 0;
}

.tl-card.travel .tl-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-tertiary, #888);
}

.tl-card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-1, 4px);
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-secondary, #666);
}

.tl-card.travel .tl-card-meta {
  font-size: 10px;
  color: var(--color-text-tertiary, #aaa);
  margin-top: 2px;
}

.tl-card-detail {
  margin-top: var(--space-2, 6px);
  font-size: var(--font-size-xs, 12px);
  color: var(--color-text-secondary, #666);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 480px) {
  .tl-row {
    grid-template-columns: 56px 20px 1fr;
  }
  .tl-time-start {
    font-size: 12px;
  }
}
</style>

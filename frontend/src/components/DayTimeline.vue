<template>
  <div class="day-timeline">
    <div class="timeline-header">
      <span class="timeline-title">⏰ 时间安排</span>
      <span class="timeline-summary">
        {{ timelineItems.length }}项活动 · {{ formatTimeRange }}
      </span>
    </div>
    <div class="timeline-body">
      <div class="time-ruler">
        <div
          v-for="hour in displayHours"
          :key="hour"
          class="ruler-mark"
          :style="getHourStyle(hour)"
        >
          <span class="ruler-label">{{ formatHourLabel(hour) }}</span>
          <div class="ruler-line"></div>
        </div>
      </div>
      <div class="timeline-track">
        <div
          v-for="(item, idx) in timelineItems"
          :key="idx"
          class="timeline-item"
          :class="item.type"
          :style="getItemStyle(item)"
          @click="$emit('itemClick', item)"
        >
          <div class="item-bar">
            <div class="item-icon">{{ getIcon(item.type) }}</div>
            <div class="item-info">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-time">{{ item.startTime }} - {{ item.endTime }}</div>
            </div>
            <div v-if="item.cost" class="item-cost">¥{{ item.cost }}</div>
          </div>
          <div v-if="item.detail && item.type !== 'travel'" class="item-detail">{{ item.detail }}</div>
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
}

const props = defineProps<{
  day: DayPlan
}>()

defineEmits<{
  itemClick: [item: TimelineItem]
}>()

const BASE_START_HOUR = 6

// 首先计算原始的时间线项目（不使用 timeRange）
const rawTimelineItems = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = []
  const day = props.day
  
  // 防御性检查：确保 day 和必要属性存在
  if (!day) return items
  
  // 使用固定起始时间 8:00 (480分钟)
  let currentMinutes = 8 * 60

  const hotelName = day.hotel?.name || '酒店'
  const attractions = day.attractions || []
  const meals = day.meals || []

  const breakfast = meals.find(m => m.type === 'breakfast')
  if (breakfast) {
    const travelToBreakfast = 15
    items.push(makeItem('travel', `${hotelName} → 早餐`, currentMinutes, travelToBreakfast, undefined, '前往早餐地点'))
    currentMinutes += travelToBreakfast

    const dur = 45
    items.push(makeItem('meal', breakfast.name, currentMinutes, dur, breakfast.estimated_cost, breakfast.cuisine))
    currentMinutes += dur
  }

  const routeSegs = day.route_segments || []

  for (let i = 0; i < attractions.length; i++) {
    const attr = attractions[i]

    if (i === 0 && breakfast) {
      const travelMin = 20
      items.push(makeItem('travel', `早餐地点 → ${attr.name}`, currentMinutes, travelMin, undefined, '前往第一个景点'))
      currentMinutes += travelMin
    } else if (i > 0) {
      const prevAttr = attractions[i - 1]
      const route = routeSegs.find(s => s.from_name === prevAttr.name && s.to_name === attr.name)
      const travelMin = route ? parseDuration(route.duration) : 25
      const detail = route?.detail || `从${prevAttr.name}前往${attr.name}`
      const mode = route?.mode
      items.push(makeItem('travel', `${prevAttr.name} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode))
      currentMinutes += travelMin
    } else {
      const travelMin = 30
      items.push(makeItem('travel', `${hotelName} → ${attr.name}`, currentMinutes, travelMin, undefined, '从酒店出发'))
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
    const travelToDinner = 20
    items.push(makeItem('travel', lastAttr ? `${lastAttr.name} → 晚餐` : '前往晚餐', currentMinutes, travelToDinner, undefined, '前往餐厅'))
    currentMinutes += travelToDinner

    const dur = 90
    items.push(makeItem('meal', dinner.name, currentMinutes, dur, dinner.estimated_cost, dinner.cuisine))
    currentMinutes += dur
  }

  const travelBack = 20
  items.push(makeItem('travel', '返回酒店', currentMinutes, travelBack, undefined, '结束一天行程，返回酒店'))
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

const displayHours = computed(() => {
  const r = timeRange.value
  const hours = []
  for (let h = r.startHour; h <= r.endHour; h++) hours.push(h)
  return hours
})

function makeItem(type: TimelineItem['type'], name: string, startMin: number, dur: number, cost?: number, detail?: string, mode?: string): TimelineItem {
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
  }
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

function formatHourLabel(hour: number): string {
  return `${hour}:00`
}

function parseDuration(durStr?: string): number {
  if (!durStr) return 25
  const match = durStr.match(/(\d+)/)
  return match ? Math.max(parseInt(match[1]), 10) : 25
}

function getHourPosition(hour: number): number {
  const r = timeRange.value
  return ((hour * 60 - r.start) / r.total) * 100
}

function getHourStyle(hour: number): Record<string, string> {
  return {
    top: `${getHourPosition(hour)}%`,
  }
}

function getItemStyle(item: TimelineItem): Record<string, string> {
  const r = timeRange.value
  const top = ((item.startMinutes - r.start) / r.total) * 100
  const height = Math.max(((item.duration) / r.total) * 100, 3)
  return {
    top: `${top}%`,
    height: `${height}%`,
  }
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
</script>

<style scoped>
.day-timeline {
  background: #fafbfc;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.timeline-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
}

.timeline-summary {
  font-size: 12px;
  color: #999;
}

.timeline-body {
  position: relative;
  height: 600px;
  display: flex;
}

.time-ruler {
  width: 52px;
  flex-shrink: 0;
  position: relative;
  height: 100%;
}

.ruler-mark {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
}

.ruler-label {
  font-size: 11px;
  color: #bbb;
  width: 40px;
  text-align: right;
  padding-right: 8px;
  flex-shrink: 0;
}

.ruler-line {
  flex: 1;
  height: 1px;
  background: #eee;
}

.timeline-track {
  flex: 1;
  position: relative;
  border-left: 2px solid #e8e8e8;
  margin-left: 4px;
  height: 100%;
}

.timeline-item {
  position: absolute;
  left: 8px;
  right: 8px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  z-index: 2;
  min-height: 20px;
}

.timeline-item:hover {
  transform: scale(1.02);
  z-index: 3;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.timeline-item.attraction {
  background: linear-gradient(135deg, #e6f4ff, #bae0ff);
  border-left: 3px solid #1677ff;
}

.timeline-item.meal {
  background: linear-gradient(135deg, #fff7e6, #ffe7ba);
  border-left: 3px solid #fa8c16;
}

.timeline-item.hotel {
  background: linear-gradient(135deg, #f6ffed, #d9f7be);
  border-left: 3px solid #52c41a;
}

.timeline-item.travel {
  background: transparent;
  border-left: 2px dashed #ccc;
  min-height: 16px;
}

.timeline-item.travel .item-bar {
  padding: 2px 8px;
  min-height: 16px;
}

.timeline-item.travel .item-name {
  font-size: 11px;
  color: #888;
  font-weight: 500;
}

.timeline-item.travel .item-time {
  font-size: 10px;
  color: #aaa;
}

.item-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  min-height: 24px;
}

.item-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.item-time {
  font-size: 11px;
  color: #666;
}

.item-cost {
  font-size: 12px;
  font-weight: 600;
  color: #fa8c16;
  flex-shrink: 0;
}

.item-detail {
  padding: 0 10px 6px;
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

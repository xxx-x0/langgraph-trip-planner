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
import type { Attraction, DayPlan, Hotel, Meal } from '@/types'

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

  let currentMinutes = parseClockTime(day.day_start_time)

  const hotelName = day.hotel?.name || '酒店'
  const attractions = day.attractions || []
  const meals = day.meals || []
  const routeSegs = day.route_segments || []

  if (day.timeline_order?.length) {
    return buildSavedTimeline(day, currentMinutes)
  }

  const breakfast = meals.find(m => m.type === 'breakfast')
  if (breakfast) {
    const route = findRouteSegment(routeSegs, hotelName, breakfast.name)
    const travelMin = route ? parseDuration(route.duration) : 15
    const detail = routeDetail(route?.detail, '前往早餐地点')
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
      const detail = routeDetail(route?.detail, `前往${attr.name}`)
      const mode = route?.mode
      const distance = route?.distance
      items.push(makeItem('travel', `${breakfast.name} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
      currentMinutes += travelMin
    } else if (i > 0) {
      const prevAttr = attractions[i - 1]
      const route = findRouteSegment(routeSegs, prevAttr.name, attr.name)
      const travelMin = route ? parseDuration(route.duration) : 25
      const detail = routeDetail(route?.detail, `从${prevAttr.name}前往${attr.name}`)
      const mode = route?.mode
      const distance = route?.distance
      items.push(makeItem('travel', `${prevAttr.name} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
      currentMinutes += travelMin
    } else {
      const route = findRouteSegment(routeSegs, hotelName, attr.name)
      const travelMin = route ? parseDuration(route.duration) : 30
      const detail = routeDetail(route?.detail, '从酒店出发')
      const mode = route?.mode
      const distance = route?.distance
      items.push(makeItem('travel', `${hotelName} → ${attr.name}`, currentMinutes, travelMin, undefined, detail, mode, distance))
      currentMinutes += travelMin
    }

    const visitDur = attr.visit_duration || 120
    items.push(makeItem('attraction', attr.name, currentMinutes, visitDur, attr.ticket_price, attr.description?.slice(0, 60)))
    currentMinutes += visitDur

    if (i === Math.floor(attractions.length / 2) - 1 || (attractions.length === 1 && i === 0)) {
      const middayMeals = meals.filter(m => m.type !== 'breakfast' && m.type !== 'dinner')
      for (const meal of middayMeals) {
        const travelMin = 15
        items.push(makeItem('travel', `前往${mealDisplayName(meal)}`, currentMinutes, travelMin, undefined, '前往餐厅'))
        currentMinutes += travelMin
        const dur = mealDuration(meal)
        items.push(makeItem('meal', meal.name, currentMinutes, dur, meal.estimated_cost, meal.cuisine))
        currentMinutes += dur
      }
    }
  }

  const dinner = meals.find(m => m.type === 'dinner')
  if (dinner) {
    const lastAttr = attractions[attractions.length - 1]
    const route = lastAttr ? findRouteSegment(routeSegs, lastAttr.name, dinner.name) : undefined
    const travelToDinner = route ? parseDuration(route.duration) : 20
    const detail = routeDetail(route?.detail, '前往餐厅')
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
  const backDetail = routeDetail(routeBack?.detail, '结束一天行程，返回酒店')
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

  const startHour = Math.floor(minStart / 60)
  const endHour = Math.ceil(maxEnd / 60)

  return {
    start: minStart,
    end: maxEnd,
    total: maxEnd - minStart,
    startHour,
    endHour,
  }
})

const timelineItems = computed<TimelineItem[]>(() => {
  return rawTimelineItems.value
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

type SavedTimelineNode = {
  type: 'attraction' | 'meal' | 'hotel'
  name: string
  attraction?: Attraction
  meal?: Meal
  hotel?: Hotel
}

function buildSavedTimeline(day: DayPlan, startMinutes: number): TimelineItem[] {
  const items: TimelineItem[] = []
  const routeSegs = day.route_segments || []
  const attractionsByName = new Map((day.attractions || []).map(attr => [attr.name, attr]))
  const mealsByName = new Map((day.meals || []).map(meal => [meal.name, meal]))
  let currentMinutes = startMinutes
  let previous: SavedTimelineNode | null = null

  for (const entry of day.timeline_order || []) {
    const node = savedNodeFor(
      entry.kind,
      entry.ref_name,
      attractionsByName,
      mealsByName,
      day.hotel,
    )
    if (!node) continue

    if (node.type === 'hotel' && entry.phase === 'start') {
      previous = node
      continue
    }

    if (previous && previous.name !== node.name) {
      const route = findRouteSegment(routeSegs, previous.name, node.name)
      const travelMin = route ? parseDuration(route.duration) : 20
      const travelName = node.type === 'hotel'
        ? '返回酒店'
        : `${previous.name} → ${node.name}`
      const detail = routeDetail(route?.detail, (
        node.type === 'hotel'
          ? '结束一天行程，返回酒店'
          : `前往${node.name}`
      ))
      items.push(makeItem(
        'travel',
        travelName,
        currentMinutes,
        travelMin,
        undefined,
        detail,
        route?.mode,
        route?.distance,
      ))
      currentMinutes += travelMin
    }

    if (node.type === 'attraction' && node.attraction) {
      const attraction = node.attraction
      const duration = attraction.visit_duration || 120
      items.push(makeItem(
        'attraction',
        attraction.name,
        currentMinutes,
        duration,
        attraction.ticket_price,
        attraction.description?.slice(0, 60),
      ))
      currentMinutes += duration
    } else if (node.type === 'meal' && node.meal) {
      const duration = mealDuration(node.meal)
      items.push(makeItem(
        'meal',
        node.meal.name,
        currentMinutes,
        duration,
        node.meal.estimated_cost,
        node.meal.cuisine,
      ))
      currentMinutes += duration
    } else if (node.type === 'hotel' && node.hotel) {
      items.push(makeItem(
        'hotel',
        node.hotel.name,
        currentMinutes,
        30,
        node.hotel.estimated_cost,
        node.hotel.address,
      ))
      currentMinutes += 30
    }

    previous = node
  }

  return items
}

function savedNodeFor(
  kind: string,
  name: string,
  attractionsByName: Map<string, Attraction>,
  mealsByName: Map<string, Meal>,
  hotel?: Hotel,
): SavedTimelineNode | null {
  if (kind === 'attraction') {
    const attraction = attractionsByName.get(name)
    return attraction ? { type: 'attraction', name, attraction } : null
  }
  if (kind === 'meal') {
    const meal = mealsByName.get(name)
    return meal ? { type: 'meal', name, meal } : null
  }
  if (kind === 'hotel' && hotel) {
    return { type: 'hotel', name: hotel.name, hotel }
  }
  return null
}

function mealDuration(meal: Meal): number {
  if (meal.type === 'breakfast') return 45
  if (meal.type === 'dinner') return 90
  if (meal.type === 'snack' || meal.type === 'dessert' || meal.type === 'cafe') return 35
  return 60
}

function mealDisplayName(meal: Meal): string {
  if (meal.type === 'breakfast') return '早餐'
  if (meal.type === 'lunch') return '午餐'
  if (meal.type === 'dinner') return '晚餐'
  return '用餐'
}

function routeDetail(detail: string | undefined, fallback: string): string {
  const text = detail?.trim()
  if (!text) return fallback
  if (
    text.includes("'transits': []") ||
    text.includes('"transits": []') ||
    text.startsWith("{'origin'") ||
    text.startsWith('{"origin"')
  ) {
    return fallback
  }
  return text
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

function parseClockTime(value?: string): number {
  const match = value?.match(/^(\d{1,2}):(\d{2})$/)
  if (!match) return 8 * 60
  const hours = Math.min(Math.max(Number(match[1]), 0), 23)
  const minutes = Math.min(Math.max(Number(match[2]), 0), 59)
  return hours * 60 + minutes
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
  background: var(--white);
  border-radius: 0;
  padding: var(--space-4);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: var(--border-2) solid var(--border);
}

.timeline-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-black);
  text-transform: uppercase;
  color: var(--foreground);
  letter-spacing: 0.05em;
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
  border-radius: 0;
  padding: var(--space-3, 12px);
  margin-bottom: var(--space-3, 12px);
  transition: all var(--transition-fast);
  border: var(--border-2) solid var(--border);
}

.tl-card:hover {
  box-shadow: 4px 4px 0px 0px var(--border);
}

.tl-card.attraction {
  background: var(--white);
  border-left: 4px solid var(--primary-blue);
}

.tl-card.meal {
  background: var(--white);
  border-left: 4px solid var(--primary-yellow);
}

.tl-card.hotel {
  background: var(--white);
  border-left: 4px solid var(--primary-red);
}

.tl-card.travel {
  background: transparent;
  border: none;
  border-left: 2px dashed var(--border);
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
  font-weight: var(--font-black);
  text-transform: uppercase;
  color: var(--foreground);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0.03em;
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

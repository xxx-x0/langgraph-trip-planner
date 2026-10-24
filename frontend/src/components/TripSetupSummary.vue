<template>
  <section class="trip-setup-summary" aria-label="本次预算与入住条件">
    <div><span>同行</span><strong>{{ request.companions?.count || 1 }} 人</strong></div>
    <div><span>整趟总预算</span><strong>{{ request.budget ? `¥${request.budget.toLocaleString()}` : '未设上限' }}</strong></div>
    <div v-if="request.travel_days > 1"><span>入住配置</span><strong v-if="request.hotel_occupancy">{{ request.hotel_occupancy.room_count }} 间房 · 每间 {{ request.hotel_occupancy.adults_per_room }} 成人<span v-if="request.hotel_occupancy.children_ages.length">、{{ request.hotel_occupancy.children_ages.length }} 儿童</span></strong><strong v-else>待确认</strong></div>
    <p>预算含往返交通、住宿、餐饮与游玩；已填条件不代表费用齐全或已预订。房型与报价以酒店卡片为准。</p>
  </section>
</template>
<script setup lang="ts">
import type { TripFormData } from '@/types'
defineProps<{request:Pick<TripFormData,'companions'|'budget'|'travel_days'|'hotel_occupancy'>}>()
</script>
<style scoped>
.trip-setup-summary{display:flex;flex-wrap:wrap;gap:18px 36px;border:1px solid var(--color-border);border-radius:16px;padding:20px 24px;margin-bottom:20px;background:var(--color-bg-primary);color:var(--color-text-primary)}.trip-setup-summary>div{display:flex;flex-direction:column;gap:8px}.trip-setup-summary>div>span{font-size:11px;color:var(--color-text-secondary)}strong{font-size:15px;font-weight:500}.trip-setup-summary p{flex-basis:100%;margin:0;font-size:11px;line-height:1.7;color:var(--color-text-secondary)}
@media(max-width:600px){.trip-setup-summary{padding:18px;gap:16px 24px}}
</style>

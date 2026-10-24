<template>
  <div class="tab-overview">
    <section class="day-directory">
      <div class="section-heading"><div><p class="eyebrow">THE DAYS AHEAD</p><h2>每天，慢慢展开</h2></div><span>{{ tripPlan.days.length }} 天的旅行安排</span></div>
      <div class="day-cards">
        <button v-for="(day, index) in tripPlan.days" :key="day.date || index" class="day-card" @click="$emit('openDay', index)">
          <span class="day-card-top"><span class="day-index">DAY {{ String(index + 1).padStart(2, '0') }}</span><span>{{ day.date?.slice(5).replace('-', ' / ') }}</span></span>
          <strong>{{ day.attractions?.map(a => a.name).join(' · ') || '当天尚未安排景点' }}</strong>
          <span class="day-facts">{{ day.attractions?.length || 0 }} 个景点 · {{ day.meals?.length || 0 }} 次用餐<span v-if="day.overnight_stay === false"> · 离开日</span></span>
          <span class="day-stay">{{ day.hotel?.name || day.accommodation || '住宿待确认' }}</span>
          <span class="day-card-bottom">查看当天时间轴 <span aria-hidden="true">↗</span></span>
        </button>
      </div>
    </section>
    <div class="overview-bottom">
      <section class="overview-note">
        <p class="eyebrow">BEFORE YOU GO</p><h3>出发前，再确认一下</h3>
        <template v-if="pending.length">
          <p class="pending-intro">每日安排还有 {{ pending.length }} 项待确认，费用缺项可在「费用明细」查看。</p>
          <ul class="pending-preview"><li v-for="item in pending.slice(0, 3)" :key="item">{{ item }}</li></ul>
          <details v-if="pending.length > 3" :open="expanded"><summary>查看其余 {{ pending.length - 3 }} 项</summary><ul><li v-for="item in pending.slice(3)" :key="item">{{ item }}</li></ul></details>
        </template>
        <p v-else class="pending-intro">当前记录未列出待确认项，出发前仍请核对营业时间与预订信息。</p>
      </section>
      <section class="overview-note reading-note">
        <p class="eyebrow">TRAVEL NOTES</p><h3>把细节留在手边</h3>
        <p>每日安排、往返交通和费用分别查看，展开卡片就能找到对应细节。</p>
        <details v-if="tripPlan.overall_suggestions" :open="expanded">
          <summary>完整行程说明</summary>
          <div class="suggestions-content">{{ tripPlan.narrative_source === 'itinerary_facts_v1' ? tripPlan.overall_suggestions : '旧版建议尚未核对当前行程，请以安排和费用数据为参考。' }}</div>
        </details>
        <p class="saved-note">这里展示的是保存时的安排与参考报价。</p>
      </section>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { TripPlan } from '@/types'
const props = defineProps<{ tripPlan: TripPlan; expanded?: boolean }>()
defineEmits<{ openDay: [index: number] }>()
const pending = computed(() => [...new Set((props.tripPlan.days || []).flatMap(day => day.pending_confirmations || []))])
</script>
<style scoped>
.tab-overview { color: var(--color-text-primary); }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin: 6px 0 20px; }
.eyebrow { font-size: 10px; letter-spacing: .16em; color: var(--color-primary); margin: 0 0 8px; }
h2 { font-size: 24px; font-weight: 500; margin: 0; letter-spacing: -.03em; }
.section-heading > span { font-size: 12px; color: var(--color-text-secondary); }
.day-cards { display: grid; grid-template-columns: repeat(auto-fit,minmax(min(100%,270px),1fr)); gap: 16px; }
.day-card { display: flex; flex-direction: column; gap: 14px; text-align: left; color: var(--color-text-primary); background: var(--color-bg-primary); border: 1px solid var(--color-border); border-radius: 18px; padding: 24px; cursor: pointer; transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease; min-width: 0; }
.day-card:hover { transform: translateY(-3px); border-color: var(--color-primary); box-shadow: 0 10px 25px #00000009; }
.day-card:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 3px; }
.day-card-top { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--color-text-secondary); }
.day-index { letter-spacing: .12em; font-size: 11px; color: var(--color-primary); }
.day-card strong { font-size: 21px; font-weight: 500; line-height: 1.5; overflow-wrap: anywhere; }
.day-facts,.day-stay { font-size: 12px; color: var(--color-text-secondary); line-height: 1.7; }
.day-stay { flex: 1; }
.day-card-bottom { display: flex; justify-content: space-between; border-top: 1px solid var(--color-border); padding-top: 16px; margin-top: 4px; font-size: 12px; color: var(--color-primary); }
.overview-bottom { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; margin-top: 24px; }
.overview-note { background: var(--color-bg-secondary); border: 1px solid var(--color-border); border-radius: 18px; padding: 24px; min-width: 0; }
h3 { font-size: 17px; font-weight: 500; margin: 0 0 12px; }
.pending-intro,.reading-note > p:not(.eyebrow),li { font-size: 13px; color: var(--color-text-secondary); line-height: 1.8; }
ul { padding-left: 18px; margin: 12px 0; }
li { margin: 6px 0; overflow-wrap: anywhere; }
details { border-top: 1px solid var(--color-border); margin-top: 16px; padding-top: 14px; }
summary { cursor: pointer; color: var(--color-primary); font-size: 13px; }
.suggestions-content { white-space: pre-line; overflow-wrap: anywhere; font-size: 13px; line-height: 1.9; margin-top: 16px; color: var(--color-text-primary); }
.saved-note { margin: 22px 0 0; }
@media(max-width:700px) { .overview-bottom { grid-template-columns: 1fr; }.section-heading { align-items: start; }.section-heading > span { max-width: 90px; text-align: right; }.day-card,.overview-note { padding: 20px; } }
@media(prefers-reduced-motion:reduce) { .day-card { transition: none; }.day-card:hover { transform: none; } }
</style>

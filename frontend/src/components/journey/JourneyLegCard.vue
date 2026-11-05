<template>
  <article class="ticket-card" :aria-label="`${label} · ${leg?.service_number || '班次待定'}`">
    <header>
      <span class="ticket-direction">
        <svg v-if="leg?.mode==='flight'" viewBox="0 0 24 24" aria-hidden="true"><path d="m21 3-7 18-3-8-8-3 18-7ZM11 13l5-5" /></svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="15" rx="4"/><path d="M5 11h14M9 3v8M8 21l2-3m6 3-2-3M8 15h1m6 0h1"/></svg>
        {{ label }}<span class="ticket-date">{{ dateLabel(leg?.departure_time) }}</span>
      </span>
      <span class="ticket-status" :class="{booked:leg?.booking_status==='booked'}">{{leg?.booking_status==='booked'?'已订票':leg?'待预订':'待选择'}}</span>
    </header>
    <div v-if="leg" class="ticket-route">
      <div class="ticket-stop"><strong>{{leg.departure_time?.slice(11,16)||'—'}}</strong><span>{{leg.departure_station||'出发站待确认'}}</span></div>
      <div class="ticket-track"><b>{{leg.service_number||'班次待定'}}</b><span aria-hidden="true"><i></i><i></i></span><small>{{leg.seat_class|| (leg.mode==='flight'?'飞机':'铁路')}}</small></div>
      <div class="ticket-stop arrival"><strong>{{leg.arrival_time?.slice(11,16)||'—'}}</strong><span>{{leg.arrival_station||'到达站待确认'}}</span><small v-if="leg.arrival_time?.slice(0,10)!==leg.departure_time?.slice(0,10)">{{dateLabel(leg.arrival_time)}}抵达</small></div>
    </div>
    <div v-else class="ticket-empty"><strong>还没有{{label}}班次</strong><span>选好后，会一起衔接当天的游玩时间。</span></div>
    <footer v-if="leg"><span>{{leg.passengers||1}} 人同行</span><span v-if="leg.ticket_total!=null">全体票价 <b>{{leg.currency==='CNY'?'¥':leg.currency+' '}}{{leg.ticket_total.toLocaleString()}}</b></span><span v-else class="ticket-unknown">票价待核对</span></footer>
  </article>
</template>

<script setup lang="ts">
import type {JourneyLeg} from '@/types'
defineProps<{leg?:JourneyLeg|null;label:string}>()
function dateLabel(value?:string){return value ? `${Number(value.slice(5,7))}月${Number(value.slice(8,10))}日` : ''}
</script>

<style scoped>
.ticket-card{min-width:0;border:1px solid var(--color-border);border-radius:16px;background:var(--color-bg-primary);color:var(--color-text-primary);overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:17px 20px 0;font-size:13px}.ticket-direction{display:flex;gap:8px;align-items:center;font-weight:600}.ticket-direction svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;color:var(--color-primary)}.ticket-date{font-size:12px;font-weight:400;color:var(--color-text-secondary);margin-left:4px}.ticket-status{font-size:11px;white-space:nowrap;padding:4px 8px;background:var(--color-bg-secondary);border-radius:6px;color:var(--color-text-secondary)}.ticket-status.booked{background:color-mix(in srgb,var(--color-primary) 10%,transparent);color:var(--color-primary)}
.ticket-route{display:grid;grid-template-columns:minmax(0,1fr) minmax(72px,.65fr) minmax(0,1fr);align-items:start;gap:14px;padding:24px 20px 20px}.ticket-stop{display:flex;flex-direction:column;gap:7px;min-width:0}.ticket-stop strong{font-size:29px;font-weight:600;line-height:1.1;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.ticket-stop span{font-size:13px;overflow-wrap:anywhere}.arrival{text-align:right}.ticket-stop small{font-size:11px;color:var(--color-text-secondary)}.ticket-track{display:flex;flex-direction:column;align-items:center;gap:7px;min-width:0}.ticket-track b{font-size:12px;line-height:1.4;font-weight:500}.ticket-track>span{display:flex;justify-content:space-between;align-items:center;width:100%;height:1px;background:var(--color-border-strong);margin:3px 0 1px}.ticket-track i{width:5px;height:5px;border:1px solid var(--color-border-strong);border-radius:50%;background:var(--color-bg-primary)}.ticket-track small{font-size:10px;color:var(--color-text-secondary);text-align:center}
footer{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px dashed var(--color-border);padding:10px 20px;font-size:11px;color:var(--color-text-secondary);background:color-mix(in srgb,var(--color-bg-secondary) 55%,transparent)}footer b{color:var(--color-text-primary);font-weight:500;font-size:13px}.ticket-empty{display:flex;flex-direction:column;gap:10px;padding:30px 20px}.ticket-empty strong{font-size:16px;font-weight:500}.ticket-empty span{font-size:12px;color:var(--color-text-secondary)}
@media(max-width:480px){.ticket-route{gap:12px;padding:20px 16px}.ticket-stop strong{font-size:28px}header{padding:16px 16px 0}footer{padding:10px 16px}}
</style>

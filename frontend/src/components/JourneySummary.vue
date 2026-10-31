<template>
 <section class="journey-summary">
  <header class="journey-heading"><p class="eyebrow">ON THE WAY</p><h2>往返交通</h2><p>{{ journey ? `${journey.origin_city} → ${city} → ${journey.return_city}` : '抵离交通尚未填写；首末日时间暂定，往返费用尚未计入。' }}</p></header>
  <template v-if="journey">
   <p v-if="days?.length" class="journey-capacity">整趟 {{days.length}} 天（含去返程）；按08:00—22:00估算，目的地有 {{capacitySummary.full}} 个完整可用日、{{capacitySummary.partial}} 个部分可用日、{{capacitySummary.travel}} 个在途或暂无游玩时间的日期。{{journey.planning && (!journey.outbound || !journey.inbound)?'部分边界仍按本次预留暂定。':''}}</p>
   <div class="journey-legs">
    <article v-for="item in directions" :key="item.key" class="journey-leg">
     <template v-if="journey[item.key]">
      <div class="leg-heading"><span>{{ item.label }} · {{ journey[item.key]!.service_number || '班次待定' }}</span><span class="booking-status">{{ journey[item.key]!.booking_status === 'booked' ? '已订时间约束' : '暂定班次' }}</span></div>
      <div class="leg-route">
       <div><strong>{{ journey[item.key]!.departure_time.slice(11, 16) }}</strong><span>{{ journey[item.key]!.departure_time.slice(0, 10) }}</span><b>{{ journey[item.key]!.departure_station || '出发站待确认' }}</b></div>
       <span class="route-arrow" aria-hidden="true">→</span>
       <div><strong>{{ journey[item.key]!.arrival_time.slice(11, 16) }}</strong><span>{{ journey[item.key]!.arrival_time.slice(0, 10) }}</span><b>{{ journey[item.key]!.arrival_station || '抵达站待确认' }}</b></div>
      </div>
      <p class="leg-timezone">出发 {{ journey[item.key]!.departure_timezone }} · 到达 {{ journey[item.key]!.arrival_timezone }}</p>
      <div class="leg-price"><span>全体 {{ journey[item.key]!.passengers }} 人票价</span><strong>{{ journey[item.key]!.ticket_total ?? '未知' }} <small>{{ journey[item.key]!.currency }}</small></strong></div>
      <p class="leg-extra">额外费用：{{ extraCostLabel(journey[item.key]!) }}</p>
      <p class="leg-extra">{{ sources[journey[item.key]!.price_source] }}</p>
      <details :open="expanded"><summary>接驳时间、报价来源与票务条件</summary>
     <p v-if="timings[item.key]">班次运行 {{ timings[item.key].duration_minutes }} 分钟；含两端接驳、候车／行李和住宿缓冲约 {{ timings[item.key].door_to_door_minutes }} 分钟。缓冲是可编辑的预留，不是实时路况。预计从 {{ timings[item.key].door_departure }} 至 {{ timings[item.key].door_arrival }}。</p>
     <p>全体 {{ journey[item.key]!.passengers }} 人票价：{{ journey[item.key]!.ticket_total ?? '未知' }} {{ journey[item.key]!.currency }}；额外费用：{{ extraCostLabel(journey[item.key]!) }}。{{ sources[journey[item.key]!.price_source] }}，{{ journey[item.key]!.price_note || '条件未核实' }}；记录时间 {{ journey[item.key]!.quoted_at || '未提供' }}。</p>
     <p v-if="journey[item.key]!.quote_expires_at">来源标注的失效时间：{{journey[item.key]!.quote_expires_at}}（{{journey[item.key]!.departure_timezone}}）。{{(days||[]).flatMap(d=>d.travel_window?.unknown_cost_items||[]).filter(n=>n.includes(item.label+'报价已过期')).join('；')}}</p>
     <p v-if="journey[item.key]!.extra_costs">额外费用明细：未含税费 {{journey[item.key]!.extra_costs!.taxes ?? '未知'}}；行李 {{journey[item.key]!.extra_costs!.baggage ?? '未知'}}；两端接驳 {{journey[item.key]!.extra_costs!.transfers ?? '未知'}}；途中住宿 {{journey[item.key]!.extra_costs!.overnight ?? '未知'}}（全体同行总额）。</p>
     <p v-if="journey[item.key]!.seat_class || journey[item.key]!.baggage_policy || journey[item.key]!.refund_policy">{{journey[item.key]!.seat_class || '席别待确认'}}；行李：{{journey[item.key]!.baggage_policy || '待确认'}}；退改：{{journey[item.key]!.refund_policy || '待确认'}}。</p>
      </details>
     </template>
     <template v-else><h3>{{ item.label }}</h3><p>尚未填写，时间和费用暂定。</p><p v-if="journey.planning">{{reservationLabel(item.key)}}</p></template>
    </article>
   </div>
   <details v-if="days?.length" class="journey-windows" :open="expanded"><summary>每日目的地可用时间 · {{ journey.destination_timezone }}</summary><div class="window-grid"><p v-for="day in days" :key="day.date"><span>{{ day.date }}</span><strong>{{ !day.travel_window ? '尚未核对' : day.travel_window.unavailable ? '在途／暂无游玩时间' : timeLabel(day.travel_window.start_minutes ?? 0)+'—'+timeLabel(day.travel_window.end_minutes ?? 1440) }}</strong><small>{{ day.travel_window?.provisional ? '暂定' : '' }}</small></p></div></details>
  </template>
 </section>
</template>
<script setup lang="ts">
import {extraCostLabel} from '@/utils/journeyCosts'
import type {Journey} from '@/types'
import {computed} from 'vue'
const props=defineProps<{expanded?:boolean;journey?:Journey|null;city:string;days?:Array<{date:string;travel_window?:Record<string,any>}>}>()
const timings=computed<Record<string,any>>(()=>Object.fromEntries((props.days||[]).flatMap(d=>d.travel_window?.legs||[]).map(l=>[l.direction,l])))
const capacitySummary=computed(()=>{const result={full:0,partial:0,travel:0};for(const day of props.days||[]){const w=day.travel_window||{};const minutes=w.unavailable?0:Math.max(0,Math.min(1320,w.end_minutes??1440)-Math.max(480,w.start_minutes??0));if(!minutes)result.travel++;else if(minutes>=840)result.full++;else result.partial++}return result})
function reservationLabel(key:'outbound'|'inbound'){const p=props.journey?.planning;if(!p)return '';const policy=key==='outbound'?p.arrival_policy:p.departure_policy;return policy==='travel_day'?(key==='outbound'?'首日':'末日')+'已暂留给交通，不作为完整游玩日；实际班次待定。':policy==='time_window'?'按本次预计活动边界预留：'+((key==='outbound'?p.ready_at:p.leave_by)||'待填写').replace('T',' ')+'，尚非实际班次。':'本方向尚未预留交通占用时间。'}
function timeLabel(n:number){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
const directions=[{key:'outbound' as const,label:'去程'},{key:'inbound' as const,label:'返程'}]
const sources={unknown:'价格未知',user_estimate:'用户估算',user_quote:'用户记录报价，需重新核价',paid:'用户记录已付金额'}
</script>
<style scoped>
.journey-summary { padding: 24px; background: var(--color-bg-primary); color: var(--color-text-primary); border: 1px solid var(--color-border); border-radius: 18px; }
.journey-heading { margin-bottom: 22px; }
.eyebrow { color: var(--color-primary); font-size: 10px; letter-spacing: .16em; margin: 0 0 8px; }
h2 { margin: 0 0 8px; font-size: 24px; font-weight: 500; }
.journey-heading > p:last-child { color: var(--color-text-secondary); font-size: 13px; }
.journey-legs { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 20px; }
.journey-leg { padding: 22px; background: var(--color-bg-secondary); border-radius: 14px; min-width: 0; }
.leg-heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 13px; color: var(--color-primary); }
.booking-status { font-size: 11px; padding: 4px 8px; border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text-secondary); }
.leg-route { display: grid; grid-template-columns: 1fr 24px 1fr; align-items: start; gap: 8px; margin: 26px 0 12px; }
.leg-route > div { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.leg-route > div:last-child { text-align: right; }
.leg-route strong { font-size: 32px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.2; }
.leg-route span { font-size: 11px; color: var(--color-text-secondary); }
.leg-route b { font-size: 13px; font-weight: 400; overflow-wrap: anywhere; }
.leg-route .route-arrow { font-size: 20px; padding-top: 6px; color: var(--color-primary); }
.leg-timezone { color: var(--color-text-secondary); font-size: 11px; }
.leg-price { display: flex; justify-content: space-between; gap: 12px; align-items: center; border-top: 1px solid var(--color-border); padding-top: 16px; margin-top: 18px; }
.leg-price > span { font-size: 12px; color: var(--color-text-secondary); }
.leg-price strong { font-size: 22px; font-weight: 500; }.leg-price small { font-size: 11px; }
.leg-extra { font-size: 12px; color: var(--color-text-secondary); }
details { margin-top: 18px; border-top: 1px solid var(--color-border); padding-top: 14px; }summary { cursor: pointer; color: var(--color-primary); font-size: 12px; line-height: 1.8; }
p { overflow-wrap: anywhere; line-height: 1.8; }details p { font-size: 12px; color: var(--color-text-secondary); margin-top: 12px; }
.window-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 12px; }.window-grid p { display: flex; flex-direction: column; gap: 5px; }.window-grid strong { font-size: 15px; color: var(--color-text-primary); font-weight: 500; }
@media(max-width:800px) { .journey-legs { grid-template-columns: 1fr; } }
@media(max-width:480px) { .journey-summary { padding: 18px; }.journey-leg { padding: 16px; }.leg-route strong { font-size: 28px; } }
</style>

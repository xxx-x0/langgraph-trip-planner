<template>
  <section class="travel-preview" aria-label="交通与日程调整预览">
    <header class="proposal-heading">
      <div><span class="proposal-label"><i></i>调整预览 · 尚未保存</span><h3>{{preview.coordination?'看看整趟的新安排':'看看这份衔接方案'}}</h3><p>{{preview.coordination?'景点、用餐和休息一起协调，确认后更新每天的安排。':'核对班次与活动变化，确认后更新每天的安排。'}}</p></div>
      <span v-if="preview.unassigned_attractions?.length" class="proposal-status warning">{{preview.unassigned_attractions.length}} 个景点待安排</span>
      <span v-else-if="preview.adjustment_id" class="proposal-status">{{scheduledCount}} 个景点 · {{days.length}} 天</span>
    </header>

    <div class="proposal-tickets" aria-label="即将保存的去返程">
      <JourneyLegCard :leg="journey?.outbound" label="去程" />
      <JourneyLegCard :leg="journey?.inbound" label="返程" />
    </div>

    <section v-if="preview.coordination" class="pace-summary" aria-label="调整后的旅行节奏">
      <div class="proposal-section-heading"><h4>时间留得更从容</h4><span>21:00 前收尾 · 预留休息 · 返程多留至少 30 分钟</span></div>
      <div class="pace-days"><article v-for="day in preview.coordination.days" :key="day.date">
        <span>{{shortDate(day.date)}}</span><strong>{{day.start_time}}—{{day.end_time}}</strong>
        <p>游玩 {{durationLabel(day.visit_minutes)}} · 用餐 {{day.meal_count}} 顿</p>
        <div><span>休息 {{day.rest_minutes}} 分钟</span><span v-if="day.return_margin_minutes!=null">接驳外余量 {{day.return_margin_minutes}} 分钟</span></div>
      </article></div>
      <p class="pace-note" v-if="preview.unassigned_attractions?.length">{{preview.unassigned_attractions.length}} 个景点暂留待安排，完整游览时长仍保留。以后可以换日期加入。</p>
    </section>

    <div class="proposal-section-heading"><h4>每天还可以怎么玩</h4><span>点开日期，查看具体时间轴</span></div>
    <JourneyDayWindows :days="windows" interactive :active-date="activeDate" @select="activeDate=activeDate===$event?'':$event" />
    <div v-if="activeDate" class="proposal-timeline">
      <header><strong>{{shortDate(activeDate)}} · {{activeDetail?'调整后时间安排':'当天安排'}} </strong><button type="button" @click="activeDate=''" aria-label="收起时间轴">收起 ↑</button></header>
      <ol v-if="activeDetail?.timeline_schedule?.length">
        <li v-for="(item,index) in activeDetail.timeline_schedule" :key="index" :class="item.kind">
          <time>{{item.start_time}}<small>{{item.end_time}}</small></time><span class="timeline-dot" aria-hidden="true"></span><div><span>{{kindLabel(item.kind)}}</span><strong>{{item.ref_name}}</strong></div>
        </li>
      </ol>
      <p v-else>{{activeDetail?'当天没有已安排活动。':preview.adjustment_id?'当天尚未生成日程，路线和用餐仍待核对。':'本次先同步可容纳的时刻，保存后可在当天安排中查看时间轴。'}}</p>
    </div>

    <section v-if="preview.meal_recovery?.length" class="proposal-meals" aria-label="重新推荐的用餐">
      <div class="proposal-section-heading"><h4>用餐也一起衔接</h4><span>保留景点时长与手动选店</span></div>
      <div class="meal-proposals"><article v-for="meal in preview.meal_recovery" :key="meal.date+meal.slot" class="meal-proposal" :class="{pending:meal.status!=='scheduled'}">
        <header><span>{{shortDate(meal.date)}} · {{meal.slot==='lunch'?'午餐':'晚餐'}}</span><time v-if="meal.status==='scheduled'">{{meal.start_time}}—{{meal.end_time}}</time><span v-else class="meal-pending-label">尚未排入</span></header>
        <h5>{{meal.status==='scheduled'?meal.restaurant:'这顿还需要更多时间或候选'}}</h5>
        <p v-if="meal.old_restaurant" class="meal-replaced">原安排：{{meal.old_restaurant}}</p><p>{{meal.reason}}</p>
        <p v-if="mealTimingNote(meal)" class="meal-timing-note">{{mealTimingNote(meal)}}</p>
        <small v-if="meal.status==='scheduled'">{{meal.selection_method==='ai'?'AI 选店':'规则推荐'}} · 实际路线已核对 · 营业与价格以门店为准</small>
        <details v-if="meal.cautions?.length"><summary>餐厅信息待核对</summary><ul><li v-for="note in meal.cautions" :key="note">{{note}}</li></ul></details>
      </article></div>
    </section>

    <section v-if="moves.length||notices.length||preview.unassigned_attractions?.length||conflicts.length" class="proposal-changes" aria-label="需要核对的调整">
      <div class="proposal-section-heading"><h4>这次调整了什么</h4><span>游览时长、锁定与预约继续保留</span></div>
      <div v-for="move in moves" :key="move.name" class="change-row moved"><span class="change-symbol" aria-hidden="true">↗</span><div><strong>{{move.name}}</strong><p>{{shortDate(move.from)}} <span>→</span> {{shortDate(move.to)}}<small>保留原游览时长</small></p></div><span class="change-type">跨日移动</span></div>
      <div v-for="(note,index) in notices" :key="index" class="change-row" :class="note.attention?'attention':'changed'"><span class="change-symbol" aria-hidden="true">{{note.attention?'−':'↻'}}</span><div><strong>{{note.date?shortDate(note.date)+' · ':''}}{{note.heading}}</strong><p>{{note.text}}</p></div></div>
      <div v-if="preview.unassigned_attractions?.length" class="pending-note"><strong>{{preview.unassigned_attractions.map((item:any)=>item.name).join('、')}}</strong><p>暂时放不下，已保留在待安排清单。保存后可换日期安排。</p></div>
      <div v-for="(conflict,index) in conflicts" :key="index" class="conflict-note" role="alert"><strong>{{shortDate(conflict.date)}} · 仍需调整</strong><p>{{conflict.text}}</p></div>
    </section>
    <p v-else-if="!preview.meal_recovery?.length" class="unchanged-note"><span aria-hidden="true">✓</span> 本次没有列出活动移动或取消。</p>

    <details class="proposal-evidence">
      <summary><span>费用、接驳与完整调整说明</span><span>{{costLabel}} <i aria-hidden="true">＋</i></span></summary>
      <div class="evidence-content">
        <p v-if="preview.budget">整趟已知费用 <strong>¥{{preview.budget.total?.toLocaleString()}}</strong> · {{preview.budget.is_within_budget===false?'已超预算':preview.budget.is_complete?'按当前已填费用计算，仍需核价':'仍有费用待核对'}}</p>
        <p>票价按全体同行人数记录，不再重复乘人数。未知费用尚未计入，接驳为可编辑的预留。</p>
        <ul v-if="preview.changes?.length"><li v-for="(change,index) in preview.changes" :key="index">{{change}}</li></ul>
        <div v-for="day in preview.impacts||[]" :key="day.date" class="evidence-day"><strong>{{shortDate(day.date)}}</strong><p v-for="note in day.window?.notes||[]" :key="note">{{note}}</p><p v-if="day.window?.overnight_stay!=null">{{day.window.overnight_stay?'目的地住宿计一晚':'当天不新增住宿'}}</p><p v-for="note in day.changes||[]" :key="note">{{note}}</p></div>
        <details v-if="missingCosts.length"><summary>待核对费用 {{missingCosts.length}} 项</summary><ul><li v-for="item in missingCosts" :key="item">{{item}}</li></ul></details>
      </div>
    </details>

    <footer class="proposal-actions">
      <label v-if="preview.adjustment_id" class="proposal-ack"><input type="checkbox" :checked="acknowledged" :disabled="disabled" @change="emit('acknowledge',($event.target as HTMLInputElement).checked)" /><span>我已核对以上调整<small>包括活动移动、取消和待安排项</small></span></label>
      <p v-else class="proposal-ready">确认后，交通与日程一起更新。</p>
      <div class="proposal-buttons"><button type="button" class="secondary-action" :disabled="disabled" @click="emit('cancel')">暂不采用</button><button type="button" class="primary-action" :disabled="disabled||!!preview.adjustment_id&&!acknowledged" @click="emit('save')">{{disabled?'正在保存…':'确认并保存'}}<span aria-hidden="true"> →</span></button></div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import type {Journey} from '@/types'
import JourneyLegCard from './JourneyLegCard.vue'
import JourneyDayWindows from './JourneyDayWindows.vue'
const props=defineProps<{preview:any;journey?:Journey|null;days:any[];originalDetails:any[];acknowledged:boolean;disabled:boolean}>()
const emit=defineEmits<{(e:'acknowledge',value:boolean):void;(e:'save'):void;(e:'cancel'):void}>()
const activeDate=ref('')
watch(()=>props.preview,()=>activeDate.value='')
const windows=computed(()=>(props.preview.impacts||[]).map((impact:any,index:number)=>({date:impact.date,window:impact.window,activityCount:props.preview.days_detail?.[index]?.attractions?.length??impact.activities?.length})))
const activeDetail=computed(()=>props.preview.days_detail?.[props.days.findIndex(day=>day.date===activeDate.value)])
const scheduledCount=computed(()=>(props.preview.days_detail||[]).reduce((n:number,day:any)=>n+(day?.attractions?.length||0),0))
const moves=computed<Array<{name:string;from:string;to:string}>>(()=>{
  const before=new Map<string,string>()
  props.days.forEach((day,index)=>(props.originalDetails?.[index]?.attractions||day.attractions||[]).forEach((a:any)=>before.set(a.name,day.date)))
  return (props.preview.days_detail||[]).flatMap((day:any,index:number)=>(day?.attractions||[]).filter((a:any)=>before.has(a.name)&&before.get(a.name)!==(day.date||props.days[index]?.date)).map((a:any)=>({name:a.name,from:before.get(a.name)!,to:day.date||props.days[index]?.date})))
})
const notices=computed(()=>{
  const changes=[...(props.preview.changes||[]),...(props.preview.impacts||[]).flatMap((day:any)=>day.changes||[])] as string[]
  return [...new Set(changes)].filter(text=>!text.includes('按交通窗口核对原选景点')&&!(props.preview.meal_recovery?.length&&/重新推荐[午晚]餐：/.test(text))&&!moves.value.some(move=>text.includes(move.name)&&/移至|移出原日/.test(text))).map(text=>{
    const match=text.match(/^(\d{4}-\d{2}-\d{2})[：:]/)
    const detail=match?text.slice(match[0].length).trim():text
    const meal=detail.match(/^移除本城用餐 (.+?)；/)
    const attention=/移除|取消|不再安排/.test(text)
    return {date:match?.[1],text:meal?`${meal[1]}未能匹配合适时段，已从当天安排移出。保存后可使用「AI 推荐用餐」重新查找。`:detail,
      heading:meal?'这顿用餐尚未安排':attention?'需要留意':'时间调整',attention}
  })
})
const conflicts=computed(()=>(props.preview.impacts||[]).flatMap((day:any)=>(day.conflicts||[]).map((text:string)=>({date:day.date,text}))))
const missingCosts=computed(()=>[...new Set<string>((props.preview.impacts||[]).flatMap((day:any)=>day.window?.unknown_cost_items||[]))])
const costLabel=computed(()=>props.preview.budget?.total>0?`已知 ¥${props.preview.budget.total.toLocaleString()}${props.preview.budget.is_complete?'':' · 尚未核齐'}`:props.preview.intercity_total>0?`交通已知 ¥${props.preview.intercity_total.toLocaleString()}`:'费用待核对')
function shortDate(value:string){return `${Number(value.slice(5,7))}月${Number(value.slice(8,10))}日`}
function durationLabel(minutes:number){return `${Math.floor(minutes/60)?Math.floor(minutes/60)+'小时':''}${minutes%60?minutes%60+'分钟':''}`||'0分钟'}
function mealTimingNote(meal:any){
  if(meal.status!=='scheduled')return ''
  if(meal.timing_note)return meal.timing_note
  const day=props.preview.days_detail?.find((d:any)=>d?.date===meal.date)
  if(!day?.travel_window?.legs?.some((leg:any)=>leg.direction==='inbound'))return ''
  const end=Math.max(0,...(day.timeline_schedule||[]).map((row:any)=>row.end_minutes||0))
  const margin=(day.travel_window.end_minutes??1440)-end
  return margin>=0&&margin<=30?`预留接驳之外仅余${margin}分钟，返程前的安排偏紧。`:''
}
function kindLabel(value:string){return ({attraction:'游玩',travel:'路程',meal:'用餐',hotel:'住宿',rest:'休息',free_time:'自由时间',wait:'等候'} as Record<string,string>)[value]||'安排'}
</script>

<style scoped>
.pace-days{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.pace-days article{padding:18px;border-radius:12px;background:color-mix(in srgb,var(--color-primary) 4%,var(--color-bg-primary));border:1px solid var(--color-border)}.pace-days article>span{font-size:12px;color:var(--color-text-secondary)}.pace-days strong{display:block;margin-top:8px;font-size:20px;font-weight:500;font-variant-numeric:tabular-nums}.pace-days p{font-size:12px;color:var(--color-text-secondary);margin:9px 0 12px}.pace-days article>div{display:flex;gap:8px;flex-wrap:wrap;font-size:11px;color:var(--color-primary)}.pace-days article>div>span{padding:5px 8px;border-radius:6px;background:var(--color-bg-primary)}.pace-note{font-size:12px;color:var(--color-text-secondary);line-height:1.7;margin:12px 0 0}@media(max-width:650px){.pace-days{grid-template-columns:1fr}.pace-days strong{font-size:18px}}
.meal-proposal .meal-timing-note{color:var(--color-warning);padding-top:6px}
.meal-proposals{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.meal-proposal{padding:18px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-bg-primary)}.meal-proposal header{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:var(--color-primary)}.meal-proposal time{font-variant-numeric:tabular-nums;white-space:nowrap}.meal-proposal h5{font-size:15px;font-weight:500;line-height:1.6;margin:12px 0 8px;overflow-wrap:anywhere}.meal-proposal p{font-size:12px;line-height:1.7;color:var(--color-text-secondary);margin:6px 0}.meal-proposal .meal-replaced{font-size:11px}.meal-proposal small{display:block;font-size:10px;color:var(--color-text-secondary);margin-top:12px;line-height:1.7}.meal-proposal details{font-size:11px;line-height:1.8;color:var(--color-text-secondary);margin-top:10px}.meal-proposal summary{cursor:pointer}.meal-proposal ul{padding-left:16px}.meal-proposal.pending{border-color:color-mix(in srgb,var(--color-warning) 25%,var(--color-border))}.meal-pending-label{color:var(--color-warning)}@media(max-width:650px){.meal-proposals{grid-template-columns:1fr}.meal-proposal{padding:16px}}
.travel-preview{color:var(--color-text-primary);animation:proposal-in .28s ease-out}.proposal-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:4px 0 22px}.proposal-label{display:flex;align-items:center;gap:7px;color:var(--color-primary);font-size:11px;letter-spacing:.03em}.proposal-label i{height:6px;width:6px;border-radius:50%;background:var(--color-primary)}h3{font-size:24px;line-height:1.4;font-weight:500;letter-spacing:-.02em;margin:8px 0 6px}.proposal-heading p{font-size:13px;color:var(--color-text-secondary);margin:0}.proposal-status{font-size:12px;padding:8px 12px;border:1px solid var(--color-border);border-radius:20px;white-space:nowrap;color:var(--color-text-secondary)}.proposal-status.warning{color:var(--color-warning)}.proposal-tickets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.proposal-section-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:25px 0 12px}h4{font-size:14px;margin:0;font-weight:600}.proposal-section-heading>span{font-size:11px;color:var(--color-text-secondary)}.proposal-timeline{border:1px solid var(--color-border);border-radius:12px;padding:18px 22px;margin-top:12px;background:var(--color-bg-primary)}.proposal-timeline header{display:flex;justify-content:space-between;gap:20px;align-items:center;font-size:13px}.proposal-timeline header strong{font-weight:500}.proposal-timeline header button{border:0;background:none;color:var(--color-primary);font:inherit;font-size:12px;cursor:pointer}.proposal-timeline>p{font-size:13px;color:var(--color-text-secondary)}.proposal-timeline ol{list-style:none;margin:20px 0 0;padding:0}.proposal-timeline li{display:grid;grid-template-columns:44px 14px 1fr;gap:14px;position:relative;padding:0 0 20px}.proposal-timeline li:last-child{padding-bottom:0}.proposal-timeline li::before{content:'';position:absolute;top:8px;bottom:-8px;left:64px;width:1px;background:var(--color-border)}.proposal-timeline li:last-child::before{display:none}.timeline-dot{height:7px;width:7px;border-radius:50%;border:1px solid var(--color-primary);background:var(--color-bg-primary);margin:6px 0 0 3px;z-index:1}.proposal-timeline time{font-size:12px;font-variant-numeric:tabular-nums;display:flex;flex-direction:column;gap:3px}.proposal-timeline time small{color:var(--color-text-secondary);font-size:10px}.proposal-timeline li>div{display:flex;gap:12px;align-items:baseline;min-width:0}.proposal-timeline li>div>span{font-size:10px;color:var(--color-text-secondary);white-space:nowrap}.proposal-timeline li strong{font-size:13px;font-weight:500;overflow-wrap:anywhere}.proposal-timeline .travel strong,.proposal-timeline .free_time strong{font-size:12px;font-weight:400;color:var(--color-text-secondary)}.proposal-timeline .travel .timeline-dot{height:4px;width:4px;margin-left:5px;border-color:var(--color-text-secondary)}
.proposal-changes{margin-bottom:20px}.change-row{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;background:var(--color-bg-primary);border:1px solid var(--color-border);border-radius:10px;margin-bottom:8px}.change-symbol{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:26px;height:26px;border-radius:8px;background:var(--color-bg-secondary);color:var(--color-primary);font-size:16px}.change-row>div{flex:1;min-width:0}.change-row strong{font-size:13px;font-weight:500;line-height:1.7}.change-row p{margin:3px 0 0;color:var(--color-text-secondary);font-size:12px;line-height:1.7;overflow-wrap:anywhere}.change-row p span{margin:0 6px;color:var(--color-primary)}.change-row small{margin-left:14px;font-size:11px}.change-type{align-self:center;font-size:10px;color:var(--color-text-secondary);white-space:nowrap}.attention{background:color-mix(in srgb,var(--color-warning) 5%,var(--color-bg-primary));border-color:color-mix(in srgb,var(--color-warning) 20%,var(--color-border))}.attention .change-symbol{color:var(--color-warning)}.pending-note,.conflict-note{padding:16px;border-left:3px solid var(--color-warning);border-radius:8px;background:var(--color-bg-primary);margin:10px 0;font-size:13px}.pending-note p,.conflict-note p{line-height:1.7;margin:6px 0 0;color:var(--color-text-secondary)}.unchanged-note{display:flex;gap:10px;font-size:13px;color:var(--color-text-secondary);margin:24px 0}.unchanged-note>span{color:var(--color-primary)}
.proposal-evidence{margin-top:22px;border-top:1px solid var(--color-border);font-size:12px}.proposal-evidence>summary{display:flex;justify-content:space-between;gap:14px;cursor:pointer;padding:17px 0;color:var(--color-text-secondary);list-style:none}.proposal-evidence>summary::-webkit-details-marker{display:none}.proposal-evidence>summary i{font-style:normal;margin-left:12px;color:var(--color-primary)}.evidence-content{background:var(--color-bg-primary);padding:18px 20px;border-radius:12px;margin-bottom:18px;line-height:1.8;color:var(--color-text-secondary)}.evidence-content p{margin:8px 0}.evidence-content ul{padding-left:18px}.evidence-day{border-top:1px solid var(--color-border);padding-top:12px;margin-top:12px}.evidence-day>strong{color:var(--color-text-primary)}
.proposal-actions{display:flex;align-items:center;justify-content:space-between;gap:20px;position:relative;z-index:1;padding:16px 18px;margin:4px -6px -6px;border:1px solid var(--color-border);border-radius:14px;background:var(--color-bg-primary);box-shadow:0 6px 24px #00000007}.proposal-ack{display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;line-height:1.6}.proposal-ack input{width:17px;height:17px;margin:0;accent-color:var(--color-primary);flex-shrink:0}.proposal-ack small{display:block;color:var(--color-text-secondary);font-size:10px;margin-top:2px}.proposal-ready{font-size:12px;color:var(--color-text-secondary);margin:0}.proposal-buttons{display:flex;align-items:center;gap:10px;flex-shrink:0}.proposal-buttons button{font:inherit;font-size:13px;min-height:42px;padding:10px 18px;border-radius:9px;cursor:pointer;transition:background .18s,opacity .18s}.secondary-action{border:1px solid var(--color-border);background:transparent;color:var(--color-text-secondary)}.primary-action{border:1px solid var(--color-primary);background:var(--color-primary);color:var(--desk-on-accent,#fff);font-weight:500!important}.primary-action span{margin-left:12px}.proposal-buttons button:disabled{opacity:.45;cursor:default}:focus-visible{outline:2px solid var(--color-primary);outline-offset:4px}
@keyframes proposal-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}@media(prefers-reduced-motion:reduce){.travel-preview{animation:none}.proposal-buttons button{transition:none}}@media(max-width:650px){.proposal-heading{align-items:flex-start;gap:10px}.proposal-status{font-size:10px;padding:6px 8px}.proposal-tickets{grid-template-columns:1fr;gap:12px}h3{font-size:21px}.proposal-section-heading{flex-wrap:wrap;gap:6px}.proposal-section-heading>span{font-size:10px}.proposal-actions{flex-direction:column;align-items:stretch;gap:12px;margin:4px -5px -5px;padding:14px}.proposal-buttons{display:grid;grid-template-columns:1fr 1.5fr}.proposal-buttons button{width:100%;padding:10px 12px}.proposal-ack small{display:inline;margin-left:7px}.proposal-timeline{padding:16px 12px}.proposal-timeline li{gap:10px;grid-template-columns:40px 14px 1fr}.proposal-timeline li::before{left:56px}.proposal-timeline li>div{flex-direction:column;gap:3px}.change-row{padding:12px}.change-row small{display:block;margin:3px 0 0}.change-type{display:none}.proposal-evidence>summary{font-size:11px}}
</style>

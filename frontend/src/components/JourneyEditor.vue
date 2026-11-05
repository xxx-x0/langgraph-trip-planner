<template>
  <section ref="editorRoot" class="journey-editor">
    <div class="journey-heading"><div><span class="journey-eyebrow">ON THE WAY · 往返大交通</span><h3>{{ singleLeg ? '这一段交通' : '出发与返回' }}</h3></div><span class="journey-party">{{ passengers || 1 }} 人同行</span></div>
    <p>{{ singleLeg ? '直接选择交通方式，再补充这一程的站点与时间。' : '先确定从哪里出发，再分别安排去程和返程。还没定班次，可以稍后补充。' }}</p>
    <div v-if="!singleLeg" class="route-fields">
      <label>出发城市<input v-model="value.origin_city" @input="publish" placeholder="例如：杭州" aria-label="出发城市" /></label><span class="route-arrow" aria-hidden="true">→</span>
      <div class="destination-label"><span>游玩城市</span><strong>{{ destinationCity || '在上方填写目的地' }}</strong></div><span class="route-arrow" aria-hidden="true">→</span>
      <label>返回城市<input v-model="value.return_city" @input="returnCityChanged" :placeholder="value.origin_city || '默认回到出发城市'" aria-label="返回城市" /></label>
    </div>
    <p v-if="!singleLeg" class="journey-hint">返回城市留空时回到出发城市；只安排市内游玩可将出发城市留空。</p>
    <p v-if="showErrors && !value.origin_city.trim()" class="passenger-warning" role="alert">请先填写出发城市。</p>
    <div class="leg-tabs" aria-label="选择去程或返程" v-if="!singleLeg">
      <button v-for="direction in directions" :key="direction.key" type="button" :aria-pressed="activeLeg === direction.key" :class="{selected:activeLeg === direction.key}" @click="activeLeg=direction.key"><span>{{ direction.label }}</span><strong>{{ routeLabel(direction.key) }}</strong><small>{{ value[direction.key] ? modeLabel(value[direction.key]!.mode) : '班次待确定' }}</small></button>
    </div>
    <fieldset v-for="direction in visibleDirections" :key="direction.key" :aria-label="direction.label + '交通安排'">
      <legend>{{ direction.label }} · {{ singleLeg ? '选择交通方式' : routeLabel(direction.key) }}</legend>
      <div class="mode-choices" :aria-label="direction.label + '交通方式'">
        <button type="button" :aria-pressed="!value[direction.key]" :class="{selected:!value[direction.key]}" @click="selectMode(direction.key,null)">稍后确定</button>
        <button v-for="mode in modes" :key="mode.key" type="button" :aria-pressed="value[direction.key]?.mode === mode.key" :class="{selected:value[direction.key]?.mode === mode.key}" @click="selectMode(direction.key,mode.key)">{{ mode.label }}</button>
      </div>
      <div v-if="!value[direction.key] && !singleLeg" class="leg-empty">
        <p>未定班次时，景点先作为可调整安排。选定交通后按实际抵离时间联动调整，首末天不会自动整天留空。已有明确时间要求时可在这里设置。</p>
        <label>{{direction.label}}交通时间预留<select :value="reservationPolicy(direction.key)" @change="setReservationPolicy(direction.key,($event.target as HTMLSelectElement).value)"><option value="travel_day">{{direction.key==='outbound'?'首日留给交通':'末日留给交通'}}</option><option value="time_window">填写预计目的地可用时间</option><option value="unreserved">暂不预留，按全天游玩</option></select></label>
        <label v-if="reservationPolicy(direction.key)==='time_window'">{{direction.key==='outbound'?'预计可以开始本城活动的时间':'预计必须结束本城活动的时间'}}<input type="datetime-local" :value="direction.key==='outbound'?value.planning?.ready_at:value.planning?.leave_by" @input="setReservationTime(direction.key,($event.target as HTMLInputElement).value)" /></label>
        <p v-if="reservationPolicy(direction.key)==='travel_day'">{{direction.key==='outbound'?'首日':'末日'}}暂不安排景点；景点优先放到其他可用日期，放不下的保留待安排。这不是已查到或已订的班次。</p>
        <p v-if="showErrors && reservationIssue(direction.key)" role="alert" class="passenger-warning">{{reservationIssue(direction.key)}}</p>
      </div>
      <p v-else-if="!value[direction.key]" class="leg-empty">本段班次及费用待定。</p>
      <template v-if="value[direction.key]">
          <p v-if="showErrors && legIssue(direction.key)" class="passenger-warning" role="alert">{{ legIssue(direction.key) }}</p>
          <p v-if="value[direction.key]!.passengers !== (passengers || 1) && !(showErrors && legIssue(direction.key).includes('同行人数'))" class="passenger-warning" role="alert">这程按 {{ value[direction.key]!.passengers }} 人填写，与本次 {{ passengers || 1 }} 人同行不同，请核对人数与报价。</p>
          <p class="journey-hint"><span v-if="direction.key === 'outbound' ? startDate : endDate">{{ direction.key === 'outbound' ? startDate : endDate }} · </span>请按实际班次填写时间。切换交通方式会清空这程的班次和报价，接驳预留保持不变。</p>
          <div class="fields">
            <label>班次（可选）<input v-model="value[direction.key]!.service_number" @input="publish" /></label>
            <label>预订状态<select v-model="value[direction.key]!.booking_status" @change="publish"><option value="planned">正在考虑</option><option value="booked">已订，固定时间</option></select></label>
            <label>出发站／机场<input v-model="value[direction.key]!.departure_station" @input="publish" /></label>
            <label>到达站／机场<input v-model="value[direction.key]!.arrival_station" @input="publish" /></label>
            <label>同行人数<input type="number" min="1" max="20" v-model.number="value[direction.key]!.passengers" @input="publish" /></label>
            <label>当地出发日期时间<input type="datetime-local" v-model="value[direction.key]!.departure_time" @input="publish" /></label>
            <label>当地到达日期时间<input type="datetime-local" v-model="value[direction.key]!.arrival_time" @input="publish" /></label>
          </div>
          <details class="price-details"><summary>票价与来源 <span>{{ value[direction.key]!.ticket_total == null ? '金额未知，可稍后补充' : '已填参考金额' }}</span></summary><div class="fields">
            <label>全体同行票价总额<input type="number" min="0" step="0.01" :value="value[direction.key]!.ticket_total ?? ''" @input="money(direction.key,'ticket_total',$event)" placeholder="未知留空" /></label>
            <label>币种<input v-model="value[direction.key]!.currency" @input="publish" maxlength="3" /></label>
            <label v-if="!value[direction.key]!.extra_costs">全体额外费用总额<input type="number" min="0" step="0.01" :value="value[direction.key]!.extras_total ?? ''" @input="money(direction.key,'extras_total',$event)" placeholder="未知留空；含税费、行李和两端接驳" /></label>
            <label>价格来源<select v-model="value[direction.key]!.price_source" @change="publish"><option value="unknown">未知</option><option value="user_estimate">自己估算</option><option value="user_quote">手动记录报价</option><option value="paid">已支付</option></select></label>
            <label>来源说明<input v-model="value[direction.key]!.price_note" @input="publish" placeholder="查询渠道、税费行李和退改条件" /></label>
            <label>记录时间（出发时区）<input type="datetime-local" v-model="value[direction.key]!.quoted_at" @input="publish" /></label>
          </div>
          </details>
          <details><summary>拆分额外费用和舒适度信息</summary>
            <p>只填写尚未包含在票价内的费用；已含税、无额外行李或无需途中住宿时填 0。这里的途中住宿不包含目的地酒店，避免重复计算。所有金额均为全体同行总额。</p>
            <label><input type="checkbox" :checked="!!value[direction.key]!.extra_costs" @change="toggleExtras(direction.key)" />逐项填写费用（替代额外费用总额）</label>
            <div class="fields" v-if="value[direction.key]!.extra_costs">
              <label v-for="cost in costs" :key="cost.key">{{cost.label}}<input type="number" min="0" step="0.01" :value="value[direction.key]!.extra_costs![cost.key] ?? ''" @input="extraMoney(direction.key,cost.key,$event)" placeholder="未知留空" /></label>
            </div>
            <div class="fields">
              <label>中转次数（直达填0）<input type="number" min="0" max="10" :value="value[direction.key]!.connections ?? ''" @input="connections(direction.key,$event)" /></label>
              <label>席别／舱等<input v-model="value[direction.key]!.seat_class" @input="publish" /></label>
              <label>行李条件<input v-model="value[direction.key]!.baggage_policy" @input="publish" /></label>
              <label>退改条件<input v-model="value[direction.key]!.refund_policy" @input="publish" /></label>
              <label>报价失效时间（来源明确提供时填写）<input type="datetime-local" v-model="value[direction.key]!.quote_expires_at" @input="publish" /></label>
            </div>
          </details>
          <details><summary>编辑接驳与缓冲时间</summary>
            <p>下列默认值仅用于预留时间，不是地图查询或航空公司的要求。市内安排从去程到达、取行李、接驳至酒店和入住缓冲之后开始；返程预留退房、酒店至车站接驳及候车。请按实际情况修改。</p>
            <div class="fields"><label v-for="buffer in buffers" :key="buffer.key">{{ buffer.label }}（分钟）<input type="number" min="0" :max="buffer.key === 'lodging_buffer_minutes' ? 240 : 720" v-model.number="value[direction.key]![buffer.key]" @input="publish" /></label></div>
          </details>
          <details><summary>时区设置 <span>{{ value[direction.key]!.departure_timezone === 'Asia/Shanghai' && value[direction.key]!.arrival_timezone === 'Asia/Shanghai' ? '北京时间' : '按各地当地时间' }}</span></summary><div class="fields">
            <label v-if="!singleLeg">目的地时区<input v-model="value.destination_timezone" @input="publish" /></label>
            <label>出发时区<input v-model="value[direction.key]!.departure_timezone" @input="publish" /></label>
            <label>到达时区<input v-model="value[direction.key]!.arrival_timezone" @input="publish" /></label>
          </div></details>
        </template>
      </fieldset>
      <p>日期范围包含在途日期；跨日到达请填写次日日期。非人民币不自动换算。尚未填写的一段保持暂定，不按免费处理。</p>
    <p class="journey-hint">填写的是已买好或正在考虑的班次；这里不会下单或改签。</p>
  </section>
</template>
<script setup lang="ts">
import {ref, watch, computed, nextTick} from 'vue'
import type {Journey,JourneyExtras,JourneyLeg,JourneyPlanning} from '@/types'
const props=defineProps<{modelValue?:Journey|null; startDate?:string; endDate?:string; passengers?:number; singleLeg?:boolean; destinationCity?:string}>()
const emit=defineEmits<{(e:'update:modelValue',value:Journey|null):void}>()
const emptyJourney=()=>({origin_city:'',return_city:'',destination_timezone:'Asia/Shanghai',...(props.singleLeg?{}:{planning:{arrival_policy:'unreserved' as const,departure_policy:'unreserved' as const,ready_at:null,leave_by:null}})})
const value=ref<Journey>(JSON.parse(JSON.stringify(props.modelValue || emptyJourney())))
const activeLeg=ref<'outbound'|'inbound'>('outbound')
const editorRoot=ref<HTMLElement>()
const showErrors=ref(false)
// Keep a blank return field as an explicit UI choice to follow the origin.
let followOrigin=!props.modelValue?.return_city || props.modelValue.return_city===props.modelValue.origin_city
if(followOrigin)value.value.return_city=''
let lastPublished=''
watch(()=>props.modelValue, v=>{
 if(JSON.stringify(v)===lastPublished)return
 const updated:Journey=JSON.parse(JSON.stringify(v || emptyJourney()))
 if(followOrigin && (!updated.return_city || updated.return_city===updated.origin_city)) updated.return_city=''
 else followOrigin=false
 value.value=updated
})
function returnCityChanged(){followOrigin=!value.value.return_city.trim();publish()}
function reservationPolicy(key:'outbound'|'inbound'){return (key==='outbound'?value.value.planning?.arrival_policy:value.value.planning?.departure_policy)||'unreserved'}
function ensurePlanning(){return value.value.planning ||= {arrival_policy:'unreserved',departure_policy:'unreserved',ready_at:null,leave_by:null}}
function setReservationPolicy(key:'outbound'|'inbound',policy:string){const planning=ensurePlanning();if(key==='outbound')planning.arrival_policy=policy as JourneyPlanning['arrival_policy'];else planning.departure_policy=policy as JourneyPlanning['departure_policy'];publish()}
function setReservationTime(key:'outbound'|'inbound',time:string){const planning=ensurePlanning();if(key==='outbound')planning.ready_at=time||null;else planning.leave_by=time||null;publish()}
function reservationIssue(key:'outbound'|'inbound'){
 if(value.value[key]||!value.value.origin_city.trim()||reservationPolicy(key)!=='time_window')return ''
 const time=key==='outbound'?value.value.planning?.ready_at:value.value.planning?.leave_by
 if(!time)return '请填写预计目的地可用时间，或改为整天留给交通。'
 if((props.startDate && time.slice(0,10)<props.startDate)||(props.endDate && time.slice(0,10)>props.endDate))return '预计可用时间须在整趟出行日期范围内。'
 return ''
}
function legIssue(key:'outbound'|'inbound'){
 const leg=value.value[key];const label=key==='outbound'?'去程':'返程'
 if(!leg)return ''
 if(!leg.departure_station.trim() || !leg.arrival_station.trim() || !leg.departure_time || !leg.arrival_time)return `请补充${label}的站点与日期时间；班次未定可选择“稍后确定”。`
 if(leg.departure_timezone===leg.arrival_timezone && leg.arrival_time<=leg.departure_time)return `${label}到达时间须晚于出发时间；跨日到达请选次日日期。`
 if(leg.passengers!==(props.passengers||1))return `请核对${label}同行人数与报价，与本次 ${props.passengers||1} 人保持一致。`
 if(leg.ticket_total!=null && leg.price_source==='unknown')return `请为${label}票价选择价格来源；不确定金额可留空。`
 if(['user_quote','paid'].includes(leg.price_source) && (!leg.price_note?.trim() || !leg.quoted_at))return `请补充${label}价格的来源说明和记录时间。`
 return ''
}
async function validate(){
 showErrors.value=true
 const direction=directions.value.find(d=>legIssue(d.key)||reservationIssue(d.key))
 if((value.value.origin_city.trim() && !direction) || (!value.value.origin_city.trim() && !value.value.return_city.trim() && !value.value.outbound && !value.value.inbound))return true
 if(direction)activeLeg.value=direction.key
 await nextTick()
 const root=editorRoot.value
 if(direction && /价格|票价/.test(legIssue(direction.key)))root?.querySelector('details.price-details')?.setAttribute('open','')
 const target=!value.value.origin_city.trim()?root?.querySelector<HTMLInputElement>('[aria-label="出发城市"]'):root?.querySelector<HTMLElement>('fieldset')
 target?.setAttribute('tabindex','-1');target?.scrollIntoView?.({block:'center',behavior:'auto'});target?.focus?.({preventScroll:true})
 return false
}
defineExpose({validate})
const directions=computed(()=>props.singleLeg?[{key:'outbound' as const,label:'本段'}]:[{key:'outbound' as const,label:'去程'},{key:'inbound' as const,label:'返程'}])
const visibleDirections=computed(()=>directions.value.filter(d=>props.singleLeg || d.key===activeLeg.value))
const modes: {key:JourneyLeg['mode'];label:string}[]=[{key:'train',label:'铁路'},{key:'flight',label:'飞机'},{key:'driving',label:'自驾'},{key:'bus',label:'长途汽车'},{key:'other',label:'其他'}]
const modeLabel=(mode:string)=>modes.find(m=>m.key===mode)?.label || mode
function routeLabel(key:'outbound'|'inbound') { const destination=props.destinationCity || '目的地'; return key==='outbound' ? `${value.value.origin_city || '出发地'} → ${destination}` : `${destination} → ${value.value.return_city || value.value.origin_city || '返回地'}` }
const buffers=[{key:'transfer_before_minutes' as const,label:'出发地至车站／机场接驳'},{key:'station_buffer_minutes' as const,label:'安检／候车'},{key:'baggage_minutes' as const,label:'到达取行李'},{key:'transfer_after_minutes' as const,label:'到达站至酒店／家接驳'},{key:'lodging_buffer_minutes' as const,label:'目的地入住／退房'}]
const costs=[{key:'taxes' as const,label:'未含税费'},{key:'baggage' as const,label:'额外行李'},{key:'transfers' as const,label:'两端接驳'},{key:'overnight' as const,label:'途中额外住宿'}]
function toggleExtras(key:'outbound'|'inbound') {const leg=value.value[key]!;leg.extra_costs=leg.extra_costs?null:{taxes:null,baggage:null,transfers:null,overnight:null};leg.extras_total=null;publish()}
function extraMoney(key:'outbound'|'inbound',field:keyof JourneyExtras,event:Event){const input=(event.target as HTMLInputElement).value;const leg=value.value[key]!;leg.extra_costs![field]=input===''?null:Number(input);leg.extras_total=Object.values(leg.extra_costs!).reduce<number>((sum,v)=>sum+(v??0),0);publish()}
function connections(key:'outbound'|'inbound',event:Event){const input=(event.target as HTMLInputElement).value;value.value[key]!.connections=input===''?null:Number(input);publish()}
function publish(){
 const result=!value.value.origin_city.trim() && !value.value.outbound && !value.value.inbound ? null : JSON.parse(JSON.stringify({...value.value,return_city:value.value.return_city.trim() || value.value.origin_city.trim()}))
 lastPublished=JSON.stringify(result);emit('update:modelValue',result)
}
function selectMode(key:'outbound'|'inbound',mode:JourneyLeg['mode']|null){
 const old=value.value[key]
 if(mode===old?.mode)return
 if(!mode){value.value[key]=null;publish();return}
 const retainedBuffers=old ? Object.fromEntries(buffers.map(b=>[b.key,old[b.key]])) : {}
 value.value[key]={mode,service_number:'',departure_station:'',arrival_station:'',departure_time:'',arrival_time:'',departure_timezone:'Asia/Shanghai',arrival_timezone:'Asia/Shanghai',passengers:props.passengers||1,booking_status:'planned',price_source:'unknown',price_note:'',quoted_at:null,ticket_total:null,extras_total:null,currency:'CNY',transfer_before_minutes:60,station_buffer_minutes:60,baggage_minutes:30,transfer_after_minutes:60,lodging_buffer_minutes:30,...retainedBuffers};publish()
}
function money(key:'outbound'|'inbound',field:'ticket_total'|'extras_total',event:Event){const input=(event.target as HTMLInputElement).value;value.value[key]![field]=input===''?null:Number(input);publish()}
</script>
<style scoped>
.journey-editor{background:var(--color-bg-primary);color:var(--color-text-primary);padding:28px;border:1px solid var(--color-border);border-radius:20px;margin:0 0 24px}.journey-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.journey-eyebrow{color:var(--color-primary);font-size:10px;letter-spacing:.12em}.journey-heading h3{font-size:22px;font-weight:500;margin:10px 0}.journey-party{font-size:12px;color:var(--color-text-secondary)}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px;margin:18px 0}label{display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--color-text-secondary)}.fields label,.route-fields label{flex-direction:column}input,select{font:inherit;font-size:13px;color:var(--color-text-primary);background:var(--desk-input);border:1px solid var(--color-border-strong);border-radius:10px;padding:11px;min-width:0;max-width:100%}input[type=checkbox]{width:auto}fieldset{min-width:0;margin-top:24px;border:1px solid var(--color-border);border-radius:16px;padding:20px}legend{font-size:13px;padding:0 8px;color:var(--color-text-secondary);width:auto;float:none}p{line-height:1.8;font-size:13px;color:var(--color-text-secondary)}.journey-hint{font-size:11px}.passenger-warning{color:var(--color-warning);background:var(--color-warning-bg);padding:12px;border-radius:10px}.route-fields{display:grid;grid-template-columns:1fr 24px 1fr 24px 1fr;gap:12px;align-items:center;margin-top:24px}.route-arrow{text-align:center;color:var(--color-primary);padding-top:18px}.destination-label{display:flex;flex-direction:column;gap:14px;min-width:0}.destination-label span{font-size:12px;color:var(--color-text-secondary)}.destination-label strong{font-size:18px;font-weight:500;overflow-wrap:anywhere}.leg-tabs{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:24px}.leg-tabs button{display:flex;flex-direction:column;gap:8px;text-align:left;background:var(--color-bg-secondary);color:var(--color-text-primary);padding:18px;border:1px solid var(--color-border);border-radius:14px;cursor:pointer;transition:background .2s,border-color .2s}.leg-tabs span,.leg-tabs small{font-size:11px;color:var(--color-text-secondary)}.leg-tabs strong{font-size:15px;font-weight:500}.leg-tabs button.selected{border-color:var(--color-primary);background:var(--color-primary-bg)}.mode-choices{display:flex;gap:8px;flex-wrap:wrap}.mode-choices button{border:1px solid var(--color-border);border-radius:100px;padding:10px 16px;background:transparent;color:var(--color-text-secondary);font:inherit;font-size:12px;cursor:pointer;transition:background .2s,color .2s}.mode-choices .selected{background:var(--color-primary);border-color:var(--color-primary);color:var(--desk-on-accent)}.leg-empty{margin:20px 0 0}.journey-editor details{border-top:1px solid var(--color-border);padding:14px 0}.journey-editor summary{cursor:pointer;font-size:12px}.journey-editor summary span{font-size:11px;color:var(--color-text-secondary);margin-left:12px}input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--color-primary);outline-offset:3px}
@media(max-width:600px){.route-fields{grid-template-columns:1fr 16px 1fr;gap:10px}.route-fields label:last-child{grid-column:1/-1}.route-arrow:nth-of-type(2){display:none}.fields{grid-template-columns:1fr}.journey-editor{padding:20px 18px}.leg-tabs button{padding:14px}.leg-tabs strong{font-size:13px}.journey-editor fieldset{padding:16px 12px}.mode-choices{gap:6px}.mode-choices button{padding:9px 12px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

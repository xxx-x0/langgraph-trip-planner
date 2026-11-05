<template>
  <section class="journey-planner" aria-label="交通与景点一起规划" :aria-busy="busy">
    <div class="planner-heading"><div><small>AI TRIP · 一起安排怎么去、怎么玩</small><h3>让交通和景点配合起来</h3></div><span>{{request.companions?.count||1}} 人同行</span></div>
    <p>告诉我从哪里出发，我会搭配往返班次，留出接驳时间，再把景点放进合适的时段。选好景点后也能换方案。</p>
    <div class="route-fields">
      <label>出发城市<input aria-label="出发城市" :value="modelValue?.origin_city||''" :disabled="disabled||booked||fixedRoute" placeholder="例如：上海" @change="setRoute('origin_city',($event.target as HTMLInputElement).value)" /></label>
      <div class="destination"><small>前往</small><strong>{{request.city||'选择目的地'}}</strong></div>
      <label>返回城市<input aria-label="返回城市" :value="modelValue?.return_city===modelValue?.origin_city?'':modelValue?.return_city||''" :disabled="disabled||booked||fixedRoute" :placeholder="modelValue?.origin_city||'回到出发城市'" @change="setRoute('return_city',($event.target as HTMLInputElement).value)" /></label>
    </div>
    <p v-if="!modelValue?.origin_city" class="hint">只逛本地可以留空。</p>
    <div class="transport-choices" aria-label="交通偏好">
      <button v-for="choice in modes" :key="choice.value" type="button" :aria-pressed="mode===choice.value" :disabled="disabled" @click="mode=choice.value">{{choice.label}}</button>
    </div>
    <div class="preferences">
      <label>这趟更看重<select v-model="priority" aria-label="这趟更看重" :disabled="disabled"><option value="balanced">时间、费用和游玩兼顾</option><option value="price">已知参考价最低</option><option value="time">乘坐时间最短</option></select></label>
      <label v-if="priority==='balanced'">推荐方式<select v-model="engine" aria-label="推荐方式" :disabled="disabled"><option value="default">默认 AI</option><option value="jev">Jev（WindHub）</option></select></label>
    </div>
    <label class="intent">交通方面的想法<input v-model="intent" :disabled="disabled" maxlength="500" placeholder="例如：不想一整天在路上，希望第一天还能逛逛" /></label>
    <details class="conditions"><summary>必须满足的条件与接驳说明</summary>
      <label>每程每人参考价上限<input v-model.number="priceLimit" type="number" min="0" max="1000000" :disabled="disabled" placeholder="不限" /></label>
      <label>接受的席别／舱等<select v-model="seats" multiple :disabled="disabled" aria-label="自动规划接受席别"><option v-for="seat in ['二等座','一等座','商务座','硬座','硬卧','软卧','经济舱','商务舱','头等舱']" :key="seat">{{seat}}</option></select></label>
      <label><input v-model="daytimeHard" type="checkbox" :disabled="disabled" />必须当天 07:00 后出发、22:00 前到达</label>
      <p>只在符合明确条件的候选中比较。接驳和候车先用可编辑的时间预留，采用后可核对；列表价仍需确认票种、税费和同行总额。</p>
    </details>
    <div class="planner-actions">
      <button type="button" class="primary" :disabled="disabled||busy||!canSearch" @click="search(false)">{{busy?'正在搭配交通…':modelValue?.outbound||modelValue?.inbound?'重新搭配未订班次':'AI 帮我搭配往返'}}</button>
      <button v-if="busy" type="button" @click="stop">停止查询</button>
    </div>
    <p v-if="status" role="status">{{status}}</p>
    <p v-if="!options.length&&!busy" class="hint">班次未确定时，首末天仍可选景点，安排会标为暂定；取得班次后一起调整。</p>
    <div v-if="modelValue?.outbound||modelValue?.inbound" class="current-journey">
      <strong>当前衔接方案</strong>
      <p v-for="d in directions" :key="d.key">{{d.label}} · <template v-if="modelValue?.[d.key]">{{modelValue[d.key]!.service_number||'自行安排'}}　{{modelValue[d.key]!.departure_time.replace('T',' ')}} → {{modelValue[d.key]!.arrival_time.replace('T',' ')}}<span v-if="modelValue[d.key]!.booking_status==='booked'">　已订，保持不变</span></template><template v-else>待取得班次，时间暂定</template></p>
    </div>
    <div class="journey-options" v-if="options.length">
      <article v-for="(option,index) in options" :key="option.id" :class="{selected:selected===option.id}">
        <h4>{{index===0?(rankedBy==='ai'||rankedBy==='jev'?'推荐衔接方案':'可行方案'):'另一种选择'}} <small v-if="rankedBy==='jev'&&index===0">Jev</small></h4>
        <p v-for="d in directions" :key="d.key">{{d.label}} · <template v-if="option.journey[d.key]">{{option.journey[d.key].mode==='train'?'铁路':'航班'}} {{option.journey[d.key].service_number}}<br />{{option.journey[d.key].departure_station}} {{option.journey[d.key].departure_time.slice(11)}} → {{option.journey[d.key].arrival_station}} {{option.journey[d.key].arrival_time.replace('T',' ')}}</template><template v-else>仍待查询</template></p>
        <p>{{option.reference_fare_per_person==null?'往返参考价尚不完整':'往返每人列表参考 ¥'+option.reference_fare_per_person}} · 含接驳约 {{duration(option.door_minutes)}}</p>
        <ul><li v-for="day in edgeDays(option.days)" :key="day.date">{{day.date}} · {{windowLabel(day.window)}}</li></ul>
        <p v-if="option.selection_tight" class="tight">已选景点时长接近或超出可用时间，还需留出用餐与市内交通。可换班次、调整景点或增加天数。</p>
        <p class="hint">{{option.note}}</p>
        <button type="button" :disabled="disabled||busy||selected===option.id" @click="adopt(option)">{{selected===option.id?'已按此方案衔接景点':'用此方案衔接景点'}}</button>
      </article>
    </div>
    <details v-if="notices.length" class="source-status"><summary>本次查票范围与未取得的结果</summary><p v-for="notice in notices" :key="notice">{{notice}}</p><p>比较的是本次查询取得的部分直达候选，不代表全部班次。</p></details>
    <details class="manual-journey" :open="manualOpen" @toggle="manualOpen=($event.target as HTMLDetailsElement).open">
      <summary>已有车票／自行安排 <span>录入或修改已知信息</span></summary>
      <JourneyEditor ref="manualEditor" :model-value="modelValue" :destination-city="request.city" :start-date="request.start_date" :end-date="request.end_date" :passengers="request.companions?.count||1" @update:model-value="manualChanged" />
    </details>
  </section>
</template>
<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,ref,watch} from 'vue'
import type {Journey,TripFormData} from '@/types'
import JourneyEditor from './JourneyEditor.vue'
import {collectJourneyTickets,type JourneySearchMode} from '@/utils/journeySearch'
import {recommendJourneys} from '@/services/api'

const props=defineProps<{modelValue?:Journey|null;request:TripFormData;selectedVisitMinutes?:number;disabled?:boolean;fixedRoute?:boolean}>()
const emit=defineEmits<{(e:'update:modelValue',value:Journey|null):void;(e:'busy',value:boolean):void}>()
const mode=ref<JourneySearchMode>('auto'),priority=ref<'balanced'|'price'|'time'>('balanced'),engine=ref<'default'|'jev'>('default')
const intent=ref(''),priceLimit=ref<number|''>(''),seats=ref<string[]>([]),daytimeHard=ref(false)
const busy=ref(false),status=ref(''),notices=ref<string[]>([]),options=ref<any[]>([]),rankedBy=ref('')
const selected=computed(()=>options.value.find(option=>JSON.stringify(option.journey)===JSON.stringify(props.modelValue))?.id||'')
const manualOpen=ref(false),manualEditor=ref<InstanceType<typeof JourneyEditor>>()
const modes=[{value:'auto' as const,label:'AI 比较铁路和飞机'},{value:'train' as const,label:'只看铁路'},{value:'flight' as const,label:'只看飞机'}]
const directions=[{key:'outbound' as const,label:'去程'},{key:'inbound' as const,label:'返程'}]
const booked=computed(()=>[props.modelValue?.outbound,props.modelValue?.inbound].some(l=>l?.booking_status==='booked'))
const canSearch=computed(()=>!!(props.modelValue?.origin_city?.trim()&&props.request.city&&props.request.start_date&&props.request.end_date)&&props.modelValue?.origin_city!==props.request.city)
const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v))
let generation=0,controller:AbortController|undefined,lastAttempt='',lastAdopted=''
const basis=computed(()=>JSON.stringify([props.request.city,props.request.start_date,props.request.end_date,props.request.companions,props.request.free_text_input,props.modelValue?.origin_city,props.modelValue?.return_city,mode.value,priority.value,engine.value,intent.value,priceLimit.value,seats.value,daytimeHard.value,props.selectedVisitMinutes||0]))
function invalidate(){generation++;controller?.abort();busy.value=false;options.value=[];notices.value=[];lastAttempt='';status.value=''}
watch(busy,v=>emit('busy',v))
watch(basis,(value,old)=>{if(value!==old)invalidate()},{flush:'sync'})
function setRoute(key:'origin_city'|'return_city',text:string){
  if(props.disabled||booked.value)return
  const old=props.modelValue
  if(old?.[key]===text)return
  const journey:Journey=clone(old||{origin_city:'',return_city:'',destination_timezone:'Asia/Shanghai',planning:{arrival_policy:'unreserved',departure_policy:'unreserved'}})
  journey[key]=text
  if(key==='origin_city'&&(!old?.return_city||old.return_city===old.origin_city))journey.return_city=text
  if(key==='return_city'&&!text.trim())journey.return_city=journey.origin_city
  if(key==='origin_city'){journey.outbound=null;journey.inbound=null}else journey.inbound=null
  emit('update:modelValue',journey.origin_city.trim()?journey:null)
}
function manualChanged(value:Journey|null){invalidate();lastAdopted='';emit('update:modelValue',value)}
function stop(){invalidate();status.value='查询已停止。景点可以继续选择，抵离日仍可调整。'}
function adopt(option:any){
  if(props.disabled||busy.value)return
  lastAdopted=JSON.stringify(option.journey)
  emit('update:modelValue',clone(option.journey))
}
function duration(n:number){return `${Math.floor(n/60)}小时${n%60?`${n%60}分`:''}`}
function edgeDays(days:any[]){return days.length>1?[days[0],days[days.length-1]]:days}
function windowLabel(w:any){const lo=Math.max(480,w.start_minutes??0),hi=Math.min(1320,w.end_minutes??1440);const clock=(n:number)=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;return w.unavailable||hi<=lo?'当天在途，景点可放到其他日期':`${clock(lo)}—${clock(hi)} 可安排活动${w.provisional?'（部分时间暂定）':''}`}
async function search(autoAdopt:boolean){
  if(props.disabled||busy.value||!canSearch.value)return false
  invalidate();const current=generation,requestedBasis=basis.value;controller=new AbortController();const signal=controller.signal
  busy.value=true
  try{
    const request=clone({...props.request,journey:props.modelValue})
    const data=await collectJourneyTickets(request,mode.value,signal,text=>{if(current===generation)status.value=text})
    if(current!==generation)return false
    notices.value=data.notices;status.value='正在搭配往返班次，并核对目的地可用时间…'
    const result=await recommendJourneys({request,batches:data.batches,priority:priority.value,engine:engine.value,intent_note:[props.request.free_text_input,intent.value].filter(Boolean).join('；').slice(0,500),
      preferences:{accepted_seats:seats.value,max_reference_fare_per_person:priceLimit.value===''?null:priceLimit.value,daytime_hard:daytimeHard.value},
      selected_visit_minutes:props.selectedVisitMinutes||0,replace_planned:true},signal)
    if(current!==generation)return false
    options.value=result.options;rankedBy.value=result.ranked_by;status.value=result.message;lastAttempt=requestedBasis
    busy.value=false
    if(autoAdopt&&result.options.length)adopt(result.options[0])
    await nextTick()
    return true
  }catch(error:any){
    if(current!==generation)return false
    status.value=typeof error?.response?.data?.detail==='string'?error.response.data.detail:'这次没有完成交通搭配。可重新查询，也可继续选景点，抵离时间保持暂定。'
    lastAttempt=requestedBasis
    return true
  }finally{if(current===generation)busy.value=false}
}
async function prepare(){
  await nextTick()
  if(await manualEditor.value?.validate()===false){manualOpen.value=true;return false}
  if(manualOpen.value)return true
  if(!props.modelValue?.origin_city)return true
  if(props.modelValue.outbound&&props.modelValue.inbound){
    return true
  }
  if(!canSearch.value||lastAttempt===basis.value)return true
  return await search(true)
}
// Changing dates must not keep a generated suggestion for the old trip. Booked
// or manually edited legs remain visible and require explicit correction.
watch([()=>props.request.city,()=>props.request.start_date,()=>props.request.end_date],()=>{
  if(lastAdopted&&JSON.stringify(props.modelValue)===lastAdopted&&!booked.value){
    emit('update:modelValue',{...clone(props.modelValue!),outbound:null,inbound:null});lastAdopted=''
  }
})
onBeforeUnmount(()=>{generation++;controller?.abort()})
defineExpose({prepare})
</script>
<style scoped>
.journey-planner{padding:28px;background:var(--color-bg-primary);color:var(--color-text-primary);border:1px solid var(--color-border);border-radius:20px;margin:24px 0}.planner-heading{display:flex;justify-content:space-between;gap:16px;align-items:center}.planner-heading small{color:var(--color-primary);letter-spacing:.1em}.planner-heading h3{font-size:23px;margin:10px 0}.planner-heading>span,.hint{color:var(--color-text-secondary);font-size:12px}p,li{font-size:13px;line-height:1.8;overflow-wrap:anywhere}.route-fields{display:grid;grid-template-columns:1fr minmax(90px,.6fr) 1fr;gap:18px;margin:24px 0}.destination{display:flex;flex-direction:column;justify-content:center;gap:10px;text-align:center}.destination strong{font-size:22px}.destination small{color:var(--color-text-secondary)}label{display:flex;flex-direction:column;gap:8px;font-size:12px;min-width:0}input,select{font:inherit;font-size:13px;background:var(--desk-input,var(--color-bg-secondary));color:var(--color-text-primary);padding:11px;border:1px solid var(--color-border-strong);border-radius:10px;min-width:0;max-width:100%;box-sizing:border-box}input[type=checkbox]{align-self:flex-start}.transport-choices,.preferences,.planner-actions{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}.preferences>label{flex:1}.intent{margin:18px 0}button{font:inherit;font-size:13px;padding:11px 16px;border:1px solid var(--color-border-strong);border-radius:12px;background:var(--color-bg-secondary);color:var(--color-text-primary);cursor:pointer}button[aria-pressed=true],button.primary{background:var(--color-primary);border-color:var(--color-primary);color:var(--desk-on-accent,#212529)}button:disabled{opacity:.5;cursor:default}details{border-top:1px solid var(--color-border);padding:16px 0;margin-top:14px}summary{cursor:pointer;font-size:13px;line-height:1.8}summary span{font-size:11px;color:var(--color-text-secondary);margin-left:10px}.conditions label{margin:14px 0;max-width:340px}.current-journey{padding:18px;background:var(--color-bg-secondary);border-radius:14px;margin-top:16px}.journey-options{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:14px;margin-top:20px}.journey-options article{padding:18px;border:1px solid var(--color-border);border-radius:14px;min-width:0}.journey-options article.selected{border-color:var(--color-primary)}h4{font-size:16px;margin:0 0 14px}ul{padding-left:18px}.tight{color:var(--color-warning)}:focus-visible{outline:2px solid var(--color-primary);outline-offset:3px}@media(max-width:600px){.journey-planner{padding:20px 16px}.route-fields{grid-template-columns:1fr 1fr}.route-fields>label:last-child{grid-column:1/-1}.planner-heading>span{display:none}.transport-choices button{flex:1;min-width:90px;padding:10px}.preferences{flex-direction:column}.manual-journey :deep(.journey-editor){padding:14px}}
</style>

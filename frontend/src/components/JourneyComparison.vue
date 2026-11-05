<template>
  <section class="comparison">
    <h2>换一班交通，一起调整怎么玩</h2>
    <p>后台查询班次后，先比较能衔接当前安排的选择。想选的班次需要腾出时间时，可以直接生成跨日调整预览，保留景点与原游览时长，再确认变化。</p>
    <TicketAssistant :request="request" :compact="compact" :disabled="disabled || busy" :comparison-full="candidates.length>=6" :schedule-context="{kind:'draft',draft_id:draftId,request,days_detail:daysDetail||[]}" @add="importCandidate" @adopt="adoptTicket" @adjust="adjustTicket" />
    <p v-if="candidates.length >= 6">已有6个备选，请移除一个后再导入。</p>
    <details :open="editorOpen" @toggle="editorOpen=($event.target as HTMLDetailsElement).open">
      <summary>添加或修改一个备选（最多6个）</summary>
      <div class="fields">
        <label>方案名称<input v-model="name" placeholder="例如：高铁往返，晚一点出门" maxlength="80" /></label>
        <label>比较的开始日期<input type="date" v-model="start" /></label>
        <label>比较的结束日期<input type="date" v-model="end" /></label>
      </div>
      <p>可主动试试前后日期或不同车站／机场。日期变化时这里只做比较；原草稿及已订班次不会自动改动。</p>
      <JourneyEditor :destination-city="request.city" v-model="editing" :start-date="start" :end-date="end" :passengers="request.companions?.count || 1" />
      <button :disabled="disabled || busy || (candidates.length>=6 && editingIndex===null) || !editing || !name.trim()" @click="add">{{editingIndex===null?'加入比较':'保存备选修改'}}</button>
    </details>
    <ul class="candidate-list"><li v-for="(c,i) in candidates" :key="i">{{c.name}} <button :disabled="disabled || busy" @click="edit(i)">载入修改</button> <button :disabled="disabled || busy" @click="remove(i)">移除</button></li></ul>
    <button v-if="candidates.length" :disabled="disabled || busy" @click="compare">{{busy?'正在核对…':'比较这些方案'}}</button>
    <p v-if="error" role="alert">{{error}}</p>
    <div class="options">
      <article v-for="option in options" :key="option.index">
        <h3>{{option.name}}</h3>
        <p class="badges" v-if="option.badges.length">{{option.badges.join(' · ')}}</p>
        <p>{{option.start_date}} 至 {{option.end_date}}</p>
        <p v-for="direction in directions" :key="direction.key">
          {{direction.label}}：<template v-if="option.journey[direction.key]">{{option.journey[direction.key].departure_station}} → {{option.journey[direction.key].arrival_station}}<br />{{option.journey[direction.key].departure_time.replace('T',' ')}} — {{option.journey[direction.key].arrival_time.replace('T',' ')}}<br />{{option.journey[direction.key].seat_class || '席别／舱等未填'}}</template><template v-else>未填写</template>
        </p>
        <strong>往返已知费用 ¥{{option.known_total.toFixed(2)}}</strong>
        <p>{{option.cost_complete?'已填齐交通费用，仍需核价':'还有费用未确认，不代表最终总价'}}</p>
        <p>门到门合计：{{option.door_minutes===null?'缺少一段，暂不比较':duration(option.door_minutes)}}<br />包含两端接驳、候车、取行李及目的地入住／退房缓冲。</p>
        <p>中转 {{option.comfort_known?option.connections+'次':'次数未填齐'}}；早出／晚归或跨日 {{option.night_legs}} 段；接驳共 {{duration(option.transfer_minutes)}}。</p>
        <p>“少些折腾”先比较早晚和跨日，再看中转及接驳；座位空间、拥挤和个人体感未评分。</p>
        <p>目的地住 {{option.stay_nights}} 晚；08:00—22:00 内可规划约 {{duration(option.available_minutes)}}。</p>
        <p v-if="option.budget">整趟已知预算 ¥{{option.budget.total.toFixed(2)}}{{option.budget.budget_limit ? ' / 上限 ¥'+option.budget.budget_limit : ''}}<br />{{option.budget.is_within_budget===false?'已知费用已超预算，请调整。':'费用仍有待确认项，暂不能保证在预算内。'}}</p>
        <p v-else>日期不同，酒店、天气与市内活动需重新规划；这里只比较大交通。</p>
        <p>{{option.freshness.join('；')}}</p>
        <details><summary>查看费用条件及对每天的影响</summary>
          <p v-for="d in directions" :key="d.key"><template v-if="option.journey[d.key]">{{d.label}}：票价 {{option.journey[d.key].ticket_total ?? '未知'}} {{option.journey[d.key].currency}}；额外费用 {{extraCostLabel(option.journey[d.key])}}。<br />来源：{{option.journey[d.key].price_note || '未填写'}}；记录时间：{{option.journey[d.key].quoted_at || '未填写'}}。<br />行李：{{option.journey[d.key].baggage_policy || '待确认'}}；退改：{{option.journey[d.key].refund_policy || '待确认'}}。<br /><template v-if="option.journey[d.key].extra_costs">未含税费 {{option.journey[d.key].extra_costs.taxes ?? '未知'}}；行李 {{option.journey[d.key].extra_costs.baggage ?? '未知'}}；接驳 {{option.journey[d.key].extra_costs.transfers ?? '未知'}}；途中住宿 {{option.journey[d.key].extra_costs.overnight ?? '未知'}}。</template></template></p>
          <p v-for="day in option.impacts" :key="day.date">{{day.date}}：{{day.window.notes.join('；')}}<br />{{day.changes.join('；')}}<br /><strong v-if="day.conflicts.length">待调整：{{day.conflicts.join('；')}}</strong></p>
          <p>待确认：{{option.missing.join('；') || '请在出票前再次核对价格与条件'}}</p>
        </details>
        <button :disabled="disabled || busy || !option.same_dates" @click="emit('choose',option.journey)">选择此方案，预览行程变更</button>
        <p v-if="!option.same_dates">如采用这些日期，请从首页创建新规划，以重新查询酒店和天气。</p>
      </article>
    </div>
  </section>
</template>
<script setup lang="ts">
import {extraCostLabel} from '@/utils/journeyCosts'
import {ref,watch} from 'vue'
import TicketAssistant from './TicketAssistant.vue'
import JourneyEditor from './JourneyEditor.vue'
import type {Journey,JourneyLeg,TripFormData} from '@/types'
import {compareJourneys} from '@/services/api'
const props=defineProps<{draftId:string;request:TripFormData;daysDetail?:unknown[];disabled?:boolean;compact?:boolean}>()
const emit=defineEmits<{(e:'choose',value:Journey,ticketBasis?:string):void;(e:'adjust',value:Journey,ticketBasis?:string):void}>()
const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v))
const name=ref(''),start=ref(props.request.start_date),end=ref(props.request.end_date),editing=ref<Journey|null>(clone(props.request.journey || null))
const key='journey-candidates:'+props.draftId
const editorOpen=ref(false),editingIndex=ref<number|null>(null)
const candidates=ref<any[]>([]),options=ref<any[]>([]),busy=ref(false),error=ref('')
try {const saved=JSON.parse(sessionStorage.getItem(key)||'[]');if(Array.isArray(saved))candidates.value=saved.filter(c=>c && typeof c.name==='string' && c.journey && typeof c.journey==='object').slice(0,6)}catch{/* A broken local draft must not block saved travel. */}
let revision=0,requestNumber=0
function invalidate(){revision+=1;options.value=[]}
watch(candidates,v=>{invalidate();try{sessionStorage.setItem(key,JSON.stringify(v))}catch{error.value='本机备选暂存失败，请保留已查询信息。'}},{deep:true,flush:'sync'})
watch(()=>[props.request,props.daysDetail],invalidate,{deep:true,flush:'sync'})
const directions=[{key:'outbound' as const,label:'去程'},{key:'inbound' as const,label:'返程'}]
const duration=(n:number)=>`${Math.floor(n/60)}小时${n%60}分`
function add(){if(!editing.value||(candidates.value.length>=6&&editingIndex.value===null))return;const value={name:name.value.trim(),journey:clone(editing.value),start_date:start.value,end_date:end.value};if(editingIndex.value===null)candidates.value.push(value);else candidates.value.splice(editingIndex.value,1,value);editingIndex.value=null;name.value='';editorOpen.value=false}
function remove(i:number){candidates.value.splice(i,1);if(editingIndex.value===i)editingIndex.value=null;else if(editingIndex.value!==null&&editingIndex.value>i)editingIndex.value-=1}
function edit(i:number){const c=candidates.value[i];name.value=c.name;editing.value=clone(c.journey);start.value=c.start_date;end.value=c.end_date;editingIndex.value=i;editorOpen.value=true}
async function compare(){
 if(props.disabled||busy.value||!candidates.value.length)return
 busy.value=true;error.value='';options.value=[]
 const generation=revision,number=++requestNumber
 const requested=clone(candidates.value)
 try{
  const result=await compareJourneys(props.draftId,requested)
  if(generation===revision && number===requestNumber && !props.disabled)options.value=result.options
 }catch(e:any){
  if(generation===revision && number===requestNumber)error.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'比较未完成，请检查日期、人数、时区和价格来源；已选交通未改变。'
 }finally{if(number===requestNumber)busy.value=false}
}
function importCandidate(candidate:any){if(props.disabled||busy.value||candidates.value.length>=6)return;candidates.value.push(clone(candidate));error.value=''}
function adoptTicket(value:{leg:JourneyLeg;direction:'outbound'|'inbound';ticketBasis?:string}){if(props.disabled||busy.value)return;const journey:Journey=clone(props.request.journey||{origin_city:requestOrigin(value),return_city:requestOrigin(value),destination_timezone:'Asia/Shanghai',outbound:null,inbound:null});journey[value.direction]=clone(value.leg);emit('choose',journey,value.ticketBasis)}
function adjustTicket(value:{leg:JourneyLeg;direction?:'outbound'|'inbound';ticketBasis?:string}){if(props.disabled||busy.value)return;const direction=value.direction||'outbound';const journey:Journey=clone(props.request.journey||{origin_city:requestOrigin({...value,direction}),return_city:requestOrigin({...value,direction}),destination_timezone:'Asia/Shanghai',outbound:null,inbound:null});journey[direction]=clone(value.leg);emit('adjust',journey,value.ticketBasis)}
function requestOrigin(value:{leg:JourneyLeg;direction:'outbound'|'inbound'}){return value.direction==='outbound'?value.leg.departure_station:value.leg.arrival_station}
</script>
<style scoped>
.comparison{padding:24px;border:2px solid #24362e;background:var(--white,#fff);color:#24362e;margin:20px 0}.comparison h2{font-size:22px;margin-top:0}.comparison p{line-height:1.7;font-size:14px;overflow-wrap:anywhere}.source-actions,.candidate-list li{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:12px 0}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}label{display:flex;flex-direction:column;gap:6px}input{padding:8px;border:1px solid #708579;min-width:0;background:white;color:#24362e}button{cursor:pointer;border:1px solid #24362e;padding:9px 14px;background:#e6efe8;color:#183528;border-radius:4px}button:disabled{cursor:not-allowed;opacity:.55}summary{cursor:pointer;padding:10px 0}.options{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px;margin-top:20px}article{border:1px solid #9eb4a5;border-radius:8px;padding:18px;min-width:0}.badges{color:#17613c;font-weight:700}.candidate-list{padding-left:0;list-style:none}a{color:#145d3d;text-decoration:underline}@media(max-width:480px){.comparison{padding:14px}article{padding:12px}}
</style>

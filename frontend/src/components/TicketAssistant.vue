<template>
  <section class="ticket-assistant" aria-label="查票与文字导入">
    <h3>{{compact?'找一班更合适的交通':'查票、筛选，再采用合适的一班'}}</h3>
    <p>{{compact?'按行程日期查找班次，采用前会先预览日程调整。':'确认本段日期和起终点，后台查票后比较可行班次，无需安装扩展；需要登录或验证时会提示处理。'}}</p>
    <div v-if="compact" class="quick-query">
      <div v-if="!singleSegment" class="query-switch" role="group" aria-label="查询方向"><button type="button" :aria-pressed="query.direction==='outbound'" :disabled="disabled" @click="query.direction='outbound'">去程</button><button type="button" :aria-pressed="query.direction==='inbound'" :disabled="disabled" @click="query.direction='inbound'">返程</button></div>
      <div class="query-switch query-modes" role="group" aria-label="查询交通方式"><button type="button" :aria-pressed="query.mode==='train'" :disabled="disabled" @click="query.mode='train'">高铁 / 火车</button><button type="button" :aria-pressed="query.mode==='flight'" :disabled="disabled" @click="query.mode='flight'">飞机</button></div>
    </div>
    <details class="query-settings" :open="settingsOpen" @toggle="settingsOpen=($event.target as HTMLDetailsElement).open"><summary><span>{{query.from || '出发地'}} <b>→</b> {{query.to || '目的地'}}</span><span>{{query.date}} · {{query.passengers}} 人 · {{query.mode==='train'?'高铁 / 火车':'飞机'}}<small>{{settingsOpen?'收起查询条件 −':'修改查询条件 ＋'}}</small></span></summary><div class="ticket-fields">
      <label v-if="!singleSegment">查询方向<select v-model="query.direction"><option value="outbound">去程</option><option value="inbound">返程</option></select></label>
      <label>查询交通方式<select v-model="query.mode"><option value="train">火车／高铁</option><option value="flight">飞机</option></select></label>
      <label>查询出发日期<input type="date" v-model="query.date" /></label>
      <label>查询出发地<input v-model="query.from" :list="listId" placeholder="城市或具体车站，不填详细住址" maxlength="80" /></label>
      <label>查询目的地<input v-model="query.to" :list="listId" placeholder="城市或具体车站" maxlength="80" /></label>
      <label v-if="query.mode==='train'">后台铁路出发地范围<select v-model="query.fromScope"><option value="auto">自动判断</option><option value="exact">仅该车站</option><option value="city">城市内车站</option></select></label>
      <label v-if="query.mode==='train'">后台铁路目的地范围<select v-model="query.toScope"><option value="auto">自动判断</option><option value="exact">仅该车站</option><option value="city">城市内车站</option></select></label>
      <label>查询同行人数<input type="number" min="1" max="20" v-model.number="query.passengers" /></label>
    </div>
    </details><datalist :id="listId"><option v-for="place in suggestions" :key="place" :value="place" /></datalist>
    <p v-if="query.mode==='flight'" class="muted">{{ link.note }}</p>
    <BrowserTicketAssistant :query="query" :disabled="disabled" :context-key="JSON.stringify(request)" :schedule-context="scheduleContext" @adopt="emit('adopt',$event)" @adjust="emit('adjust',$event)"><template #conflict-actions><slot name="conflict-actions" /></template></BrowserTicketAssistant>
    <details><summary>直接去网站查票／复制查询条件</summary>
    <p>{{ link.note }}</p>
    <div class="ticket-actions">
      <a :href="link.url" target="_blank" rel="noopener noreferrer">{{ link.prefilled?'带日期和起终点去查票':'打开查票网站' }} ↗</a>
      <button :disabled="!!queryError(query)" @click="copy">复制查询条件</button>
    </div>
    <p class="muted">直接跳转不会自动带回；自动获取候选请使用上方后台查询或扩展备用方式。网站可能要求登录或重新选择条件。</p>
    <p v-if="copyMessage" role="status">{{ copyMessage }}</p>
    <details><summary>查看／手动复制查询条件</summary><textarea aria-label="查询条件" readonly :value="queryText(query)" rows="6" @focus="($event.target as HTMLTextAreaElement).select()" /></details>
    </details>
    <details class="import-panel" :open="importOpen" @toggle="importOpen=($event.target as HTMLDetailsElement).open">
      <summary>粘贴车票文字，导入{{ singleSegment?'本段':query.direction==='outbound'?'去程':'返程' }}</summary>
      <p>每次一段，仅在此浏览器解析，不调用模型。请只粘贴班次信息，不包含姓名、证件或订单号。确认后清空原文。</p>
      <label>车票文字<textarea v-model="raw" maxlength="8000" rows="5" :placeholder="example" /></label>
      <div class="ticket-actions"><button :disabled="!raw.trim()||disabled" @click="parse">识别并预览</button><button v-if="raw||preview" @click="clearPreview">清空导入文字</button></div>
      <div v-if="preview" class="ticket-preview">
        <h4>核对这一段，再放入待比较车票</h4>
        <ul><li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li></ul>
        <div class="ticket-fields">
          <label v-if="!singleSegment">导入方向<select v-model="importDirection"><option value="outbound">去程</option><option value="inbound">返程</option></select></label>
          <label>导入交通方式<select v-model="preview.mode"><option value="train">铁路</option><option value="flight">飞机</option></select></label>
          <label>班次<input v-model="preview.service" maxlength="60" /></label>
          <label>出发站／机场<input v-model="preview.from" maxlength="120" /></label>
          <label>到达站／机场<input v-model="preview.to" maxlength="120" /></label>
          <label>出发日期时间<input v-model="preview.departure" type="datetime-local" /></label>
          <label>到达日期时间<input v-model="preview.arrival" type="datetime-local" /></label>
          <label>票价适用人数<input v-model.number="preview.passengers" type="number" min="1" max="20" /></label>
          <label>识别金额<input type="number" min="0" step="0.01" :value="preview.amount??''" @input="setAmount" placeholder="未知留空" /></label>
          <label>金额口径<select v-model="preview.basis"><option value="unknown">尚未确认</option><option value="person">每人同价（按人数计算）</option><option value="total">全体总额（不再乘人数）</option></select></label>
          <label>币种<input v-model="preview.currency" maxlength="3" /></label>
          <label>席别／舱等<input v-model="preview.seat" maxlength="80" /></label>
          <label>查票来源<select v-model="source"><option>12306</option><option>携程</option><option>航空公司官网</option><option>其他渠道</option></select></label>
        </div>
        <p>全体票价：{{ wholePrice===null?'待确认':wholePrice+' '+preview.currency }}。额外税费、行李和接驳未填，不代表免费。导入默认“正在考虑”，不认定已订或已支付。</p>
        <p v-if="previewError(preview)" role="alert">{{ previewError(preview) }}</p>
        <label class="confirm"><input type="checkbox" v-model="confirmed" />我已核对日期、方向、站点、人数和金额；时间为中国标准时间</label>
        <p v-if="pending[importDirection]">待比较车票中已有这一方向；确认会替换该段待加入内容，已保存行程不受影响。</p>
        <button :disabled="disabled||!confirmed||!!previewError(preview)" @click="confirmImport">{{ pending[importDirection]?'替换待比较的这一段':'确认这段车票' }}</button>
      </div>
    </details>
    <section v-if="pending.outbound||pending.inbound" class="pending" aria-label="待加入的车票">
      <h4>把这些车票组成一个新备选</h4>
      <p v-for="d in directions" :key="d.key">{{ d.label }}：<template v-if="pending[d.key]">{{ pending[d.key]!.service_number }} {{ pending[d.key]!.departure_station }} → {{ pending[d.key]!.arrival_station }}，{{ pending[d.key]!.departure_time.replace('T',' ') }} — {{ pending[d.key]!.arrival_time.replace('T',' ') }}<button @click="pending[d.key]=null">移除{{d.label}}</button></template><template v-else>尚未导入，可继续切换方向导入，也可先比较单程。</template></p>
      <div class="ticket-fields">
        <label>新备选名称<input v-model="candidateName" maxlength="80" /></label>
        <label v-if="!singleSegment">旅行出发城市<input v-model="originCity" maxlength="80" /></label>
        <label v-if="!singleSegment">旅行返回城市<input v-model="returnCity" maxlength="80" /></label>
      </div>
      <p v-if="singleSegment">请核对本段的日期、车站和人数。接驳和缓冲仍是默认估计，可在手动填写中修改。</p>
      <p v-else>将使用当前草稿的旅行日期 {{request.start_date}} 至 {{request.end_date}}；如需比较其他日期，可加入后“载入修改”。接驳和缓冲仍是默认估计，请在备选中检查。</p>
      <button :disabled="disabled||comparisonFull||!candidateName.trim()||!originCity.trim()||!returnCity.trim()" @click="addCandidate">作为新备选加入比较</button>
      <p v-if="addedMessage" role="status">{{addedMessage}}</p>
    </section>
    <p v-else-if="addedMessage" role="status">{{addedMessage}}</p>
  </section>
</template>
<script setup lang="ts">
import {computed,reactive,ref,watch} from 'vue'
import type {Journey,JourneyLeg,TripFormData} from '@/types'
import {stations,flightCities,queryError,queryText,searchLink,type TicketQuery} from '@/utils/ticketSearch'
import {parseTicket,previewError,ticketLeg,type TicketPreview} from '@/utils/ticketImport'
import BrowserTicketAssistant from './BrowserTicketAssistant.vue'
import type {TicketScheduleContext} from '@/utils/ticketSchedule'
const props=defineProps<{request:TripFormData;disabled?:boolean;singleSegment?:boolean;compact?:boolean;comparisonFull?:boolean;scheduleContext?:TicketScheduleContext}>()
const emit=defineEmits<{(e:'adjust',value:{leg:JourneyLeg;ticketBasis?:string;direction?:'outbound'|'inbound'}):void;(e:'add',value:{name:string;journey:Journey;start_date:string;end_date:string}):void;(e:'adopt',value:{leg:JourneyLeg;direction:'outbound'|'inbound';ticketBasis?:string}):void}>()
const directions=computed(()=>props.singleSegment?[{key:'outbound' as const,label:'本段'}]:[{key:'outbound' as const,label:'去程'},{key:'inbound' as const,label:'返程'}])
const query=reactive<TicketQuery>({mode:props.request.journey?.outbound?.mode==='flight'?'flight':'train',direction:'outbound',from:props.request.journey?.origin_city||'',to:props.request.city||'',date:props.request.start_date||'',passengers:props.request.companions?.count||1,fromScope:'auto',toScope:'auto'})
const settingsOpen=ref(!props.singleSegment&&(!props.compact||!query.from||!query.to))
const originCity=ref(props.request.journey?.origin_city||''),returnCity=ref(props.request.journey?.return_city||'')
const candidateName=ref('导入的交通备选'),pending=reactive<{outbound:JourneyLeg|null;inbound:JourneyLeg|null}>({outbound:null,inbound:null})
const raw=ref(''),preview=ref<TicketPreview|null>(null),source=ref('12306'),confirmed=ref(false),importOpen=ref(false),importDirection=ref<'outbound'|'inbound'>('outbound')
const copyMessage=ref(''),addedMessage=ref('')
const link=computed(()=>searchLink(query)),listId='ticket-query-places'
const suggestions=computed(()=>query.mode==='train'?Object.keys(stations):Object.keys(flightCities))
const example=computed(()=>`${query.date} 上海虹桥 → 北京南 G8 08:00—12:26 二等座 每人661元\n（仅为格式示例，不代表实际报价）`)
const wholePrice=computed(()=>preview.value?.amount==null||preview.value.basis==='unknown'?null:Math.round(preview.value.amount*(preview.value.basis==='person'?preview.value.passengers:1)*100)/100)
watch(()=>query.direction,d=>{query.mode=props.request.journey?.[d]?.mode==='flight'?'flight':'train';query.date=(d==='outbound'?props.request.start_date:props.request.end_date)||'';query.from=d==='outbound'?originCity.value:props.request.city||'';query.to=d==='outbound'?props.request.city||'':returnCity.value||originCity.value})
watch([()=>query.passengers,()=>props.request.hotel_occupancy],()=>{
 const o=props.request.hotel_occupancy
 query.adultPassengers=o && !o.children_ages.length && o.room_count*o.adults_per_room===query.passengers ? query.passengers : undefined
},{immediate:true})
// A changed saved trip invalidates local imports and the old search defaults.
watch(()=>JSON.stringify(props.request),()=>{
 originCity.value=props.request.journey?.origin_city||''
 returnCity.value=props.request.journey?.return_city||''
 const d=query.direction
 query.mode=props.request.journey?.[d]?.mode==='flight'?'flight':'train'
 query.date=(d==='outbound'?props.request.start_date:props.request.end_date)||''
 query.from=d==='outbound'?originCity.value:props.request.city||''
 query.to=d==='outbound'?props.request.city||'':returnCity.value||originCity.value
 query.passengers=props.request.companions?.count||1
 pending.outbound=null;pending.inbound=null;clearPreview();addedMessage.value='';copyMessage.value=''
})
watch(query,()=>{copyMessage.value=''},{deep:true})
watch([preview,importDirection,source],()=>{confirmed.value=false},{deep:true})
watch(raw,()=>{preview.value=null;confirmed.value=false})
async function copy(){const text=queryText(query);try{if(!navigator.clipboard?.writeText)throw new Error();await navigator.clipboard.writeText(text);copyMessage.value='查询条件已复制。'}catch{copyMessage.value='未能访问剪贴板，请展开“查看／手动复制查询条件”，选中文字复制。'}}
function parse(){preview.value=parseTicket(raw.value,query.mode,query.date,query.passengers);importDirection.value=query.direction;source.value=query.mode==='train'?'12306':'携程';confirmed.value=false}
function setAmount(e:Event){const value=(e.target as HTMLInputElement).value;if(preview.value)preview.value.amount=value===''?null:Number(value)}
function clearPreview(){raw.value='';preview.value=null;confirmed.value=false}
function confirmImport(){if(!preview.value||!confirmed.value||props.disabled||previewError(preview.value))return;pending[importDirection.value]=ticketLeg(preview.value,source.value);if(!originCity.value)originCity.value=query.direction==='outbound'?query.from:query.to;if(!returnCity.value)returnCity.value=originCity.value;clearPreview();importOpen.value=false;addedMessage.value='已放入待比较车票，尚未修改行程。'}
function addCandidate(){if(props.disabled||props.comparisonFull||!candidateName.value.trim()||!originCity.value.trim()||!returnCity.value.trim())return;emit('add',{name:candidateName.value.trim(),journey:JSON.parse(JSON.stringify({origin_city:originCity.value.trim(),return_city:returnCity.value.trim(),destination_timezone:props.request.journey?.destination_timezone||'Asia/Shanghai',...pending})),start_date:props.request.start_date,end_date:props.request.end_date});pending.outbound=null;pending.inbound=null;addedMessage.value=props.singleSegment?'已加入本段备选。可继续导入另一方案，或选择一段查看整趟影响。':'已加入下方备选。可继续导入另一方案，或点击“比较这些方案”。'}
</script>
<style scoped>
.ticket-assistant{background:#f2f6f3;border:1px solid #a5b7ab;border-radius:8px;padding:18px;margin:18px 0;color:#24362e}.ticket-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:12px;margin:14px 0}label{display:flex;flex-direction:column;gap:6px;font-size:14px}.confirm{flex-direction:row;align-items:flex-start;margin:14px 0}input,select,textarea{font:inherit;border:1px solid #708579;padding:9px;background:#fff;color:#24362e;border-radius:4px;min-width:0;max-width:100%;box-sizing:border-box}textarea{width:100%;resize:vertical}input[type=checkbox]{margin:3px 0;width:auto}.ticket-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:12px 0}button,a{font:inherit;cursor:pointer;border:1px solid #365b43;border-radius:4px;padding:9px 12px;color:#183d29;background:#fff}button:disabled{opacity:.5;cursor:not-allowed}a{text-decoration:underline}summary{cursor:pointer;padding:12px 0}p,li{font-size:14px;line-height:1.7;overflow-wrap:anywhere}.muted{color:#52655a}.ticket-preview,.pending{border-top:1px solid #a5b7ab;margin-top:12px;padding-top:8px}button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #215bc5;outline-offset:2px}@media(max-width:480px){.ticket-assistant{padding:12px}.ticket-actions{align-items:stretch;flex-direction:column}}
</style>

<style scoped>
.quick-query{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;margin:24px 0 12px}.query-switch{display:flex;gap:4px;background:var(--color-bg-secondary);border:1px solid var(--color-border);border-radius:10px;padding:4px}.query-switch button{font-size:12px;min-height:36px;padding:8px 18px;border:0;border-radius:7px;background:transparent;color:var(--color-text-secondary)}.query-switch button[aria-pressed=true]{background:var(--color-bg-primary);color:var(--color-text-primary);box-shadow:0 1px 4px #0000000c}.query-modes{background:transparent;border:0;padding:0}.query-modes button[aria-pressed=true]{background:var(--color-bg-secondary);box-shadow:none}
.query-settings{border:1px solid #ffffff18;border-radius:14px;padding:0 18px;margin:18px 0}.query-settings>summary{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:18px 0;cursor:pointer;font-size:16px;list-style:none}.query-settings>summary>span:last-child{font-size:12px;text-align:right}.query-settings small{display:block;color:var(--trip-accent,#8c623d);font-size:10px;margin-top:6px}.query-settings b{font-weight:400;opacity:.5;margin:0 16px}.query-settings .ticket-fields{padding:0 0 18px}.query-settings[open]>summary{margin-bottom:12px;border-bottom:1px solid #ffffff18}@media(max-width:600px){.query-settings>summary{flex-wrap:wrap}.query-settings>summary>span:last-child{text-align:left;font-size:11px}.query-settings>summary>span:first-child{width:100%}}
</style>

<template>
  <section class="browser-tickets" aria-label="浏览器查票与AI筛选">
    <h4>查票后，比较合适的班次</h4>
    <BackgroundTicketSearch ref="backgroundSearch" :query="query" :disabled="disabled" :context-key="JSON.stringify([contextKey,scheduleContext])" @reset="invalidate" @candidates="backgroundCandidates" />
    <p>候选带回后先核对已保存安排和缓冲。未设优先级时展示不同取舍；价格和车程直接排序，兼顾或日间软偏好使用 AI 筛选。采用后预览并确认保存。</p>
    <label>这次更看重<select v-model="priority" :disabled="busy"><option value="unspecified">先看不同选择</option><option value="balanced">时间与价格兼顾</option><option value="price">列表参考价较低</option><option value="time">车程较短</option><option value="daytime">白天出发和到达</option></select></label>
    <label v-if="usesAI" class="ticket-engine">
      推荐方式
      <select v-model="engine" :disabled="busy">
        <option value="default">默认 AI</option>
        <option value="jev">Jev（WindHub）</option>
      </select>
    </label>
    <p v-if="priority==='daytime'">软偏好：尽量 {{departureAfter}} 后出发、{{arrivalBefore}} 前到达且不跨日；其他可行班次仍可作备选。</p>
    <details class="ticket-extra"><summary>更多要求（可选）</summary>
      <label>接受席别（不选表示不限）<select v-model="acceptedSeats" multiple aria-label="接受席别" :disabled="busy"><option v-for="seat in seatOptions" :key="seat" :value="seat">{{seat}}</option></select></label>
      <label>每人列表参考价上限（元）<input v-model.number="priceLimit" type="number" min="0" max="1000000" :disabled="busy" /></label>
      <p>仅约束列表参考价，同行总价、税费与票种仍待核对；不会自动更换席别或提高上限。</p>
      <label>尽量何时后出发<input v-model="departureAfter" type="time" :disabled="busy" /></label><label>尽量何时前到达<input v-model="arrivalBefore" type="time" :disabled="busy" /></label>
      <label><input v-model="daytimeHard" type="checkbox" :disabled="busy" />上述时段必须满足（且不跨日）</label>
    </details>
    <div v-if="preferenceExcluded.length" role="status"><p>有 {{preferenceExcluded.length}} 条不满足本次明确条件，可修改更多要求或重新查询；未自动放宽条件。</p><details><summary>查看条件不匹配原因</summary><p v-for="p in preferenceExcluded" :key="p.candidate.id">{{p.candidate.service}}：{{p.reasons.join('；')}}</p></details></div>
    <div class="actions"><button v-if="tickets.length" :disabled="busy||disabled" @click="rank">{{busy?'正在筛选…':usesAI?'重新AI筛选':'重新筛选'}}</button></div>
    <p v-if="status" role="status">{{status}}</p>
    <details class="extension-fallback"><summary>使用已有浏览器扩展（备用方式）</summary>
    <div class="actions"><button :disabled="disabled||busy||!!queryError(query)||!link.prefilled" @click="start">{{waiting?'重新发起查票':'打开查票并自动带回'}}</button></div>
    <p v-if="updateAvailable" role="status">已连接浏览器助手 {{extensionVersion}}，当前提供 {{currentExtensionVersion}}。更新后会校验铁路查询起终点变化，并保留航班继续加载保护。</p>
    <details v-if="!connected||updateAvailable"><summary>{{updateAvailable?'更新浏览器查票助手':'首次使用：连接浏览器查票助手'}}</summary><p>在 Chrome 或 Edge 安装本机“旅行规划查票助手”，并在同一个浏览器打开本应用。安装后刷新此页。扩展只为本次发起的查询读取票务列表；兼顾或日间软偏好筛选时，候选字段交给当前配置的 AI。</p><p>安装包：<a href="/ticket-assistant-extension.zip" download>下载浏览器助手</a>。解压后，在浏览器扩展管理页打开开发者模式，选择“加载已解压的扩展程序”，选中解压目录。更新已有扩展时，将文件解压到原目录，点击“重新加载”，再刷新规划页和查票页。安装包内附具体说明。</p></details>
    <p v-if="!link.prefilled">{{link.note}}</p>
    </details>
    <div v-if="excluded.length && !recommendations.length && !busy" class="conflict-help" role="status"><strong>这些班次需要联动调整景点</strong><p v-if="scheduleContext?.kind==='multi'">选择下方班次，可生成两侧当天的调整预览，取消的景点、用餐和休息会单独列出。若手动编辑城市工作副本，仍需同步回整趟旅行。</p><p v-else>选择下方班次，让系统尝试把可移动的景点安排到其他时段或日期。锁定和固定预约会保留，放不下的景点列入待安排。</p><slot name="conflict-actions" /></div>
    <details v-if="excluded.length" class="exclusions" :open="!recommendations.length"><summary>{{excluded.length}} 条需要调整日程的班次</summary><p>这些候选已排除在直接衔接推荐之外。可以预览联动调整，确认前不改变已保存安排。</p><div class="exclusion-list"><details v-for="e in excluded" :key="e.candidate.id"><summary>{{e.candidate.service}} · {{e.candidate.departure.replace('T',' ')}} — {{e.candidate.arrival?.slice(11,16)}}<small>{{e.conflicts[0]}}</small></summary><ul><li v-for="reason in e.conflicts" :key="reason">{{reason}}</li></ul><button v-if="scheduleContext?.kind==='multi' && e.leg" :disabled="disabled||busy||waiting" @click="emit('adjust',{leg:e.leg,ticketBasis})">按此班次调整两侧当天安排</button><button v-else-if="scheduleContext?.kind==='draft' && e.leg" :disabled="disabled||busy||waiting" @click="emit('adjust',{leg:e.leg,ticketBasis,direction:query.direction})">按此班次重新安排</button></details></div></details>
    <div v-if="recommendations.length" class="recommendations">
      <p>{{rankingLabel}} · 本次带回 {{tickets.length}} 条，展示 {{recommendations.length}} 个候选；每批最多80条，不代表完整列表。<span v-if="usingBackground">可重新后台查询，获取更新候选。</span><span v-else>网站加载更多结果后，可点击网站右下角“重新带回当前列表”。</span></p>
      <article v-for="(r,index) in recommendations" :key="r.candidate.id">
        <h5>{{rankedBy==='options'?'':(index+1)+'. '}}{{r.candidate.service}} · {{r.candidate.seat||'席别待确认'}}</h5>
        <p>{{r.candidate.from_station}} → {{r.candidate.to_station}}<br />{{r.candidate.departure.replace('T',' ')}} — {{r.candidate.arrival.replace('T',' ')}}</p>
        <strong v-if="r.candidate.fare_per_person===null">列表参考价未知</strong>
        <strong v-else>列表每人参考 ¥{{r.candidate.fare_per_person}}{{r.candidate.mode==='flight'?' 起':''}}</strong>
        <p v-if="r.badges?.length">{{r.badges.join(' · ')}}</p>
        <p v-if="r.fit_status==='requires_adjustment'"><strong>需调整后可用</strong>：采用前在预览核对</p><p v-else-if="r.fit_status==='direct'">原安排可用</p>
        <ul v-if="r.adjustments?.length"><li v-for="a in r.adjustments" :key="a.date+a.kind+a.ref_name">{{a.date}} {{a.city}} {{a.ref_name}}：{{a.before}} → {{a.after}}</li></ul>
        <ul class="ticket-key-reasons"><li v-for="reason in r.reasons.filter((text:string)=>/剩余|时间较紧|同行总额|不计入预算/.test(text))" :key="reason">{{reason}}</li></ul><details class="ticket-reason-details"><summary>推荐依据与完整核对说明</summary><ul><li v-for="reason in r.reasons" :key="reason">{{reason}}</li></ul></details>
        <button :disabled="busy||disabled||waiting" @click="adopt(r.leg)">采用这班，预览行程</button>
      </article>
    </div>
  </section>
</template>
<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref,watch} from 'vue'
import type {JourneyLeg} from '@/types'
import {queryError,searchLink,type TicketQuery} from '@/utils/ticketSearch'
import {recommendTickets} from '@/services/api'
import BackgroundTicketSearch from './BackgroundTicketSearch.vue'
import type {TicketScheduleContext} from '@/utils/ticketSchedule'
const props=defineProps<{query:TicketQuery;disabled?:boolean;contextKey:string;scheduleContext?:TicketScheduleContext}>()
const emit=defineEmits<{(e:'adjust',value:{leg:JourneyLeg;ticketBasis?:string;direction?:'outbound'|'inbound'}):void;(e:'adopt',value:{leg:JourneyLeg;direction:'outbound'|'inbound';ticketBasis?:string}):void}>()
const priority=ref('unspecified'),connected=ref(false),waiting=ref(false),busy=ref(false),status=ref(''),tickets=ref<any[]>([]),recommendations=ref<any[]>([]),rankedBy=ref('')
const engine=ref<'default'|'jev'>('default')
const usesAI=computed(()=>['balanced','daytime'].includes(priority.value))
const rankingLabels:Record<string,string>={options:'不同取舍 · 未设唯一首选',ai:'AI推荐',jev:'Jev 推荐',metric:'按所选指标排序'}
const rankingLabel=computed(()=>rankingLabels[rankedBy.value]||'规则排序')
const backgroundSearch=ref<InstanceType<typeof BackgroundTicketSearch>>()
const usingBackground=ref(false)
function backgroundCandidates(values:any[]){usingBackground.value=true;tickets.value=values;void rank()}
const currentExtensionVersion='0.2.2',extensionVersion=ref('')
const updateAvailable=computed(()=>{if(!extensionVersion.value)return false;const installed=extensionVersion.value.split('.').map(Number),latest=currentExtensionVersion.split('.').map(Number);for(let i=0;i<3;i++){if(installed[i]!==latest[i])return installed[i]!<latest[i]!}return false})
const link=computed(()=>searchLink(props.query))
const excluded=ref<any[]>([]),ticketBasis=ref(''),preferenceExcluded=ref<any[]>([])
const acceptedSeats=ref<string[]>([]),priceLimit=ref<number|''>(''),departureAfter=ref('07:00'),arrivalBefore=ref('22:00'),daytimeHard=ref(false)
const seatOptions=computed(()=>Array.from(new Set([...(props.query.mode==='train'?['二等座','一等座','商务座','硬座','硬卧','软卧','二等卧']:['经济舱','商务舱','头等舱']),...tickets.value.map(t=>t.seat).filter(Boolean)])))
let requestId='',generation=0,controller:AbortController|undefined,connectionTimer:ReturnType<typeof setTimeout>|undefined,waitTimer:ReturnType<typeof setTimeout>|undefined,expiryTimer:ReturnType<typeof setTimeout>|undefined
function post(type:string,extra:Record<string,unknown>={}){window.postMessage({channel:'ltp-ticket-app-v1',type,requestId,...extra},window.location.origin)}
function invalidate(){if(requestId)post('ltp-cancel');requestId='';generation++;controller?.abort();clearTimeout(connectionTimer);clearTimeout(waitTimer);clearTimeout(expiryTimer);waiting.value=false;busy.value=false;tickets.value=[];recommendations.value=[];excluded.value=[];preferenceExcluded.value=[];ticketBasis.value='';status.value=''}
watch([()=>JSON.stringify(props.query),()=>props.contextKey,()=>JSON.stringify(props.scheduleContext)],invalidate)
watch([priority,engine,acceptedSeats,priceLimit,departureAfter,arrivalBefore,daytimeHard],()=>{generation++;controller?.abort();busy.value=false;recommendations.value=[];excluded.value=[];preferenceExcluded.value=[];ticketBasis.value='';if(tickets.value.length)status.value='偏好已改变或推荐方式已更新，点击重新筛选。'})
function start(){
  if(props.disabled||busy.value||queryError(props.query)||!link.value.prefilled)return
  backgroundSearch.value?.stop(false)
  usingBackground.value=false
  invalidate();requestId=crypto.randomUUID();waiting.value=true;status.value='正在连接浏览器助手…'
  post('ltp-start',{url:link.value.url,query:{...props.query}})
  expiryTimer=setTimeout(()=>{invalidate();status.value='本次查票连接已过期，请重新查询以获取更新列表。'},15*60*1000)
  connectionTimer=setTimeout(()=>{if(waiting.value&&!connected.value){waiting.value=false;status.value=['5173','4173','15173'].includes(window.location.port)?'未连接到浏览器助手。请先安装并刷新此页，或继续使用下方网站跳转与文字导入。':'未连接到浏览器助手：当前地址不在浏览器助手支持范围内。请在 Chrome 或 Edge 使用本机 5173、4173 或 15173 端口的规划页；也可使用下方网站跳转与文字导入。'}},2200)
  waitTimer=setTimeout(()=>{if(waiting.value){waiting.value=false;status.value='尚未收到列表。请完成票务网站查询或验证，再点击网站右下角重新带回；也可重新发起。'}},90000)
}
async function rank(){
  if(props.disabled||!tickets.value.length)return
  const current=++generation;controller?.abort();controller=new AbortController();busy.value=true;recommendations.value=[];excluded.value=[];preferenceExcluded.value=[];ticketBasis.value='';status.value='候选已带回，正在核对安排并筛选…'
  try{
    const result=await recommendTickets({query:{mode:props.query.mode,direction:props.query.direction,from_place:props.query.from,to_place:props.query.to,date:props.query.date,passengers:props.query.passengers,priority:priority.value,preferences:{accepted_seats:acceptedSeats.value,max_reference_fare_per_person:priceLimit.value===''?null:priceLimit.value,departure_after:departureAfter.value,arrival_before:arrivalBefore.value,daytime_hard:daytimeHard.value}},candidates:tickets.value,context:props.scheduleContext,engine:usesAI.value?engine.value:'default'},controller.signal)
    if(current!==generation)return
    recommendations.value=result.recommendations;excluded.value=result.excluded||[];preferenceExcluded.value=result.preference_excluded||[];ticketBasis.value=result.schedule_basis||'';rankedBy.value=result.ranked_by;status.value=result.message
  }catch(e:any){if(current===generation){recommendations.value=[];ticketBasis.value='';status.value=e?.response?.status===409?'安排已改变，请重新读取草稿后查票；旧推荐未采用。':'本次筛选未完成，候选已保留，可重试；已保存行程未改变。'}}finally{if(current===generation)busy.value=false}
}
function receive(event:MessageEvent){
  if(event.source!==window||event.origin!==window.location.origin||event.data?.channel!=='ltp-ticket-extension-v1')return
  const m=event.data
  if(m.type==='ltp-ping-reply'&&typeof m.version==='string'&&/^\d+\.\d+\.\d+$/.test(m.version)){connected.value=true;extensionVersion.value=m.version;return}
  if(!requestId||m.requestId!==requestId)return
  if(m.error){generation++;controller?.abort();clearTimeout(connectionTimer);clearTimeout(waitTimer);waiting.value=false;busy.value=false;recommendations.value=[];excluded.value=[];preferenceExcluded.value=[];ticketBasis.value='';status.value=m.error;return}
  if(m.type==='ltp-start-reply'&&m.started){connected.value=true;clearTimeout(connectionTimer);status.value='查票页已打开，列表载入后会自动带回。遇到网站验证请在查票页完成。'}
  if(m.type==='ltp-result'&&m.status==='empty'&&Array.isArray(m.candidates)&&m.candidates.length===0){generation++;controller?.abort();busy.value=false;waiting.value=false;clearTimeout(connectionTimer);clearTimeout(waitTimer);tickets.value=[];recommendations.value=[];excluded.value=[];preferenceExcluded.value=[];ticketBasis.value='';status.value='票务网站当前没有返回可读取候选，请在查票页核对条件或登录后重试。已保存行程未改变。';return}
  if(m.type==='ltp-result'&&Array.isArray(m.candidates)&&m.candidates.length>0&&m.candidates.length<=80){connected.value=true;clearTimeout(connectionTimer);clearTimeout(waitTimer);waiting.value=false;tickets.value=m.candidates;void rank()}
}
function adopt(leg:JourneyLeg){if(props.disabled||busy.value||waiting.value)return;emit('adopt',{leg:JSON.parse(JSON.stringify(leg)),direction:props.query.direction,...(ticketBasis.value?{ticketBasis:ticketBasis.value}:{})})}
onMounted(()=>{window.addEventListener('message',receive);post('ltp-ping')})
onBeforeUnmount(()=>{invalidate();window.removeEventListener('message',receive)})
</script>
<style scoped>
.ticket-engine{margin-top:12px}
.ticket-extra{margin:12px 0}.ticket-extra label{margin:10px 0;max-width:100%}.ticket-extra input{font:inherit;max-width:100%;box-sizing:border-box}.ticket-extra select[multiple]{min-height:90px}.ticket-extra input[type=checkbox]{width:auto;align-self:flex-start}

.conflict-help{padding:14px;background:#fff4e3;border:1px solid #d4b984;border-radius:10px;margin:16px 0}.exclusion-list{max-height:420px;overflow:auto;border-top:1px solid #d8e1da}.exclusion-list>details{padding:12px 4px;border-bottom:1px solid #d8e1da}.exclusion-list small{display:block;line-height:1.6;color:#52655a;margin:6px 0}.exclusion-list summary{font-weight:600}.exclusions>summary{padding:12px 0}

.browser-tickets{margin:20px 0;padding:18px;border:2px solid #365b43;border-radius:8px;background:#fff}h4{margin:0;font-size:19px}h5{font-size:16px;margin:0}p,li{line-height:1.7;font-size:14px;overflow-wrap:anywhere}label{display:flex;flex-direction:column;gap:8px;max-width:280px}button,select{font:inherit;padding:9px;border:1px solid #365b43;border-radius:4px;background:#edf5ef;color:#183d29}button{cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.actions{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.recommendations{display:grid;gap:14px}.recommendations>p{margin:0}article{border:1px solid #a5b7ab;border-radius:6px;padding:16px}summary{cursor:pointer}a{color:#145d3d}button:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #215bc5;outline-offset:2px}
</style>

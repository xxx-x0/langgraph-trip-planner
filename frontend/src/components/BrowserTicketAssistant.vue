<template>
  <section class="browser-tickets" aria-label="浏览器查票与AI筛选">
    <h4>查票后让 AI 帮你选</h4>
    <p>候选带回后，先按当前已保存的景点、餐饮、住宿衔接和缓冲排除冲突，再由 AI 筛选。采用后预览并确认保存。</p>
    <label>这次更看重<select v-model="priority" :disabled="busy"><option value="balanced">时间与价格兼顾</option><option value="price">列表参考价较低</option><option value="time">车程较短</option><option value="daytime">白天出发和到达</option></select></label>
    <div class="actions"><button :disabled="disabled||busy||!!queryError(query)||!link.prefilled" @click="start">{{waiting?'重新发起查票':'打开查票并自动带回'}}</button><button v-if="tickets.length" :disabled="busy||disabled" @click="rank">{{busy?'AI正在筛选…':'重新AI筛选'}}</button></div>
    <p v-if="status" role="status">{{status}}</p>
    <p v-if="updateAvailable" role="status">已连接浏览器助手 {{extensionVersion}}，当前提供 {{currentExtensionVersion}}。更新后会校验铁路查询起终点变化，并保留航班继续加载保护。</p>
    <details v-if="!connected||updateAvailable"><summary>{{updateAvailable?'更新浏览器查票助手':'首次使用：连接浏览器查票助手'}}</summary><p>在 Chrome 或 Edge 安装本机“旅行规划查票助手”，并在同一个浏览器打开本应用。安装后刷新此页。扩展只为本次发起的查询读取票务列表，候选字段交给当前配置的 AI 筛选。</p><p>安装包：<a href="/ticket-assistant-extension.zip" download>下载浏览器助手</a>。解压后，在浏览器扩展管理页打开开发者模式，选择“加载已解压的扩展程序”，选中解压目录。更新已有扩展时，将文件解压到原目录，点击“重新加载”，再刷新规划页和查票页。安装包内附具体说明。</p></details>
    <p v-if="!link.prefilled">{{link.note}}</p>
    <div v-if="excluded.length && !recommendations.length && !busy" class="conflict-help" role="status"><strong>本次候选都放不进当前安排</strong><p v-if="scheduleContext?.kind==='multi'">先核对换城当天两座城市的活动和休息，再查票。修改每日安排后，还需同步回整趟旅行。</p><p v-else>先核对抵达日或离开日的活动、用餐和接驳时间，也可以预览具体班次的冲突，再决定调整当天安排或换一班。</p><slot name="conflict-actions" /><p v-if="scheduleContext?.kind==='multi'">也可以先选班次，生成两侧当天的调整建议。取消的景点、用餐和休息会单独列出，确认前不改变行程。</p></div>
    <details v-if="excluded.length" class="exclusions"><summary>已排除 {{excluded.length}} 条与当前安排冲突的候选</summary><p>逐班展开查看原因；已保存的活动不会自动删除。</p><div class="exclusion-list"><details v-for="e in excluded" :key="e.candidate.id"><summary>{{e.candidate.service}} · {{e.candidate.departure.replace('T',' ')}} — {{e.candidate.arrival?.slice(11,16)}}<small>{{e.conflicts[0]}}</small></summary><ul><li v-for="reason in e.conflicts" :key="reason">{{reason}}</li></ul><button v-if="scheduleContext?.kind==='multi' && e.leg" :disabled="disabled||busy||waiting" @click="emit('adjust',{leg:e.leg,ticketBasis})">按此班次调整两侧当天安排</button><button v-else-if="scheduleContext?.kind==='draft' && e.leg" :disabled="disabled||busy||waiting" @click="adopt(e.leg)">预览此班次与当天冲突</button></details></div></details>
    <div v-if="recommendations.length" class="recommendations">
      <p>{{rankedBy==='ai'?'AI推荐':'规则排序'}} · 本次带回 {{tickets.length}} 条，展示 {{recommendations.length}} 个候选；每批最多80条，不代表完整列表。网站加载更多结果后，可点击网站右下角“重新带回当前列表”。</p>
      <article v-for="(r,index) in recommendations" :key="r.candidate.id">
        <h5>{{index+1}}. {{r.candidate.service}} · {{r.candidate.seat||'席别待确认'}}</h5>
        <p>{{r.candidate.from_station}} → {{r.candidate.to_station}}<br />{{r.candidate.departure.replace('T',' ')}} — {{r.candidate.arrival.replace('T',' ')}}</p>
        <strong>{{r.candidate.fare_per_person===null?'列表参考价未知':'列表每人参考 ¥'+r.candidate.fare_per_person}}{{r.candidate.mode==='flight'?' 起':''}}</strong>
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
import type {TicketScheduleContext} from '@/utils/ticketSchedule'
const props=defineProps<{query:TicketQuery;disabled?:boolean;contextKey:string;scheduleContext?:TicketScheduleContext}>()
const emit=defineEmits<{(e:'adjust',value:{leg:JourneyLeg;ticketBasis?:string}):void;(e:'adopt',value:{leg:JourneyLeg;direction:'outbound'|'inbound';ticketBasis?:string}):void}>()
const priority=ref('balanced'),connected=ref(false),waiting=ref(false),busy=ref(false),status=ref(''),tickets=ref<any[]>([]),recommendations=ref<any[]>([]),rankedBy=ref('')
const currentExtensionVersion='0.2.2',extensionVersion=ref('')
const updateAvailable=computed(()=>{if(!extensionVersion.value)return false;const installed=extensionVersion.value.split('.').map(Number),latest=currentExtensionVersion.split('.').map(Number);for(let i=0;i<3;i++){if(installed[i]!==latest[i])return installed[i]!<latest[i]!}return false})
const link=computed(()=>searchLink(props.query))
const excluded=ref<any[]>([]),ticketBasis=ref('')
let requestId='',generation=0,controller:AbortController|undefined,connectionTimer:ReturnType<typeof setTimeout>|undefined,waitTimer:ReturnType<typeof setTimeout>|undefined,expiryTimer:ReturnType<typeof setTimeout>|undefined
function post(type:string,extra:Record<string,unknown>={}){window.postMessage({channel:'ltp-ticket-app-v1',type,requestId,...extra},window.location.origin)}
function invalidate(){if(requestId)post('ltp-cancel');requestId='';generation++;controller?.abort();clearTimeout(connectionTimer);clearTimeout(waitTimer);clearTimeout(expiryTimer);waiting.value=false;busy.value=false;tickets.value=[];recommendations.value=[];excluded.value=[];ticketBasis.value='';status.value=''}
watch([()=>JSON.stringify(props.query),()=>props.contextKey,()=>JSON.stringify(props.scheduleContext)],invalidate)
watch(priority,()=>{generation++;controller?.abort();busy.value=false;recommendations.value=[];excluded.value=[];ticketBasis.value='';if(tickets.value.length)status.value='偏好已改变，点击重新AI筛选。'})
function start(){
  if(props.disabled||busy.value||queryError(props.query)||!link.value.prefilled)return
  invalidate();requestId=crypto.randomUUID();waiting.value=true;status.value='正在连接浏览器助手…'
  post('ltp-start',{url:link.value.url,query:{...props.query}})
  expiryTimer=setTimeout(()=>{invalidate();status.value='本次查票连接已过期，请重新查询以获取更新列表。'},15*60*1000)
  connectionTimer=setTimeout(()=>{if(waiting.value&&!connected.value){waiting.value=false;status.value=['5173','4173','15173'].includes(window.location.port)?'未连接到浏览器助手。请先安装并刷新此页，或继续使用下方网站跳转与文字导入。':'未连接到浏览器助手：当前地址不在浏览器助手支持范围内。请在 Chrome 或 Edge 使用本机 5173、4173 或 15173 端口的规划页；也可使用下方网站跳转与文字导入。'}},2200)
  waitTimer=setTimeout(()=>{if(waiting.value){waiting.value=false;status.value='尚未收到列表。请完成票务网站查询或验证，再点击网站右下角重新带回；也可重新发起。'}},90000)
}
async function rank(){
  if(props.disabled||!tickets.value.length)return
  const current=++generation;controller?.abort();controller=new AbortController();busy.value=true;recommendations.value=[];excluded.value=[];ticketBasis.value='';status.value='候选已带回，正在核对安排并筛选…'
  try{
    const result=await recommendTickets({query:{mode:props.query.mode,direction:props.query.direction,from_place:props.query.from,to_place:props.query.to,date:props.query.date,passengers:props.query.passengers,priority:priority.value},candidates:tickets.value,context:props.scheduleContext},controller.signal)
    if(current!==generation)return
    recommendations.value=result.recommendations;excluded.value=result.excluded||[];ticketBasis.value=result.schedule_basis||'';rankedBy.value=result.ranked_by;status.value=result.message
  }catch(e:any){if(current===generation){recommendations.value=[];ticketBasis.value='';status.value=e?.response?.status===409?'安排已改变，请重新读取草稿后查票；旧推荐未采用。':'本次筛选未完成，候选已保留，可重试；已保存行程未改变。'}}finally{if(current===generation)busy.value=false}
}
function receive(event:MessageEvent){
  if(event.source!==window||event.origin!==window.location.origin||event.data?.channel!=='ltp-ticket-extension-v1')return
  const m=event.data
  if(m.type==='ltp-ping-reply'&&typeof m.version==='string'&&/^\d+\.\d+\.\d+$/.test(m.version)){connected.value=true;extensionVersion.value=m.version;return}
  if(!requestId||m.requestId!==requestId)return
  if(m.error){generation++;controller?.abort();clearTimeout(connectionTimer);clearTimeout(waitTimer);waiting.value=false;busy.value=false;recommendations.value=[];excluded.value=[];ticketBasis.value='';status.value=m.error;return}
  if(m.type==='ltp-start-reply'&&m.started){connected.value=true;clearTimeout(connectionTimer);status.value='查票页已打开，列表载入后会自动带回。遇到网站验证请在查票页完成。'}
  if(m.type==='ltp-result'&&m.status==='empty'&&Array.isArray(m.candidates)&&m.candidates.length===0){generation++;controller?.abort();busy.value=false;waiting.value=false;clearTimeout(connectionTimer);clearTimeout(waitTimer);tickets.value=[];recommendations.value=[];excluded.value=[];ticketBasis.value='';status.value='票务网站当前没有返回可读取候选，请在查票页核对条件或登录后重试。已保存行程未改变。';return}
  if(m.type==='ltp-result'&&Array.isArray(m.candidates)&&m.candidates.length>0&&m.candidates.length<=80){connected.value=true;clearTimeout(connectionTimer);clearTimeout(waitTimer);waiting.value=false;tickets.value=m.candidates;void rank()}
}
function adopt(leg:JourneyLeg){if(props.disabled||busy.value||waiting.value)return;emit('adopt',{leg:JSON.parse(JSON.stringify(leg)),direction:props.query.direction,...(ticketBasis.value?{ticketBasis:ticketBasis.value}:{})})}
onMounted(()=>{window.addEventListener('message',receive);post('ltp-ping')})
onBeforeUnmount(()=>{invalidate();window.removeEventListener('message',receive)})
</script>
<style scoped>
.conflict-help{padding:14px;background:#fff4e3;border:1px solid #d4b984;border-radius:10px;margin:16px 0}.exclusion-list{max-height:420px;overflow:auto;border-top:1px solid #d8e1da}.exclusion-list>details{padding:12px 4px;border-bottom:1px solid #d8e1da}.exclusion-list small{display:block;line-height:1.6;color:#52655a;margin:6px 0}.exclusion-list summary{font-weight:600}.exclusions>summary{padding:12px 0}

.browser-tickets{margin:20px 0;padding:18px;border:2px solid #365b43;border-radius:8px;background:#fff}h4{margin:0;font-size:19px}h5{font-size:16px;margin:0}p,li{line-height:1.7;font-size:14px;overflow-wrap:anywhere}label{display:flex;flex-direction:column;gap:8px;max-width:280px}button,select{font:inherit;padding:9px;border:1px solid #365b43;border-radius:4px;background:#edf5ef;color:#183d29}button{cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.actions{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.recommendations{display:grid;gap:14px}.recommendations>p{margin:0}article{border:1px solid #a5b7ab;border-radius:6px;padding:16px}summary{cursor:pointer}a{color:#145d3d}button:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #215bc5;outline-offset:2px}
</style>

<template>
  <section class="background-search" aria-label="免扩展查票">
    <p>{{query.mode==='train'?'直接查询12306，无需安装浏览器扩展。按城市查询可能包含辖区车站；可展开查询条件，选择“仅该车站”缩小范围。':'在本机后台查询携程，无需安装浏览器扩展；需要登录或验证时可打开独立查询窗口。'}}</p>
    <div class="search-actions">
      <button :disabled="disabled||active||!!queryError(query)" @click="start">{{active?'正在查询…':'后台查询'+(query.mode==='train'?'火车票':'机票')}}</button>
      <button v-if="active||phase==='needs_action'" @click="stop()">停止本次查询</button>
      <button v-if="phase==='needs_action'&&!browserVisible" :disabled="disabled" @click="resume(true)">打开登录／验证窗口</button>
      <button v-if="phase==='needs_action'&&browserVisible" :disabled="disabled" @click="resume(false)">已完成处理，继续读取</button>
    </div>
    <p v-if="message" role="status">{{message}}</p>
    <p v-if="phase==='completed'&&count">本次带回 {{count}} 条{{sampled?'（经过采样，仅比较本批部分）':''}}。票价为查询参考，采用后仍需预览确认。</p>
    <p v-if="phase==='needs_action'">查询窗口运行在启动后端的这台电脑。请保留原日期和起终点；处理后回到这里继续读取。</p>
  </section>
</template>
<script setup lang="ts">
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {cancelTicketSearch,continueTicketSearch,getTicketSearch,startTicketSearch} from '@/services/api'
import {queryError,type TicketQuery} from '@/utils/ticketSearch'
const props=defineProps<{query:TicketQuery;disabled?:boolean;contextKey:string}>()
const emit=defineEmits<{(e:'reset'):void;(e:'candidates',value:any[]):void}>()
const phase=ref('idle'),message=ref(''),count=ref(0),sampled=ref(false),browserVisible=ref(false)
const active=computed(()=>phase.value==='searching')
let jobId='',generation=0,controller:AbortController|undefined,pollTimer:ReturnType<typeof setTimeout>|undefined,expiryTimer:ReturnType<typeof setTimeout>|undefined
function errorMessage(error:any,fallback:string){
  const detail=error?.response?.data?.detail
  if(typeof detail==='string')return detail
  if(Array.isArray(detail)){const messages=detail.map(item=>typeof item?.msg==='string'?item.msg.replace(/^Value error, /,''):'').filter(Boolean);if(messages.length)return messages.slice(0,3).join('；')}
  return fallback
}
function stop(showMessage=true){
  generation++;controller?.abort();clearTimeout(pollTimer);clearTimeout(expiryTimer)
  const old=jobId;jobId='';if(old)void cancelTicketSearch(old).catch(()=>{})
  phase.value='idle';count.value=0;sampled.value=false;browserVisible.value=false
  message.value=showMessage?'已停止本次查询，已保存行程未改变。':''
  emit('reset')
}
function accept(result:any,current:number){
  if(current!==generation)return
  phase.value=result.status;message.value=result.message||'';browserVisible.value=!!result.browser_visible
  if(result.status==='completed'){
    const values=Array.isArray(result.candidates)?result.candidates:[]
    count.value=values.length;sampled.value=!!result.sampled
    if(values.length)emit('candidates',values)
  }else if(result.status==='searching')pollTimer=setTimeout(()=>void poll(current),1000)
}
async function poll(current:number){
  try{const result=await getTicketSearch(jobId,controller?.signal);accept(result,current)}
  catch(e:any){if(current===generation){phase.value='failed';message.value=errorMessage(e,'查询连接中断，请重新查票；已保存行程未改变。');emit('reset')}}
}
async function start(){
  if(props.disabled||active.value||queryError(props.query))return
  stop(false);const current=generation;controller=new AbortController();phase.value='searching';message.value='正在发起查询…'
  try{
    const q=props.query
    const result=await startTicketSearch({mode:q.mode,direction:q.direction,from_place:q.from,to_place:q.to,date:q.date,passengers:q.passengers,adult_passengers:q.adultPassengers,from_scope:q.fromScope||'auto',to_scope:q.toScope||'auto'},controller.signal)
    if(current!==generation){if(result.search_id)void cancelTicketSearch(result.search_id).catch(()=>{});return}
    jobId=result.search_id
    expiryTimer=setTimeout(()=>{stop(false);message.value='本次查票已过期，请重新查询以获取更新列表。'},15*60*1000)
    accept(result,current)
  }catch(e:any){if(current===generation){phase.value='failed';message.value=errorMessage(e,'本次后台查询未完成，可重试或使用网站查询；已保存行程未改变。')}}
}
async function resume(showBrowser:boolean){
  if(!jobId||props.disabled||phase.value!=='needs_action')return
  const current=generation;phase.value='searching';message.value=showBrowser?'正在打开本机查询窗口…':'正在继续读取…'
  try{accept(await continueTicketSearch(jobId,showBrowser,controller?.signal),current)}
  catch(e:any){if(current===generation){phase.value='failed';message.value=errorMessage(e,'本次未能继续查询，请重新查票。');emit('reset')}}
}
watch([()=>JSON.stringify(props.query),()=>props.contextKey],()=>stop(false))
onBeforeUnmount(()=>stop(false))
defineExpose({stop})
</script>
<style scoped>
.background-search{margin:16px 0;padding:14px;background:#edf5ef;border:1px solid #a5b7ab;border-radius:8px;color:#183d29}.search-actions{display:flex;gap:10px;flex-wrap:wrap}p{font-size:14px;line-height:1.7;overflow-wrap:anywhere}button{font:inherit;padding:10px 14px;background:#fff;color:#183d29;border:1px solid #365b43;border-radius:6px;cursor:pointer}button:first-child{background:#365b43;color:#fff}button:disabled{opacity:.5;cursor:not-allowed}button:focus-visible{outline:3px solid #215bc5;outline-offset:2px}
</style>

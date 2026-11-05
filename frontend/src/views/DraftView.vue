<template>
  <div class="draft-page journey-draft">
    <header class="draft-hero"><p class="draft-eyebrow">把喜欢的地方，排进每一天</p>
      <div class="draft-hero-anchor" data-flip-id="loader-hero">
        <span class="draft-hero-city">{{ draft?.city || '行程' }}</span>
        <span class="draft-hero-days">{{ draft?.request?.travel_days || '' }} 日</span>
      </div>
      <div class="meta" v-if="draft">
        {{ draft.request.start_date }} 至 {{ draft.request.end_date }} ·
        {{ draft.request.travel_days }} 天
      </div>
      <p class="draft-intro">先看当天怎么逛，再调整景点、用餐和出发时间。每次修改成功后都会保存。</p>
    </header>

    <a-alert v-if="loadError" type="error" :message="loadError" show-icon>
      <template #action><a-button @click="loadDraft">重新加载</a-button></template>
    </a-alert>

    <main v-if="draft && draft.status !== 'finalized' && !loadError" class="draft-content">
      <section v-if="route.query?.multi" class="journey-change"><router-link :to="{path:`/multi-trip/${route.query?.multi}`,query:multiReturnQuery}">← 返回整趟旅行</router-link><p>这里编辑这座城市的工作副本；确认同步后，整趟预算和说明才一起更新。跨城班次请回整趟页面修改。</p><a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @click="syncMulti">将当前安排同步到整趟旅行</a-button><p role="status">{{multiMessage}}</p></section>
      <TripSetupSummary v-if="!route.query?.multi" :request="draft.request" compact />
      <details v-if="route.query?.multi" class="city-journey-context"><summary>本城抵离时间与交通约束</summary><JourneySummary :journey="draft.request.journey" :city="draft.city" :days="draft.days" /></details>
      <section v-else ref="travelEditor" class="transport-desk" aria-label="往返交通与日程衔接">
        <header v-if="!journeyPreview" class="transport-heading">
          <div><span class="transport-eyebrow">往返交通</span><h2>{{draft.request.journey?.origin_city||'出发地'}} <span aria-hidden="true">↔</span> {{draft.city}}</h2></div>
          <span class="transport-state">{{journeyBusy?'正在衔接':journeyDirty?'有待确认的调整':draft.request.journey?.outbound&&draft.request.journey?.inbound?'已选往返班次':'班次待完善'}}</span>
        </header>
        <div v-if="journeyError" class="transport-error" role="alert"><strong>这次调整还未保存</strong><p>{{journeyError}}</p></div>
        <JourneyAdjustmentPreview v-if="journeyPreview" :preview="journeyPreview" :journey="journeyEdit" :days="draft.days" :original-details="draft.days_detail" :acknowledged="acknowledgeTravelAdjustment" :disabled="journeyBusy||Object.keys(dayBusy).length>0" @acknowledge="acknowledgeTravelAdjustment=$event" @save="saveTravel" @cancel="cancelTravel" />
        <div v-else-if="journeyBusy" class="transport-progress" role="status" aria-live="polite"><span class="transport-spinner" aria-hidden="true"></span><h3>正在衔接这趟行程</h3><p>核对真实路线，安排景点与用餐的合适时段。</p><span>完成后会显示调整预览，由你确认保存。</span></div>
        <div v-else-if="transportMode==='overview'" class="transport-overview">
          <div class="transport-tickets"><JourneyLegCard :leg="journeyDirty?journeyEdit?.outbound:draft.request.journey?.outbound" label="去程" /><JourneyLegCard :leg="journeyDirty?journeyEdit?.inbound:draft.request.journey?.inbound" label="返程" /></div>
          <p v-if="journeyDirty" class="transport-edit-notice">班次或接驳已修改，预览后再更新可游玩时间。</p>
          <JourneyDayWindows v-else :days="boundaryDays" />
          <div v-if="assembledDays&&!journeyDirty" class="meal-recovery-prompt" aria-label="整体协调行程">
            <div><strong>让这趟旅行更从容</strong><p>{{missingMealCount?`还有 ${missingMealCount} 顿午晚餐待安排。`:''}}把景点、用餐和休息一起协调，留足返程余量。</p></div>
            <button class="desk-secondary" type="button" :disabled="transportDisabled" @click="previewAdjustment({refill_meals:true})">AI 统筹整趟行程 <span aria-hidden="true">↗</span></button>
          </div>
          <div v-if="hasWholeDayReservation" class="transport-reservation"><p>旧草稿曾为未定交通预留整天，可恢复为可调整的游玩日。</p><button type="button" :disabled="transportDisabled" @click="releaseWholeDayReservation">恢复首末日可安排时间，预览</button></div>
          <div class="desk-actions">
            <button v-if="journeyDirty" class="desk-primary" type="button" :disabled="transportDisabled" @click="previewAdjustment({assemble_pending:draft.days_detail.some((day:any)=>!day)})">重新预览调整 <span aria-hidden="true">→</span></button>
            <button v-else-if="draft.days_detail.some((day:any)=>!day)&&draft.request.journey" class="desk-primary" type="button" :disabled="transportDisabled" @click="previewAdjustment({assemble_pending:true})">智能衔接全部待安排日期 <span aria-hidden="true">→</span></button>
            <button :class="draft.days_detail.every((day:any)=>!!day)&&!journeyDirty?'desk-primary':'desk-secondary'" type="button" :disabled="transportDisabled" @click="transportMode='search'">{{draft.request.journey?.outbound&&draft.request.journey?.inbound?'换个班次':'AI 帮我选票'}}</button>
            <button class="desk-text" type="button" :disabled="transportDisabled" @click="transportMode='edit'">修改班次与接驳</button>
          </div>
          <details class="transport-facts"><summary>票价、接驳与票务条件 <span aria-hidden="true">＋</span></summary><JourneySummary :journey="draft.request.journey" :city="draft.city" :days="draft.days" /></details>
        </div>
        <div v-show="!journeyPreview&&!journeyBusy&&transportMode==='search'" class="transport-search">
          <button class="desk-back" type="button" @click="transportMode='overview'">← 返回交通概览</button>
          <JourneyComparison :draft-id="draftId" :request="draft.request" :days-detail="draft.days_detail" :disabled="transportDisabled" compact @choose="chooseTravel" @adjust="chooseTravelAdjusted" />
        </div>
        <div v-show="!journeyPreview&&!journeyBusy&&transportMode==='edit'" class="transport-editor">
          <button class="desk-back" type="button" @click="transportMode='overview'">← 返回交通概览</button>
          <JourneyEditor :destination-city="draft.city" v-model="journeyEdit" :start-date="draft.request.start_date" :end-date="draft.request.end_date" :passengers="draft.request.companions?.count||1" />
          <div class="desk-actions"><button class="desk-primary" type="button" :disabled="transportDisabled" @click="previewAdjustment({assemble_pending:draft.days_detail.some((day:any)=>!day)})">智能衔接日程并预览 <span aria-hidden="true">→</span></button><button v-if="journeyDirty" class="desk-text" type="button" :disabled="journeyBusy" @click="cancelTravel">取消本次交通变更</button></div>
          <details class="transport-advanced"><summary>仅检查时间影响</summary><p>沿用已有活动，检查班次和时间是否匹配。</p><label><input type="checkbox" v-model="synchronizeTravel" @change="journeyPreview=null" />同步可容纳的每日时间安排</label><button class="desk-secondary" type="button" :disabled="transportDisabled" @click="previewTravel">查看变更影响</button></details>
        </div>
      </section>
      <div v-show="!journeyPreview&&transportMode==='overview'" class="saved-itinerary">
      <section v-if="!route.query?.multi && draft.unassigned_attractions?.length" class="journey-change unassigned-attractions" aria-label="待安排景点">
        <h3>{{draft.unassigned_attractions.length}} 个景点待安排</h3><p>它们仍属于本次选择，未被删除。先选日期预览，或明确选择不再安排，再定稿。</p>
        <div v-for="item in draft.unassigned_attractions" :key="item.id"><strong>{{item.name}}</strong><p>{{item.reason}}</p><select v-model.number="unassignedDays[item.id]" :aria-label="item.name+'安排日期'"><option :value="undefined" disabled>选择安排日期</option><option v-for="(day,index) in draft.days" :key="index" :value="index" :disabled="day.travel_window?.unavailable">{{day.date}}{{day.travel_window?.unavailable?' · 交通日':''}}</option></select><a-button :disabled="journeyBusy || journeyDirty || !!journeyPreview || Object.keys(dayBusy).length>0 || unassignedDays[item.id]===undefined" @click="previewPending(item.id,false)">加入这天，预览</a-button><a-button :disabled="journeyBusy || journeyDirty || !!journeyPreview || Object.keys(dayBusy).length>0" @click="previewPending(item.id,true)">不再安排，预览</a-button></div>
      </section>
      <div class="days-heading"><div><p class="draft-eyebrow">DAY BY DAY</p><h2>每天的安排</h2></div><span>{{draft.days.length}} 天 · 点击日期快速定位</span></div>
      <nav class="day-navigation" aria-label="每日行程导航"><a v-for="(ctx,idx) in draft.days" :key="idx" :href="`#draft-day-${idx}`"><strong>第 {{Number(idx)+1}} 天</strong><span>{{ctx.date.slice(5)}}</span><small>{{draft.days_detail[idx]?.is_assembled?'已安排':'待安排'}}</small></a></nav>
      <div class="days-container">
        <DayCard
          v-for="(ctx, idx) in draft.days"
          :key="idx"
          :id="`draft-day-${idx}`"
          :context="ctx"
          :detail="draft.days_detail[idx] || null"
          :is-default-expanded="route.query.date ? ctx.date === route.query.date : idx === 0"
          :busy="dayBusy[idx] || ''"
          :save-error="dayErrors[idx] || ''"
          @assemble="onAssemble(idx, $event)"
          @recompute="onRecompute(idx, $event)"
          @refresh-dining="onRefreshDining(idx)"
          @ai-rearrange="onAIRearrange(idx, $event)"
          @rewrite-narrative="onRewriteNarrative(idx)"
        />
      </div>
      </div>

      <div v-if="route.query?.multi" class="finalize-bar multi-sync-bar">
        <div><p>{{ draft.city }} · {{ assembledDays }} / {{ draft.days.length }} 天已安排</p><small>每日修改已保存在本城；同步后才会更新整趟旅行。</small><p v-if="multiMessage" role="status">{{multiMessage}}</p></div>
        <a-button type="primary" size="large" :loading="journeyBusy" :disabled="Object.keys(dayBusy).length > 0" @click="syncMulti">同步并返回整趟旅行</a-button>
      </div>
      <div v-else-if="!journeyPreview&&!journeyBusy&&!journeyDirty&&transportMode==='overview'" class="finalize-bar"><p>每天都核对好了？<small>定稿后保存为只读行程。</small></p>
        <a-button type="primary" size="large" @click="onFinalize"
                  :disabled="!!loadError || journeyBusy || journeyDirty || !!journeyPreview || !!draft.unassigned_attractions?.length || Object.keys(dayBusy).length > 0">
          定稿并保存
        </a-button>
      </div>
    </main>

    <a-empty v-else-if="!loading && !loadError" description="草稿不存在或已过期" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, nextTick, watch } from 'vue'
import { multiApi } from '@/services/api'
import JourneyEditor from '@/components/JourneyEditor.vue'
import JourneySummary from '@/components/JourneySummary.vue'
import JourneyLegCard from '@/components/journey/JourneyLegCard.vue'
import JourneyDayWindows from '@/components/journey/JourneyDayWindows.vue'
import JourneyAdjustmentPreview from '@/components/journey/JourneyAdjustmentPreview.vue'
import TripSetupSummary from '@/components/TripSetupSummary.vue'
import JourneyComparison from '@/components/JourneyComparison.vue'
import type {Journey} from '@/types'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDraft, assembleDay, recomputeDay, aiRearrangeDay, changeJourney, adjustJourney,
  rewriteNarrative, refreshDiningOptions,
} from '@/services/api'
import DayCard from '@/components/draft/DayCard.vue'
import { useTripLoader } from '@/composables/useTripLoader'

const route = useRoute()
const router = useRouter()
const draftId = computed(() => route.params.id as string)

const multiMessage=ref('')
const multiReturnQuery=computed(()=>({city:String(route.query.stop||''),...(route.query.date && route.query.returnSection!=='transport'?{date:String(route.query.date)}:{}),...(route.query.returnSection==='transport'?{section:'transport',edge:String(route.query.edge||'0')}:{})}))
async function syncMulti(){
 journeyBusy.value=true;multiMessage.value=''
 try{const saved=await multiApi(`/${route.query?.multi}/cities/${route.query.stop}/import`,'post',{revision:Number(route.query.revision),basis:String(route.query.basis||''),draft_id:draftId.value});multiMessage.value='已同步，整趟预算与安排一起更新。';await router.push({path:`/multi-trip/${saved.id}`,query:multiReturnQuery.value})}catch(e:any){multiMessage.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'同步失败，整趟旅行保持原样；城市工作副本仍已保存。'}finally{journeyBusy.value=false}
}
const draft = ref<any>(null)
const assembledDays=computed(()=>draft.value?.days_detail?.filter((day:any)=>day?.is_assembled).length||0)
const missingMealCount=computed(()=>(draft.value?.days_detail||[]).reduce((count:number,day:any)=>count+(day?.is_assembled&&(day.attractions?.length||day.meals?.length||day.hotel)?['lunch','dinner'].filter(slot=>!(day.meals||[]).some((meal:any)=>meal.type===slot)).length:0),0))
const journeyEdit=ref<Journey|null>(null)
const journeyPreview=ref<any>(null)
const journeyDirty=computed(()=>JSON.stringify(journeyEdit.value)!==JSON.stringify(draft.value?.request?.journey ?? null))
const hasWholeDayReservation=computed(()=>{const j=draft.value?.request?.journey;return j?.planning&&((!j.outbound&&j.planning.arrival_policy==='travel_day')||(!j.inbound&&j.planning.departure_policy==='travel_day'))})
const journeyBusy=ref(false)
const journeyError=ref('')
const synchronizeTravel=ref(true)
const journeyTicketBasis=ref<string|undefined>()
const acknowledgeTravelAdjustment=ref(false)
const adjustmentActions=ref<any>({})
const unassignedDays=reactive<Record<string,number>>({})
const travelEditor=ref<HTMLElement|null>(null)
const transportMode=ref<'overview'|'search'|'edit'>('overview')
const transportDisabled=computed(()=>journeyBusy.value||Object.keys(dayBusy).length>0)
const boundaryDays=computed(()=>(draft.value?.days||[]).map((day:any,index:number)=>({date:day.date,window:day.travel_window,dayNumber:index+1,activityCount:draft.value.days_detail[index]?.attractions?.length})).filter((_:any,index:number)=>index===0||index===draft.value.days.length-1))
function cancelTravel(){journeyEdit.value=draft.value?.request?.journey?JSON.parse(JSON.stringify(draft.value.request.journey)):null;journeyPreview.value=null;journeyError.value='';journeyTicketBasis.value=undefined;transportMode.value='overview'}

async function chooseTravel(value:Journey,ticketBasis?:string){journeyEdit.value=JSON.parse(JSON.stringify(value));await nextTick();journeyTicketBasis.value=ticketBasis;await previewAdjustment();await nextTick();travelEditor.value?.scrollIntoView?.({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})}
async function releaseWholeDayReservation(){const j=draft.value?.request?.journey;if(!j?.planning)return;journeyEdit.value=JSON.parse(JSON.stringify(j));if(!j.outbound&&j.planning.arrival_policy==='travel_day')journeyEdit.value!.planning!.arrival_policy='unreserved';if(!j.inbound&&j.planning.departure_policy==='travel_day')journeyEdit.value!.planning!.departure_policy='unreserved';journeyTicketBasis.value=undefined;await nextTick();await previewAdjustment()}
async function chooseTravelAdjusted(value:Journey,ticketBasis?:string){journeyEdit.value=JSON.parse(JSON.stringify(value));await nextTick();journeyTicketBasis.value=ticketBasis;await previewAdjustment()}
async function previewPending(id:string,discard:boolean){journeyEdit.value=draft.value.request.journey?JSON.parse(JSON.stringify(draft.value.request.journey)):null;await nextTick();await previewAdjustment(discard?{discard_ids:[id]}:{placements:[{id,day_index:unassignedDays[id]}]})}
async function previewAdjustment(actions:any={}){
 if(journeyBusy.value || Object.keys(dayBusy).length)return
 actions=actions.placements||actions.discard_ids?actions:{coordinate_trip:true,...actions}
 transportMode.value='overview';journeyBusy.value=true;journeyError.value='';journeyPreview.value=null;acknowledgeTravelAdjustment.value=false
 const requested=JSON.stringify(journeyEdit.value);adjustmentActions.value=JSON.parse(JSON.stringify(actions))
 try{const result=await adjustJourney(draftId.value,{journey:journeyEdit.value,ticket_basis:journeyTicketBasis.value,...actions});if(requested!==JSON.stringify(journeyEdit.value)){journeyError.value='生成期间交通输入已变化，旧预览未采用，请重新预览。';return}journeyPreview.value=result;await nextTick();travelEditor.value?.scrollIntoView?.({block:'start'})}catch(e:any){journeyError.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'调整未完成，已保存行程未改变，请重试'}finally{journeyBusy.value=false}
}

watch(()=>draft.value?.request?.journey, v=>{journeyEdit.value=v?JSON.parse(JSON.stringify(v)):null;journeyPreview.value=null;journeyTicketBasis.value=undefined},{immediate:true})
watch(journeyEdit,()=>{journeyPreview.value=null;acknowledgeTravelAdjustment.value=false},{deep:true})
async function previewTravel(){
 if(journeyBusy.value || Object.keys(dayBusy).length)return
 transportMode.value='overview';journeyBusy.value=true;journeyError.value='';journeyPreview.value=null
 try{journeyPreview.value=await changeJourney(draftId.value,journeyEdit.value,undefined,synchronizeTravel.value,journeyTicketBasis.value)}catch(e:any){journeyError.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'交通输入无效，请检查日期、人数、时区与价格来源'}finally{journeyBusy.value=false}
}
async function saveTravel(){
 if(!journeyPreview.value || journeyBusy.value || Object.keys(dayBusy).length)return
 journeyBusy.value=true;journeyError.value=''
 try{if(journeyPreview.value.adjustment_id){if(!acknowledgeTravelAdjustment.value)return;await adjustJourney(draftId.value,{journey:journeyEdit.value,ticket_basis:journeyTicketBasis.value,...adjustmentActions.value,adjustment_id:journeyPreview.value.adjustment_id,preview_token:journeyPreview.value.preview_token,acknowledge_adjustments:true})}else await changeJourney(draftId.value,journeyEdit.value,journeyPreview.value.preview_token,synchronizeTravel.value,journeyTicketBasis.value);draft.value=await getDraft(draftId.value);for(const key of Object.keys(dayErrors))if(draft.value.days_detail[Number(key)])delete dayErrors[Number(key)];journeyPreview.value=null;message.success('已保存这份安排，用餐、路线与费用已同步更新')}catch(e:any){journeyError.value=e?.response?.data?.detail || '交通修改未保存，请重新预览';journeyPreview.value=null}finally{journeyBusy.value=false}
}
const loading = ref(true)
const loadError = ref('')
const tripLoader = useTripLoader()

const dayBusy = reactive<Record<number, string>>({})
const dayErrors = reactive<Record<number, string>>({})

async function withDayBusy<T>(
  idx: number,
  label: string,
  fn: () => Promise<T>,
): Promise<T | undefined> {
  if (dayBusy[idx] || loadError.value || journeyBusy.value) return
  delete dayErrors[idx]
  dayBusy[idx] = label
  try {
    const result = await fn()
    if(result!==false)message.success(`已更新第 ${idx + 1} 天`)
    return result
  } catch (e: any) {
    if (e?.response?.status === 409) {
      try {
        draft.value = await getDraft(draftId.value)
        if (draft.value?.status === 'finalized' && draft.value.finalized_trip_id) {
          await router.replace(`/trip/${draft.value.finalized_trip_id}`)
        }
        dayErrors[idx] = `本次修改尚未保存，已加载最新保存内容，请核对后重试。${e?.response?.data?.detail || ''}`
      } catch {
        loadError.value = '最新草稿读取失败，请重新加载后再编辑。'
        dayErrors[idx] = '本次修改尚未保存，当前显示上次读取内容，请重新加载。'
      }
    } else {
      dayErrors[idx] = `本次修改尚未保存，已恢复上次成功保存状态。${e?.response?.data?.detail || `第 ${idx + 1} 天操作失败，请重试。`}`
    }
    message.error(dayErrors[idx])
  } finally {
    delete dayBusy[idx]
  }
}

async function loadDraft() {
  loading.value = true
  loadError.value = ''
  try {
    draft.value = await getDraft(draftId.value)
    if (draft.value?.status === 'finalized' && draft.value.finalized_trip_id) {
      tripLoader.dismiss()
      await router.replace(`/trip/${draft.value.finalized_trip_id}`)
      return
    }
    // 自动展开并装配第 1 天
    if (draft.value && !draft.value.days_detail[0]) {
      if(!route.query?.multi&&draft.value.request.journey){
        tripLoader.dismiss();await nextTick();await previewAdjustment({assemble_pending:true,refill_meals:true})
      }else await onAssemble(0, {})
    }
    // 草稿与第一天内容已就绪：若从 Discover 接力来的 loader 仍在，触发 Flip 收束
    if (tripLoader.state.phase !== 'idle') {
      await nextTick()
      tripLoader.markReady()
    }
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || '草稿读取失败，请重新加载；已保存草稿不会被覆盖。'
    tripLoader.dismiss() // 直接撤场，露出下方错误/空态
    message.error(e?.response?.data?.detail || '加载草稿失败')
  } finally {
    loading.value = false
  }
}

async function onAssemble(idx: number, body: any) {
  let needsJointPreview=false
  await withDayBusy(idx, '安排中', async () => {
    try{
      const resp = await assembleDay(draftId.value, idx, body)
      draft.value.days_detail.splice(idx, 1, resp.day_detail)
      if (resp.dining_pool) draft.value.days[idx].dining_pool = resp.dining_pool
    }catch(e:any){
      needsJointPreview=!route.query?.multi&&!draft.value.days_detail[idx]&&!!draft.value.request.journey&&
        e?.response?.status===409&&typeof e?.response?.data?.detail==='string'&&e.response.data.detail.startsWith('与交通或休息安排冲突')
      if(needsJointPreview){
        // This is an intermediate planning attempt, not a failed user edit.
        // Read the saved baseline before offering the whole-trip adjustment.
        try{draft.value=await getDraft(draftId.value)}catch(error){needsJointPreview=false;throw error}
        if(draft.value?.status==='finalized'&&draft.value.finalized_trip_id){needsJointPreview=false;await router.replace(`/trip/${draft.value.finalized_trip_id}`)}
        return false
      }
      throw e
    }
  })
  if(needsJointPreview&&!draft.value.days_detail[idx]&&!loadError.value&&!Object.keys(dayBusy).length){
    tripLoader.dismiss()
    journeyEdit.value=JSON.parse(JSON.stringify(draft.value.request.journey));journeyTicketBasis.value=undefined
    await nextTick();await previewAdjustment({assemble_pending:true})
  }
}

async function onRecompute(idx: number, body: any) {
  await withDayBusy(idx, '更新路线与时间', async () => {
    const resp = await recomputeDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
    if (resp.dining_pool) draft.value.days[idx].dining_pool = resp.dining_pool
  })
}

async function onAIRearrange(idx: number, hint: string) {
  await withDayBusy(idx, 'AI 重排中', async () => {
    const resp = await aiRearrangeDay(draftId.value, idx, hint)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
    if (resp.dining_pool) draft.value.days[idx].dining_pool = resp.dining_pool
  })
}

async function onRewriteNarrative(idx: number) {
  await withDayBusy(idx, '刷新说明中', async () => {
    const resp = await rewriteNarrative(draftId.value, idx)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
    if (resp.dining_pool) draft.value.days[idx].dining_pool = resp.dining_pool
  })
}

async function onRefreshDining(idx: number) {
  await withDayBusy(idx, '按当前安排找餐厅', async () => {
    const resp = await refreshDiningOptions(draftId.value, idx)
    draft.value.days[idx].dining_pool = resp.dining_pool
    message.info(resp.message)
  })
}

async function onFinalize() {
  if (Object.keys(dayBusy).length || loadError.value || journeyBusy.value || journeyDirty.value || journeyPreview.value) return
  // 前置拉起全局 Bauhaus 加载海报（REFINEMENT / 定稿打磨）
  const d = draft.value
  if (d) {
    tripLoader.begin('refinement', {
      city: d.city,
      days: d.request.travel_days,
      // 各天景点数之和，与 Poster A（selected.length）口径一致
      attractionCount: (d.days ?? []).reduce(
        (sum: number, day: any) => sum + (day.attractions?.length ?? 0),
        0,
      ),
      metaLine:
        d.request.start_date && d.request.end_date
          ? `${d.request.start_date} – ${d.request.end_date}`
          : undefined,
    })
  }
  router.push({
    path: '/result',
    query: { streaming: 'true', draft_id: draftId.value },
  })
}

onMounted(async()=>{await loadDraft();if(route.query.date){await nextTick();const idx=draft.value?.days.findIndex((d:any)=>d.date===route.query.date);if(idx>=0)document.getElementById(`draft-day-${idx}`)?.scrollIntoView?.({block:'start'})}})
</script>

<style scoped>
.draft-page {
  --draft-ink: var(--color-text-primary);
  --draft-muted: var(--color-text-secondary);
  --draft-line: var(--color-border-strong);
  --draft-surface: var(--color-bg-primary);
  max-width: 1120px;
  margin: 0 auto;
  padding: 36px 24px 80px;
  color: var(--draft-ink)
}
.draft-hero {
  padding: 10px 0 30px;
  border-bottom: 1px solid var(--draft-line);
  margin-bottom: 28px
}
.draft-eyebrow {
  font-size: 11px;
  letter-spacing: .12em;
  color: var(--draft-muted);
  margin: 0 0 12px
}
.draft-hero-anchor {
  display: inline-flex;
  align-items: baseline;
  gap: 14px
}
.draft-hero-city {
  font-size: 42px;
  font-weight: 800;
  letter-spacing: -.04em
}
.draft-hero-days {
  font-size: 16px;
  color: var(--draft-muted)
}
.meta {
  color: var(--draft-muted);
  margin-top: 12px;
  font-size: 13px
}
.draft-intro {
  color: var(--draft-muted);
  margin-top: 16px;
  font-size: 14px
}
.journey-change {
  padding: 20px;
  background: var(--draft-surface);
  color: var(--draft-ink);
  border: 1px solid var(--draft-line);
  border-radius: 12px;
  margin-bottom: 16px
}
.journey-change summary {
  cursor: pointer;
  font-weight: 600
}
.journey-change p {
  overflow-wrap: anywhere;
  line-height: 1.8
}
.unassigned-attractions>div {
  padding: 16px 0;
  border-top: 1px solid var(--draft-line)
}
.unassigned-attractions select {
  max-width: 100%;
  padding: 7px 10px;
  margin: 0 8px 8px 0;
  border: 1px solid var(--draft-line);
  border-radius: 8px;
  background: var(--draft-surface);
  color: var(--draft-ink)
}
.unassigned-attractions :deep(.ant-btn) {
  margin: 0 8px 8px 0
}
.days-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 32px 0 18px
}
.days-heading h2 {
  font-size: 25px;
  margin: 0;
  color: var(--draft-ink)
}
.days-heading>span {
  font-size: 12px;
  color: var(--draft-muted)
}
.day-navigation {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 4px 2px 16px;
  margin-bottom: 8px
}
.day-navigation a {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--draft-line);
  border-radius: 10px;
  padding: 12px 16px;
  color: var(--draft-ink);
  background: var(--draft-surface);
  white-space: nowrap;
  text-decoration: none
}
.day-navigation span,.day-navigation small {
  font-size: 12px;
  color: var(--draft-muted)
}
.day-navigation a:hover {
  border-color: var(--color-primary)
}
.day-navigation a:focus-visible {
  outline: 3px solid var(--color-primary);
  outline-offset: 2px
}
.days-container {
  display: flex;
  flex-direction: column;
  gap: 24px
}
.days-container>:deep(.ant-card) {
  scroll-margin-top: 88px;
  border: 1px solid var(--draft-line)!important;
  border-radius: 16px!important;
  box-shadow: none!important
}
.days-container :deep(.ant-card-head) {
  background: var(--color-bg-secondary)!important;
  border-bottom: 1px solid var(--draft-line)!important;
  border-radius: 16px 16px 0 0!important
}
.days-container :deep(.ant-card-head-title) {
  color: var(--draft-ink)!important
}
.days-container :deep(.editor-section),.days-container :deep(.route-info) {
  border: 1px solid var(--draft-line);
  border-radius: 12px;
  box-shadow: none
}
.days-container :deep(.editor-section .section-header),.days-container :deep(.route-info h4) {
  background: var(--color-bg-secondary);
  color: var(--draft-ink);
  border-bottom: 1px solid var(--draft-line)
}
.days-container :deep(.narrative) {
  border: 1px solid var(--draft-line);
  border-radius: 12px;
  box-shadow: none;
  background: var(--color-bg-secondary);
  color: var(--draft-ink)
}
.days-container :deep(.narrative::before) {
  display: none
}
.days-container :deep(.narrative small) {
  color: var(--draft-muted)
}
.days-container :deep(.schedule-details),.days-container :deep(.pending-confirmations) {
  border: 1px solid var(--draft-line);
  border-radius: 10px;
  background: var(--color-bg-secondary);
  color: var(--draft-ink)
}
.finalize-bar {
  position: sticky;
  bottom: 12px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  background: var(--draft-surface);
  padding: 16px 22px;
  border: 1px solid var(--draft-line);
  border-radius: 12px;
  margin-top: 24px;
  box-shadow: 0 4px 20px #00000012
}
.finalize-bar p {
  margin: 0;
  font-size: 14px
}
.finalize-bar small {
  display: block;
  color: var(--draft-muted);
  font-size: 12px;
  margin-top: 4px
}
@media(max-width:600px) {
  .draft-page {
    padding: 24px 14px 60px
  }
  .draft-hero-city {
    font-size: 34px
  }
  .days-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px
  }
  .day-navigation a {
    padding: 10px 12px;
    flex-direction: column;
    gap: 4px
  }
  .days-container :deep(.ant-card-head) {
    padding: 14px!important
  }
  .days-container :deep(.ant-card-head-wrapper) {
    flex-wrap: wrap;
    gap: 8px
  }
  .days-container :deep(.ant-card-body) {
    padding: 16px!important
  }
  .finalize-bar {
    padding: 14px;
    flex-wrap: wrap
  }
  .multi-sync-bar > div,.multi-sync-bar > button { width: 100%; }
  .journey-change {
    padding: 16px
  }
}

.draft-page :deep(.journey-summary),
.journey-change :deep(.comparison),
.journey-change :deep(.journey-editor) {
  background: var(--draft-surface);
  color: var(--draft-ink);
  border: 1px solid var(--draft-line);
  border-radius: 12px;
}
.draft-page :deep(.journey-summary h3) { color: var(--draft-ink); }
.days-container :deep(.ant-card) {
  background: var(--draft-surface) !important;
  color: var(--draft-ink) !important;
}
.days-container :deep(.editor-section),
.days-container :deep(.route-info),
.days-container :deep(.attr-row),
.days-container :deep(.meal-row),
.days-container :deep(.removed-row) {
  background: var(--draft-surface);
  color: var(--draft-ink);
  border: 1px solid var(--draft-line);
  border-radius: 10px;
  box-shadow: none;
}
.days-container :deep(.attr-row:hover),
.days-container :deep(.meal-row:hover) { transform: none; box-shadow: none; }
.days-container :deep(.attr-row::before),
.days-container :deep(.meal-row::before) { width: 3px; }
.days-container :deep(.drag-handle),
.days-container :deep(.drag-handle-static) { color: var(--draft-muted); }
.days-container :deep(.day-timeline) { border: 1px solid var(--draft-line); border-radius: 12px; box-shadow: none; background: var(--draft-surface); }
.days-container :deep(.timeline-header) { border-bottom: 1px solid var(--draft-line); }
.days-container :deep(.tl-card) { border: 1px solid var(--draft-line); border-left: 3px solid #739783; border-radius: 8px; background: var(--draft-surface); box-shadow: none; }
.days-container :deep(.tl-card.travel) { border: 0; border-left: 1px dashed var(--draft-line); border-radius: 0; }
.days-container :deep(.tl-name) { color: var(--draft-ink); }
.finalize-bar :deep(.ant-btn-primary) { background: #356c58!important; border: 1px solid #356c58!important; border-radius: 8px!important; box-shadow: none!important; color: #fff; height: auto; min-height: 44px; white-space: normal; letter-spacing: 0!important; font-weight: 600!important; }
.finalize-bar :deep(.ant-btn-primary:hover:not(:disabled)) { background: #285441!important; border-color: #285441!important; transform: none; }
.finalize-bar :deep(.ant-btn-primary:disabled) { opacity: .55; }
</style>

<style scoped>
.city-journey-context{margin:22px 0}.city-journey-context>summary{padding:18px 0;cursor:pointer;border-bottom:1px solid var(--draft-line);font-size:13px}.city-journey-context>summary span{font-size:11px;color:var(--draft-muted);margin-left:16px}.journey-draft{--draft-ink:var(--color-text-primary);--draft-muted:var(--color-text-secondary);--draft-line:var(--color-border);--draft-surface:var(--color-bg-primary);color-scheme:inherit}.journey-draft .draft-hero{border:0;padding-bottom:16px}.journey-draft .draft-hero-city{color:var(--color-text-primary)}.journey-draft .draft-eyebrow{color:var(--color-primary)}.journey-draft .journey-change{background:linear-gradient(120deg,#e8ba880d,#ffffff03);border-color:var(--draft-line);border-radius:16px}.journey-draft a{color:var(--color-primary)}.journey-draft .day-navigation{gap:10px;border:0}.journey-draft .day-navigation a{background:#ffffff04;border:1px solid var(--draft-line);border-radius:12px;color:var(--color-text-primary)}.journey-draft :deep(.ant-card){border:1px solid var(--draft-line);border-radius:20px;box-shadow:none!important}.journey-draft :deep(.ant-card-head){background:transparent;border-color:var(--draft-line);color:var(--color-text-primary)}.journey-draft :deep(.ant-card-head)::before,.journey-draft :deep(.ant-card-head)::after{display:none}.journey-draft :deep(.ant-btn){background:var(--color-bg-tertiary);border-color:var(--color-border-strong);color:var(--color-primary);border-radius:9px;box-shadow:none}.journey-draft :deep(.ant-btn-link){background:transparent;border:0}.journey-draft :deep(.ant-btn-dangerous){color:#efa39a}.journey-draft :deep(.ant-input){background:var(--desk-input);color:var(--color-text-primary);border-color:var(--draft-line);border-radius:9px}.journey-draft :deep(h4),.journey-draft :deep(.name),.journey-draft :deep(.meal-name){color:var(--color-text-primary)}.journey-draft :deep(.narrative){background:#ffffff03;border:1px solid var(--draft-line);border-radius:14px;color:var(--color-text-secondary)}.journey-draft :deep(.description-text){font-size:13px;line-height:1.9}.journey-draft :deep(.schedule-details){background:transparent;border:1px solid var(--draft-line);border-radius:12px;color:var(--color-text-secondary)}.journey-draft :deep(.pending-confirmations),.journey-draft :deep(.next-step){background:#e8ba8809;border-color:#e8ba8825;color:var(--color-warning);border-radius:12px}.journey-draft :deep(.editor-section){border-radius:14px}.journey-draft :deep(.meal-card){background:#ffffff03;color:var(--color-text-primary);border-color:var(--draft-line)}.journey-draft :deep(.meal-card p){color:var(--color-text-secondary)}.journey-draft .finalize-bar{background:#232629f2;border-color:var(--draft-line);border-radius:16px;backdrop-filter:blur(16px)}.journey-draft .finalize-bar :deep(.ant-btn-primary){background:var(--color-primary)!important;border-color:var(--color-primary)!important;color:var(--desk-on-accent)!important}

.journey-draft{--background:var(--color-bg-secondary);--white:var(--color-bg-primary);--foreground:var(--color-text-primary);--border:var(--color-border-strong);--primary-yellow:var(--color-primary);--primary-blue:#a7c4cb;--primary-red:#efa39a}
.journey-draft .days-container :deep(.ant-card-body){background:var(--color-bg-secondary);color:var(--color-text-primary)}
.journey-draft .days-container :deep(.ant-btn-link){color:var(--color-primary)!important;font-weight:500!important;letter-spacing:0!important}
.journey-draft .days-container :deep(.ant-btn-dangerous){color:#efa39a!important;border:1px solid #efa39a40!important;border-radius:9px!important;background:#efa39a0a!important;box-shadow:none!important}
.journey-draft .days-container :deep(input[type="time"]){border:1px solid var(--color-border-strong);border-radius:9px;box-shadow:none;background:var(--desk-bg);color:var(--color-text-primary)}

.journey-draft .draft-hero{margin-bottom:8px;padding-bottom:10px}.draft-intro{margin-bottom:0}
.transport-desk{padding:26px;border:1px solid var(--color-border);border-radius:22px;background:var(--color-bg-primary);margin:8px 0 32px;scroll-margin-top:88px;color:var(--color-text-primary)}
.meal-recovery-prompt{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-top:18px;padding:18px;border-radius:12px;background:color-mix(in srgb,var(--color-primary) 5%,var(--color-bg-primary));border:1px solid var(--color-border)}.meal-recovery-prompt strong{font-size:13px;font-weight:500}.meal-recovery-prompt p{font-size:12px;line-height:1.6;margin:5px 0 0;color:var(--color-text-secondary)}.meal-recovery-prompt button{flex-shrink:0}.meal-recovery-prompt button span{margin-left:8px}@media(max-width:650px){.meal-recovery-prompt{align-items:stretch;flex-direction:column;gap:12px;padding:14px}}
.transport-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:24px}.transport-eyebrow{font-size:11px;color:var(--color-text-secondary)}.transport-heading h2{font-size:23px;line-height:1.4;font-weight:500;letter-spacing:-.02em;margin:6px 0 0}.transport-heading h2>span{color:var(--color-text-secondary);font-size:18px;margin:0 12px}.transport-state{font-size:11px;padding:7px 10px;border-radius:20px;background:var(--color-bg-secondary);color:var(--color-text-secondary)}
.transport-tickets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:14px}.transport-desk :deep(.ticket-card){background:var(--color-bg-secondary)}.transport-desk :deep(.ticket-track i){background:var(--color-bg-secondary)}.transport-desk :deep(.window-card){background:var(--color-bg-primary)}
.transport-edit-notice{padding:12px 0;font-size:12px;color:var(--color-primary);margin:0}
.desk-actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:22px 0 0}.transport-desk .desk-primary,.transport-desk .desk-secondary,.transport-desk .desk-text,.transport-desk .desk-back,.transport-reservation button{font:inherit;font-size:13px;cursor:pointer;min-height:42px;border-radius:9px;padding:10px 16px;transition:background .16s,opacity .16s}.transport-desk .desk-primary{background:var(--color-primary);border:1px solid var(--color-primary);color:var(--desk-on-accent,#fff)}.desk-primary span{margin-left:12px}.transport-desk .desk-secondary{border:1px solid var(--color-border-strong);background:transparent;color:var(--color-text-primary)}.transport-desk .desk-text{border:0;background:none;color:var(--color-text-secondary);margin-left:auto;padding-right:0}.transport-desk .desk-back{padding:0;min-height:32px;margin-bottom:16px;border:0;background:none;color:var(--color-primary);font-size:12px}.transport-desk button:disabled{cursor:default;opacity:.45}.transport-desk button:focus-visible,.transport-desk summary:focus-visible{outline:2px solid var(--color-primary);outline-offset:4px}
.transport-facts{margin-top:22px;border-top:1px solid var(--color-border)}.transport-facts>summary{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:16px 0 0;font-size:11px;color:var(--color-text-secondary);cursor:pointer;list-style:none}.transport-facts>summary::-webkit-details-marker{display:none}.transport-facts[open]>summary{padding-bottom:16px}.transport-facts :deep(.journey-summary){border:0;padding:8px 0}.transport-facts :deep(.journey-heading){display:none}
.transport-progress{text-align:center;padding:40px 18px 44px;min-height:250px;display:flex;align-items:center;flex-direction:column;justify-content:center}.transport-spinner{width:32px;height:32px;border:2px solid var(--color-border);border-top-color:var(--color-primary);border-radius:50%;animation:transport-spin 1.2s linear infinite}.transport-progress h3{margin:20px 0 10px;font-size:21px;font-weight:500}.transport-progress p{font-size:13px;color:var(--color-text-secondary);margin:0 0 10px}.transport-progress>span:last-child{font-size:11px;color:var(--color-text-secondary)}.transport-error{padding:14px 16px;background:color-mix(in srgb,var(--color-warning) 6%,var(--color-bg-primary));border:1px solid color-mix(in srgb,var(--color-warning) 25%,var(--color-border));border-radius:12px;margin-bottom:20px;font-size:13px}.transport-error p{margin:5px 0 0;line-height:1.8;color:var(--color-text-secondary);overflow-wrap:anywhere}
.transport-advanced{margin-top:20px;border-top:1px solid var(--color-border);padding-top:16px;font-size:12px;color:var(--color-text-secondary)}.transport-advanced summary{cursor:pointer}.transport-advanced p{margin:14px 0}.transport-advanced label{display:flex;align-items:center;gap:8px;margin:12px 0}.transport-advanced input{accent-color:var(--color-primary)}.transport-advanced button{margin-top:4px}.transport-editor :deep(.journey-editor){border:0;border-radius:0;padding:0}.transport-reservation{padding:16px;border-radius:10px;margin-top:14px;background:var(--color-bg-secondary);font-size:12px}.transport-reservation p{margin:0 0 10px;color:var(--color-text-secondary)}.transport-reservation button{background:transparent;color:var(--color-primary);border:1px solid var(--color-border-strong)}
.transport-search :deep(.comparison){padding:0;border:0;background:transparent}.transport-search :deep(.comparison>h2),.transport-search :deep(.comparison>p:first-of-type){display:none}.transport-search :deep(.ticket-assistant){border:0;padding:0}.transport-search :deep(.ticket-assistant>h3){font-size:21px;font-weight:500;margin:4px 0 8px}.transport-search :deep(.ticket-assistant>p:first-of-type){font-size:12px;line-height:1.8}.transport-search :deep(.browser-tickets>h4),.transport-search :deep(.browser-tickets>p:first-of-type){display:none}.transport-search :deep(.browser-tickets){border:0;padding:0;margin-top:18px;background:none}
.transport-search :deep(.ticket-assistant){background:transparent;color:var(--color-text-primary);margin-bottom:0}
.transport-search :deep(p),.transport-search :deep(li){font-size:12px;line-height:1.8;color:var(--color-text-secondary)}
.transport-search :deep(label){font-size:12px;color:var(--color-text-secondary)}
.transport-search :deep(summary){font-size:12px;color:var(--color-text-secondary)}
.transport-search :deep(input),.transport-search :deep(select),.transport-search :deep(textarea){background:var(--color-bg-primary);border-color:var(--color-border-strong);color:var(--color-text-primary);border-radius:8px;min-height:40px}
.transport-search :deep(input[type=checkbox]){min-height:0;accent-color:var(--color-primary)}
.transport-search :deep(.ticket-assistant :where(button:not(.query-switch button))),.transport-search :deep(.ticket-actions a){background:var(--color-bg-primary);border:1px solid var(--color-border-strong);border-radius:8px;color:var(--color-text-primary);font-size:12px;min-height:40px;padding:10px 16px}
.transport-search :deep(.query-settings){background:var(--color-bg-secondary);border-color:var(--color-border);margin:12px 0 18px}
.transport-search :deep(.query-settings>summary){font-size:16px;color:var(--color-text-primary)}
.transport-search :deep(.query-settings[open]>summary){border-color:var(--color-border)}
.transport-search :deep(.query-settings small){color:var(--color-primary);font-size:11px}
.transport-search :deep(.background-search){background:transparent;border:0;border-radius:0;color:var(--color-text-primary);padding:0 0 22px;border-bottom:1px solid var(--color-border);margin:0 0 22px;display:flex;flex-direction:column;align-items:flex-start;gap:12px}
.transport-search :deep(.background-search>p){margin:0;max-width:700px}
.transport-search :deep(.background-search .search-actions){order:-1}
.transport-search :deep(.search-actions>button:first-child),.transport-search :deep(.recommendations article>button){background:var(--color-primary);border-color:var(--color-primary);color:var(--desk-on-accent,#fff)}
.transport-search :deep(.browser-tickets>label){display:inline-flex;vertical-align:top;min-width:220px;margin:0 16px 14px 0}
.transport-search :deep(.ticket-extra),.transport-search :deep(.extension-fallback){border-top:1px solid var(--color-border);padding-top:12px}
.transport-search :deep(.ticket-assistant>details:not(.query-settings)){border-top:1px solid var(--color-border)}
.transport-search :deep(.recommendations article){border-color:var(--color-border);border-radius:14px;background:var(--color-bg-secondary)}
.transport-search :deep(.conflict-help){background:color-mix(in srgb,var(--color-warning) 6%,var(--color-bg-primary));border-color:color-mix(in srgb,var(--color-warning) 25%,var(--color-border))}
.transport-search :deep(.exclusion-list),.transport-search :deep(.exclusion-list>details){border-color:var(--color-border)}
.transport-search :deep(a){color:var(--color-primary)}
.unassigned-attractions>div{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.unassigned-attractions>div>strong{font-size:14px;width:100%}.unassigned-attractions>div>p{width:100%;font-size:12px;margin:0 0 4px;color:var(--color-text-secondary)}
@keyframes transport-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.transport-spinner{animation:none;border-style:dotted}.transport-desk button{transition:none}}
@media(max-width:650px){.transport-desk{padding:18px 16px;border-radius:18px;scroll-margin-top:76px}.transport-heading{margin-bottom:20px}.transport-heading h2{font-size:21px}.transport-heading h2>span{margin:0 8px}.transport-state{font-size:10px}.transport-tickets{grid-template-columns:1fr;gap:12px}.desk-actions{gap:10px}.transport-desk .desk-primary,.transport-desk .desk-secondary{flex:1;text-align:center;font-size:12px}.transport-desk .desk-text{width:100%;margin:0;padding:4px 0;min-height:32px;text-align:center}.transport-progress{padding:30px 4px}.transport-advanced button{width:100%}}
</style>

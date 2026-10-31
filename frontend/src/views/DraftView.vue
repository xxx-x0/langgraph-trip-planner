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
      <TripSetupSummary v-if="!route.query?.multi" :request="draft.request" />
      <details class="city-journey-context" :open="!route.query?.multi"><summary>本城抵离时间与交通约束 <span>编辑前可展开核对</span></summary><JourneySummary :journey="draft.request.journey" :city="draft.city" :days="draft.days" /></details>
      <details v-if="!route.query?.multi" class="journey-change comparison-disclosure"><summary>查票与比较往返方案 <span>需要时展开</span></summary>
      <JourneyComparison :draft-id="draftId" :request="draft.request" :days-detail="draft.days_detail" :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @choose="chooseTravel" @adjust="chooseTravelAdjusted" />
      </details>
      <details ref="travelEditor" v-if="!route.query?.multi" class="journey-change" :open="travelEditorOpen" @toggle="travelEditorOpen=($event.target as HTMLDetailsElement).open">
        <summary>编辑往返交通，先查看对行程的影响</summary>
        <details :open="!journeyPreview"><summary>填写或修改班次、费用与接驳</summary>
          <JourneyEditor :destination-city="draft.city" v-model="journeyEdit" :start-date="draft.request.start_date" :end-date="draft.request.end_date" :passengers="draft.request.companions?.count || 1" />
        </details>
        <label><input type="checkbox" v-model="synchronizeTravel" @change="journeyPreview=null" />同步可容纳的每日时间安排</label>
        <a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @click="previewTravel">查看变更影响</a-button>
        <a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @click="previewAdjustment()">按交通重新安排并预览</a-button>
        <p v-if="journeyError" role="alert">{{ journeyError }}</p>
        <div v-if="journeyPreview" class="travel-preview">
          <div class="preview-tickets" aria-label="即将保存的去返程">
            <div v-for="(leg,label) in {去程:journeyEdit?.outbound,返程:journeyEdit?.inbound}" :key="label">
              <strong>{{ label }} · {{ leg?.service_number || '班次待定' }}</strong>
              <p v-if="leg">{{ leg.departure_station }} {{ leg.departure_time.replace('T',' ') }} → {{ leg.arrival_station }} {{ leg.arrival_time.replace('T',' ') }} · {{ leg.passengers }} 人</p>
              <p v-if="leg">全体 {{leg.passengers}} 人票价：{{leg.ticket_total == null ? '待核对（未计入预算）' : leg.ticket_total+' '+leg.currency}}；此金额不再乘人数。</p>
              <p v-else>时间与费用待定</p>
            </div>
          </div>
          <p>{{ journeyPreview.notice }}</p><p>往返大交通已知小计：{{ journeyPreview.intercity_total }} 元</p>
          <template v-if="journeyPreview.adjustment_id">
            <h4>本次移动、取消与待安排清单</h4><ul><li v-for="(change,index) in journeyPreview.changes" :key="index">{{change}}</li></ul>
            <p v-if="journeyPreview.unassigned_attractions?.length">仍有 {{journeyPreview.unassigned_attractions.length}} 个景点待安排；它们没有被删除，也未计入已完成安排。</p>
            <details v-for="(day,index) in journeyPreview.days_detail" :key="index"><summary>{{draft.days[index]?.date}} · {{day?'调整后时间轴':'当天待装配，路线及餐次尚未核对'}}</summary><ul v-if="day"><li v-for="(item,j) in day.timeline_schedule" :key="j">{{item.start_time}}—{{item.end_time}} {{item.ref_name}}</li></ul></details>
            <label><input type="checkbox" v-model="acknowledgeTravelAdjustment" />我已核对活动移动、时刻变化、用餐／休息取消及待安排清单，确认后保存</label>
          </template>
          <p v-if="journeyPreview.budget">整趟已知费用：{{journeyPreview.budget.total}} 元；{{journeyPreview.budget.is_within_budget === false ? '已超预算' : '仍有费用待核对'}}</p>
          <div v-for="day in journeyPreview.impacts" :key="day.date">
            <strong>{{ day.date }}</strong>
            <p>{{ day.window.notes.join('；') }}</p>
            <p>可用时段：{{ day.window.unavailable ? '全天在途／没有可用时间' : formatMinutes(day.window.start_minutes ?? 0)+'—'+formatMinutes(day.window.end_minutes ?? 1440) }}；住宿：{{ day.window.overnight_stay ? '计一晚' : '不计新增住宿' }}</p>
            <p v-if="day.changes?.length">{{day.changes.join('；')}}</p>
            <p v-if="day.changes?.some((change:string)=>change.includes('市内出发'))">保存后请核对当天用餐时间，延后出发也可能推迟午餐。</p>
            <p v-if="day.conflicts.length">需要调整：{{ day.conflicts.join('；') }}</p>
            <p v-if="day.window.unknown_cost_items?.length">费用待核对：{{ day.window.unknown_cost_items.join('；') }}</p>
          </div>
          <a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0 || (!!journeyPreview.adjustment_id && !acknowledgeTravelAdjustment)" @click="saveTravel">确认以上影响并保存交通</a-button>
        </div>
        <a-button v-if="journeyDirty || journeyPreview" :disabled="journeyBusy" @click="cancelTravel">取消本次交通变更</a-button>
      </details>
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

      <div v-if="route.query?.multi" class="finalize-bar multi-sync-bar">
        <div><p>{{ draft.city }} · {{ assembledDays }} / {{ draft.days.length }} 天已安排</p><small>每日修改已保存在本城；同步后才会更新整趟旅行。</small><p v-if="multiMessage" role="status">{{multiMessage}}</p></div>
        <a-button type="primary" size="large" :loading="journeyBusy" :disabled="Object.keys(dayBusy).length > 0" @click="syncMulti">同步并返回整趟旅行</a-button>
      </div>
      <div v-else class="finalize-bar"><p>每天都核对好了？<small>{{journeyDirty || journeyPreview ? '交通变更尚未确认，请先保存或取消本次变更。' : '定稿后保存为只读行程。'}}</small></p>
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
const journeyEdit=ref<Journey|null>(null)
const journeyPreview=ref<any>(null)
const journeyDirty=computed(()=>JSON.stringify(journeyEdit.value)!==JSON.stringify(draft.value?.request?.journey ?? null))
const journeyBusy=ref(false)
const journeyError=ref('')
const synchronizeTravel=ref(true)
const journeyTicketBasis=ref<string|undefined>()
const acknowledgeTravelAdjustment=ref(false)
const adjustmentActions=ref<any>({})
const unassignedDays=reactive<Record<string,number>>({})
const travelEditor=ref<HTMLDetailsElement|null>(null)
const travelEditorOpen=ref(false)
function cancelTravel(){journeyEdit.value=draft.value?.request?.journey?JSON.parse(JSON.stringify(draft.value.request.journey)):null;journeyPreview.value=null;journeyError.value='';journeyTicketBasis.value=undefined}

async function chooseTravel(value:Journey,ticketBasis?:string){journeyTicketBasis.value=ticketBasis;journeyEdit.value=JSON.parse(JSON.stringify(value));synchronizeTravel.value=true;await nextTick();await previewTravel();await nextTick();if(travelEditor.value){travelEditor.value.open=true;travelEditor.value.scrollIntoView?.({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})}}
async function chooseTravelAdjusted(value:Journey,ticketBasis?:string){journeyEdit.value=JSON.parse(JSON.stringify(value));await nextTick();journeyTicketBasis.value=ticketBasis;await previewAdjustment()}
async function previewPending(id:string,discard:boolean){journeyEdit.value=draft.value.request.journey?JSON.parse(JSON.stringify(draft.value.request.journey)):null;await nextTick();await previewAdjustment(discard?{discard_ids:[id]}:{placements:[{id,day_index:unassignedDays[id]}]})}
async function previewAdjustment(actions:any={}){
 if(journeyBusy.value || Object.keys(dayBusy).length)return
 travelEditorOpen.value=true;journeyBusy.value=true;journeyError.value='';journeyPreview.value=null;acknowledgeTravelAdjustment.value=false
 const requested=JSON.stringify(journeyEdit.value);adjustmentActions.value=JSON.parse(JSON.stringify(actions))
 try{const result=await adjustJourney(draftId.value,{journey:journeyEdit.value,ticket_basis:journeyTicketBasis.value,...actions});if(requested!==JSON.stringify(journeyEdit.value)){journeyError.value='生成期间交通输入已变化，旧预览未采用，请重新预览。';return}journeyPreview.value=result;await nextTick();travelEditor.value?.scrollIntoView?.({block:'start'})}catch(e:any){journeyError.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'调整未完成，已保存行程未改变，请重试'}finally{journeyBusy.value=false}
}

watch(()=>draft.value?.request?.journey, v=>{journeyEdit.value=v?JSON.parse(JSON.stringify(v)):null;journeyPreview.value=null;journeyTicketBasis.value=undefined},{immediate:true})
watch(journeyEdit,()=>{journeyPreview.value=null;acknowledgeTravelAdjustment.value=false},{deep:true})
function formatMinutes(n:number){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
async function previewTravel(){
 if(journeyBusy.value || Object.keys(dayBusy).length)return
 travelEditorOpen.value=true;journeyBusy.value=true;journeyError.value='';journeyPreview.value=null
 try{journeyPreview.value=await changeJourney(draftId.value,journeyEdit.value,undefined,synchronizeTravel.value,journeyTicketBasis.value)}catch(e:any){journeyError.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'交通输入无效，请检查日期、人数、时区与价格来源'}finally{journeyBusy.value=false}
}
async function saveTravel(){
 if(!journeyPreview.value || journeyBusy.value || Object.keys(dayBusy).length)return
 journeyBusy.value=true;journeyError.value=''
 try{if(journeyPreview.value.adjustment_id){if(!acknowledgeTravelAdjustment.value)return;await adjustJourney(draftId.value,{journey:journeyEdit.value,ticket_basis:journeyTicketBasis.value,...adjustmentActions.value,adjustment_id:journeyPreview.value.adjustment_id,preview_token:journeyPreview.value.preview_token,acknowledge_adjustments:true})}else await changeJourney(draftId.value,journeyEdit.value,journeyPreview.value.preview_token,synchronizeTravel.value,journeyTicketBasis.value);draft.value=await getDraft(draftId.value);journeyPreview.value=null;message.success('交通与可容纳的时间调整已保存，请核对当天安排')}catch(e:any){journeyError.value=e?.response?.data?.detail || '交通修改未保存，请重新预览';journeyPreview.value=null}finally{journeyBusy.value=false}
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
    message.success(`已更新第 ${idx + 1} 天`)
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
      await onAssemble(0, {})
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
  await withDayBusy(idx, '安排中', async () => {
    const resp = await assembleDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
    if (resp.dining_pool) draft.value.days[idx].dining_pool = resp.dining_pool
  })
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
.journey-change,.travel-preview {
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
.journey-change p,.travel-preview p {
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
.travel-preview label {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 16px 0;
  line-height: 1.7
}
.travel-preview input[type=checkbox] {
  flex-shrink: 0;
  margin-top: 5px
}
.comparison-disclosure>summary {
  display: flex;
  justify-content: space-between;
  gap: 12px
}
.comparison-disclosure>summary span {
  font-size: 12px;
  font-weight: 400;
  color: var(--draft-muted)
}
.comparison-disclosure[open]>summary {
  margin-bottom: 20px
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
.preview-tickets{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;padding:18px;background:var(--color-primary-bg);border:1px solid var(--color-border);border-radius:12px;margin:16px 0}.preview-tickets strong{font-weight:500}.preview-tickets p{font-size:12px;line-height:1.8;overflow-wrap:anywhere}
</style>

<style scoped>
.city-journey-context{margin:22px 0}.city-journey-context>summary{padding:18px 0;cursor:pointer;border-bottom:1px solid var(--draft-line);font-size:13px}.city-journey-context>summary span{font-size:11px;color:var(--draft-muted);margin-left:16px}.journey-draft{--draft-ink:var(--color-text-primary);--draft-muted:var(--color-text-secondary);--draft-line:var(--color-border);--draft-surface:var(--color-bg-primary);color-scheme:inherit}.journey-draft .draft-hero{border:0;padding-bottom:16px}.journey-draft .draft-hero-city{color:var(--color-text-primary)}.journey-draft .draft-eyebrow{color:var(--color-primary)}.journey-draft .journey-change{background:linear-gradient(120deg,#e8ba880d,#ffffff03);border-color:var(--draft-line);border-radius:16px}.journey-draft a{color:var(--color-primary)}.journey-draft .day-navigation{gap:10px;border:0}.journey-draft .day-navigation a{background:#ffffff04;border:1px solid var(--draft-line);border-radius:12px;color:var(--color-text-primary)}.journey-draft :deep(.ant-card){border:1px solid var(--draft-line);border-radius:20px;box-shadow:none!important}.journey-draft :deep(.ant-card-head){background:transparent;border-color:var(--draft-line);color:var(--color-text-primary)}.journey-draft :deep(.ant-card-head)::before,.journey-draft :deep(.ant-card-head)::after{display:none}.journey-draft :deep(.ant-btn){background:var(--color-bg-tertiary);border-color:var(--color-border-strong);color:var(--color-primary);border-radius:9px;box-shadow:none}.journey-draft :deep(.ant-btn-link){background:transparent;border:0}.journey-draft :deep(.ant-btn-dangerous){color:#efa39a}.journey-draft :deep(.ant-input){background:var(--desk-input);color:var(--color-text-primary);border-color:var(--draft-line);border-radius:9px}.journey-draft :deep(h4),.journey-draft :deep(.name),.journey-draft :deep(.meal-name){color:var(--color-text-primary)}.journey-draft :deep(.narrative){background:#ffffff03;border:1px solid var(--draft-line);border-radius:14px;color:var(--color-text-secondary)}.journey-draft :deep(.description-text){font-size:13px;line-height:1.9}.journey-draft :deep(.schedule-details){background:transparent;border:1px solid var(--draft-line);border-radius:12px;color:var(--color-text-secondary)}.journey-draft :deep(.pending-confirmations),.journey-draft :deep(.next-step){background:#e8ba8809;border-color:#e8ba8825;color:var(--color-warning);border-radius:12px}.journey-draft :deep(.editor-section){border-radius:14px}.journey-draft :deep(.meal-card){background:#ffffff03;color:var(--color-text-primary);border-color:var(--draft-line)}.journey-draft :deep(.meal-card p){color:var(--color-text-secondary)}.journey-draft .finalize-bar{background:#232629f2;border-color:var(--draft-line);border-radius:16px;backdrop-filter:blur(16px)}.journey-draft .finalize-bar :deep(.ant-btn-primary){background:var(--color-primary)!important;border-color:var(--color-primary)!important;color:var(--desk-on-accent)!important}

.journey-draft{--background:var(--color-bg-secondary);--white:var(--color-bg-primary);--foreground:var(--color-text-primary);--border:var(--color-border-strong);--primary-yellow:var(--color-primary);--primary-blue:#a7c4cb;--primary-red:#efa39a}
.journey-draft .days-container :deep(.ant-card-body){background:var(--color-bg-secondary);color:var(--color-text-primary)}
.journey-draft .days-container :deep(.ant-btn-link){color:var(--color-primary)!important;font-weight:500!important;letter-spacing:0!important}
.journey-draft .days-container :deep(.ant-btn-dangerous){color:#efa39a!important;border:1px solid #efa39a40!important;border-radius:9px!important;background:#efa39a0a!important;box-shadow:none!important}
.journey-draft .days-container :deep(input[type="time"]){border:1px solid var(--color-border-strong);border-radius:9px;box-shadow:none;background:var(--desk-bg);color:var(--color-text-primary)}
.preview-tickets{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;padding:18px;background:var(--color-primary-bg);border:1px solid var(--color-border);border-radius:12px;margin:16px 0}.preview-tickets strong{font-weight:500}.preview-tickets p{font-size:12px;line-height:1.8;overflow-wrap:anywhere}
</style>

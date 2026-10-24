<template>
  <div class="draft-page">
    <header class="draft-hero">
      <div class="draft-hero-anchor" data-flip-id="loader-hero">
        <span class="draft-hero-city">{{ draft?.city || '行程' }}</span>
        <span class="draft-hero-days">{{ draft?.request?.travel_days || '' }} 日</span>
      </div>
      <div class="meta" v-if="draft">
        {{ draft.request.start_date }} 至 {{ draft.request.end_date }} ·
        {{ draft.request.travel_days }} 天
      </div>
    </header>

    <a-alert v-if="loadError" type="error" show-icon :message="loadError">
      <template #action><a-button @click="loadDraft">重新加载</a-button></template>
    </a-alert>
    <main v-if="draft && draft.status !== 'finalized' && !loadError" class="draft-content">
      <section v-if="route.query?.multi" class="journey-change"><router-link :to="{path:`/multi-trip/${route.query?.multi}`,query:multiReturnQuery}">← 返回整趟旅行</router-link><p>这里编辑这座城市的工作副本；确认同步后，整趟预算和说明才一起更新。跨城班次请回整趟页面修改。</p><a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @click="syncMulti">将当前安排同步到整趟旅行</a-button><p role="status">{{multiMessage}}</p></section>
      <JourneySummary :journey="draft.request.journey" :city="draft.city" :days="draft.days" />
      <details v-if="!route.query?.multi" class="journey-change comparison-disclosure"><summary>查票与比较往返方案</summary>
        <JourneyComparison :draft-id="draftId" :request="draft.request" :days-detail="draft.days_detail" :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @choose="chooseTravel" />
      </details>
      <details v-if="!route.query?.multi" ref="travelEditor" class="journey-change" :open="travelEditorOpen" @toggle="travelEditorOpen=($event.target as HTMLDetailsElement).open">
        <summary>编辑往返交通，先查看对行程的影响</summary>
        <JourneyEditor v-model="journeyEdit" :destination-city="draft.city" :start-date="draft.request.start_date" :end-date="draft.request.end_date" :passengers="draft.request.companions?.count || 1" />
        <label><input type="checkbox" v-model="synchronizeTravel" @change="journeyPreview=null" />同步可容纳的每日时间安排</label>
        <a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @click="previewTravel">查看变更影响</a-button>
        <p v-if="journeyError" role="alert">{{ journeyError }}</p>
        <div v-if="journeyPreview" class="travel-preview">
          <p v-if="journeyPreview.budget">整趟已知费用：{{journeyPreview.budget.total}} 元；{{journeyPreview.budget.is_within_budget === false ? '已超预算' : '仍有费用待核对'}}</p>
          <p>{{ journeyPreview.notice }}</p><p>往返大交通已知小计：{{ journeyPreview.intercity_total }} 元</p>
          <div v-for="day in journeyPreview.impacts" :key="day.date"><p>{{ day.date }} · {{ day.window.unavailable ? '暂无可用时间' : timeLabel(day.window.start_minutes)+'—'+timeLabel(day.window.end_minutes) }}</p><p v-if="day.changes?.length">{{day.changes.join('；')}}</p><p v-for="problem in day.conflicts" :key="problem" role="alert">{{ problem }}</p></div>
          <a-button :disabled="journeyBusy || Object.keys(dayBusy).length > 0" @click="saveTravel">确认以上影响并保存交通</a-button>
        </div>
        <a-button v-if="journeyDirty || journeyPreview" :disabled="journeyBusy" @click="cancelTravel">取消本次交通变更</a-button>
      </details>
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
      <div v-else class="finalize-bar">
        <a-button type="primary" size="large" @click="onFinalize"
                  :disabled="!!loadError || journeyBusy || journeyDirty || !!journeyPreview || Object.keys(dayBusy).length > 0">
          定稿并保存
        </a-button>
      </div>
    </main>

    <a-empty v-else-if="!loadError && draft?.status !== 'finalized'" description="草稿不存在或已过期" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDraft, assembleDay, recomputeDay, aiRearrangeDay, changeJourney,
  rewriteNarrative, refreshDiningOptions,
} from '@/services/api'
import {multiApi} from '@/services/api'
import JourneyComparison from '@/components/JourneyComparison.vue'
import JourneyEditor from '@/components/JourneyEditor.vue'
import JourneySummary from '@/components/JourneySummary.vue'
import type {Journey} from '@/types'
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
const loading = ref(true)
const loadError = ref('')
const tripLoader = useTripLoader()

const dayBusy = reactive<Record<number, string>>({})
const dayErrors = reactive<Record<number, string>>({})

const journeyEdit=ref<Journey|null>(null)
const journeyPreview=ref<any>(null)
const journeyBusy=ref(false)
const journeyError=ref('')
const synchronizeTravel=ref(true)
const journeyTicketBasis=ref<string|undefined>()
const travelEditor=ref<HTMLDetailsElement|null>(null)
const travelEditorOpen=ref(false)
async function chooseTravel(value:Journey,ticketBasis?:string){
 journeyTicketBasis.value=ticketBasis;
 journeyEdit.value=JSON.parse(JSON.stringify(value));synchronizeTravel.value=true;await nextTick();await previewTravel();await nextTick();
 if(travelEditor.value){travelEditor.value.open=true;travelEditor.value.scrollIntoView?.({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})}
}
const journeyDirty=computed(()=>JSON.stringify(journeyEdit.value)!==JSON.stringify(draft.value?.request?.journey ?? null))
watch(()=>draft.value?.request?.journey,v=>{journeyEdit.value=v?JSON.parse(JSON.stringify(v)):null;journeyPreview.value=null;journeyTicketBasis.value=undefined},{immediate:true})
watch(journeyEdit,()=>{journeyPreview.value=null},{deep:true})
function timeLabel(n:number){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
function cancelTravel(){journeyEdit.value=draft.value?.request?.journey?JSON.parse(JSON.stringify(draft.value.request.journey)):null;journeyPreview.value=null;journeyError.value='';journeyTicketBasis.value=undefined}
async function previewTravel(){
 if(journeyBusy.value || Object.keys(dayBusy).length)return
 journeyBusy.value=true;journeyError.value='';journeyPreview.value=null
 try{journeyPreview.value=await changeJourney(draftId.value,journeyEdit.value,undefined,synchronizeTravel.value,journeyTicketBasis.value)}catch(e:any){journeyError.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'交通输入无效，请检查日期、人数、时区与价格来源'}finally{journeyBusy.value=false}
}
async function saveTravel(){
 if(!journeyPreview.value || journeyBusy.value || Object.keys(dayBusy).length)return
 journeyBusy.value=true;journeyError.value=''
 try{await changeJourney(draftId.value,journeyEdit.value,journeyPreview.value.preview_token,synchronizeTravel.value,journeyTicketBasis.value);draft.value=await getDraft(draftId.value);journeyPreview.value=null;message.success('交通已保存，请核对当天安排')}catch(e:any){journeyError.value=e?.response?.data?.detail || '交通修改未保存，请重新预览';journeyPreview.value=null}finally{journeyBusy.value=false}
}

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
  await withDayBusy(idx, '装配中', async () => {
    const resp = await assembleDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
    if (resp.dining_pool) draft.value.days[idx].dining_pool = resp.dining_pool
  })
}

async function onRecompute(idx: number, body: any) {
  await withDayBusy(idx, '重算中', async () => {
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
.draft-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.draft-hero { margin-bottom: 24px; }
.draft-hero h1 { font-size: 32px; margin-bottom: 8px; }
.meta { color: #888; }
.days-container { display: flex; flex-direction: column; gap: 16px; }
.finalize-bar {
  position: sticky; bottom: 0; background: white;
  padding: 16px; border-top: 1px solid #eee; text-align: right;
}
.draft-hero-anchor {
  display: inline-flex;
  align-items: baseline;
  gap: 12px;
  background: var(--primary-red);
  color: #fff;
  padding: 16px 24px;
  border: 3px solid var(--foreground);
  box-shadow: 6px 6px 0 var(--foreground);
}
.draft-hero-city { font-size: 32px; font-weight: 900; line-height: 1; letter-spacing: -0.02em; }
.draft-hero-days { font-size: 16px; font-weight: 700; letter-spacing: 0.1em; opacity: 0.9; }
</style>

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
      <div class="days-container">
        <DayCard
          v-for="(ctx, idx) in draft.days"
          :key="idx"
          :context="ctx"
          :detail="draft.days_detail[idx] || null"
          :is-default-expanded="idx === 0"
          :busy="dayBusy[idx] || ''"
          :save-error="dayErrors[idx] || ''"
          @assemble="onAssemble(idx, $event)"
          @recompute="onRecompute(idx, $event)"
          @ai-rearrange="onAIRearrange(idx, $event)"
          @rewrite-narrative="onRewriteNarrative(idx)"
        />
      </div>

      <div class="finalize-bar">
        <a-button type="primary" size="large" @click="onFinalize"
                  :disabled="!!loadError || Object.keys(dayBusy).length > 0">
          定稿并保存
        </a-button>
      </div>
    </main>

    <a-empty v-else-if="!loadError && draft?.status !== 'finalized'" description="草稿不存在或已过期" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDraft, assembleDay, recomputeDay, aiRearrangeDay,
  rewriteNarrative,
} from '@/services/api'
import DayCard from '@/components/draft/DayCard.vue'
import { useTripLoader } from '@/composables/useTripLoader'

const route = useRoute()
const router = useRouter()
const draftId = computed(() => route.params.id as string)

const draft = ref<any>(null)
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
  if (dayBusy[idx] || loadError.value) return
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
  })
}

async function onRecompute(idx: number, body: any) {
  await withDayBusy(idx, '重算中', async () => {
    const resp = await recomputeDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}

async function onAIRearrange(idx: number, hint: string) {
  await withDayBusy(idx, 'AI 重排中', async () => {
    const resp = await aiRearrangeDay(draftId.value, idx, hint)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}

async function onRewriteNarrative(idx: number) {
  await withDayBusy(idx, '重写叙述中', async () => {
    const resp = await rewriteNarrative(draftId.value, idx)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  })
}

async function onFinalize() {
  if (Object.keys(dayBusy).length || loadError.value) return
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

onMounted(loadDraft)
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

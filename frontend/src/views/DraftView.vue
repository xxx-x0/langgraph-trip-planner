<template>
  <div class="draft-page">
    <header class="draft-hero">
      <h1>{{ draft?.city || '加载中...' }}</h1>
      <div class="meta" v-if="draft">
        {{ draft.request.start_date }} 至 {{ draft.request.end_date }} ·
        {{ draft.request.travel_days }} 天
      </div>
    </header>

    <a-spin v-if="loading" tip="加载草稿中..." />

    <main v-else-if="draft" class="draft-content">
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="itinerary" tab="行程">
          <div class="days-container">
            <DayCard
              v-for="(ctx, idx) in draft.days"
              :key="idx"
              :context="ctx"
              :detail="draft.days_detail[idx] || null"
              :is-default-expanded="idx === 0"
              @assemble="onAssemble(idx, $event)"
              @recompute="onRecompute(idx, $event)"
              @ai-rearrange="onAIRearrange(idx, $event)"
              @rewrite-narrative="onRewriteNarrative(idx)"
            />
          </div>
        </a-tab-pane>
        <a-tab-pane key="map" tab="地图">
          <div>地图占位（沿用 TabMap 组件，传 draft.days 即可）</div>
        </a-tab-pane>
        <a-tab-pane key="weather" tab="天气">
          <div>天气占位（沿用 TabWeather）</div>
        </a-tab-pane>
        <a-tab-pane key="budget" tab="预算">
          <div>预算占位：已展开 {{ assembledCount }} / {{ draft.days.length }} 天</div>
        </a-tab-pane>
      </a-tabs>

      <div class="finalize-bar">
        <a-button type="primary" size="large" :loading="finalizing"
                  @click="onFinalize">
          定稿并保存
        </a-button>
      </div>
    </main>

    <a-empty v-else description="草稿不存在或已过期" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDraft, assembleDay, recomputeDay, aiRearrangeDay,
  rewriteNarrative, finalizeDraftStream,
} from '@/services/api'
import DayCard from '@/components/draft/DayCard.vue'

const route = useRoute()
const router = useRouter()
const draftId = computed(() => route.params.id as string)

const draft = ref<any>(null)
const loading = ref(true)
const activeTab = ref('itinerary')
const finalizing = ref(false)

const assembledCount = computed(
  () => draft.value?.days_detail?.filter((d: any) => d?.is_assembled).length || 0
)

async function loadDraft() {
  loading.value = true
  try {
    draft.value = await getDraft(draftId.value)
    // 自动展开第 1 天
    if (draft.value && !draft.value.days_detail[0]) {
      await onAssemble(0, {})
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载草稿失败')
  } finally {
    loading.value = false
  }
}

async function onAssemble(idx: number, body: any) {
  try {
    const resp = await assembleDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '展开失败')
  }
}

async function onRecompute(idx: number, body: any) {
  try {
    const resp = await recomputeDay(draftId.value, idx, body)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '重算失败')
  }
}

async function onAIRearrange(idx: number, hint: string) {
  try {
    const resp = await aiRearrangeDay(draftId.value, idx, hint)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'AI 重新安排失败')
  }
}

async function onRewriteNarrative(idx: number) {
  try {
    const resp = await rewriteNarrative(draftId.value, idx)
    draft.value.days_detail.splice(idx, 1, resp.day_detail)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '重写叙述失败')
  }
}

async function onFinalize() {
  finalizing.value = true
  try {
    await finalizeDraftStream(draftId.value, (event) => {
      if (event.type === 'complete' && (event as any).trip_id) {
        message.success('定稿成功')
        router.replace(`/trip/${(event as any).trip_id}`)
      } else if (event.type === 'error') {
        message.error(event.message || '定稿失败')
      }
    })
  } finally {
    finalizing.value = false
  }
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
</style>

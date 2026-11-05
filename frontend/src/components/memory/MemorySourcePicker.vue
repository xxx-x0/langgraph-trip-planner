<template>
  <section class="memory-source-picker">
    <h2>从已保存行程补记</h2>
    <p class="memory-muted">计划只提供参考。请确认实际到访，回忆会独立保存。</p>
    <div class="memory-actions" role="search">
      <label class="memory-grow"
        >查找行程<input
          v-model="query"
          type="search"
          placeholder="城市或行程标题"
          @keydown.enter.prevent="search" /></label
      ><button
        class="memory-button"
        :disabled="loading"
        type="button"
        @click="search"
      >
        查找
      </button>
    </div>
    <p v-if="error" class="memory-error" role="alert">{{ error }}</p>
    <div v-if="!source" class="memory-source-list">
      <button
        v-for="item in items"
        :key="item.kind + item.id"
        class="memory-source-item"
        type="button"
        :disabled="loading"
        @click="choose(item.kind, item.id)"
      >
        <strong>{{ item.title }}</strong
        ><span
          >{{ item.cities.join(' · ') }} · {{ item.start }} —
          {{ item.end }}</span
        ><small>{{
          item.kind === 'multi' ? '多城只读版本' : '已保存行程'
        }}</small>
      </button>
      <p v-if="!loading && !items.length" class="memory-muted">
        没有找到已保存行程，也可以直接记录一次旅行。
      </p>
      <button
        v-if="items.length < total"
        class="memory-button"
        :disabled="loading"
        type="button"
        @click="loadMore"
      >
        继续加载
      </button>
    </div>
    <div v-else class="memory-source-confirm">
      <div class="memory-section-heading">
        <h3>{{ source.title }}</h3>
        <button class="memory-link" type="button" @click="source = null">
          换一个行程
        </button>
      </div>
      <fieldset>
        <legend>实际去过哪些城市？</legend>
        <label
          v-for="visit in source.visits"
          :key="visit.id"
          class="memory-check"
          ><input
            v-model="selectedIds"
            type="checkbox"
            :value="visit.id"
          /><span
            ><strong>{{ visit.city }}</strong
            ><small
              >计划日期 {{ visit.planned_start }} —
              {{ visit.planned_end }}</small
            ></span
          ></label
        >
      </fieldset>
      <label v-if="pastDates" class="memory-check"
        ><input v-model="sameDates" type="checkbox" /><span
          >所选城市的实际日期与计划一致</span
        ></label
      >
      <p v-else class="memory-muted">
        计划日期尚未发生或不完整，请在记录中填写真实日期，也可留空。
      </p>
      <button
        class="memory-button memory-primary"
        type="button"
        :disabled="!selectedIds.length"
        @click="confirm"
      >
        用已确认的 {{ selectedIds.length }} 次到访开始记录
      </button>
    </div>
    <p v-if="loading" role="status" class="memory-muted">正在读取已保存行程…</p>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { memoryApi } from '@/services/travelMemory'
import type {
  MemoryDate,
  MemorySource,
  MemorySourceRef,
  MemoryVisit,
  SourceSummary,
} from '@/types/travelMemory'
import { unknownDate } from '@/utils/travelMemory'
const props = defineProps<{ initialKind?: string; initialId?: string }>()
const emit = defineEmits<{
  select: [source: MemorySourceRef, visits: MemoryVisit[], when: MemoryDate]
}>()
const query = ref(''),
  items = ref<SourceSummary[]>([]),
  total = ref(0),
  source = ref<MemorySource | null>(null),
  selectedIds = ref<string[]>([]),
  sameDates = ref(false),
  loading = ref(false),
  error = ref('')
let generation = 0
const today = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date())
const pastDates = computed(() =>
  source.value?.visits
    .filter((v) => selectedIds.value.includes(v.id))
    .every(
      (v) => !!v.planned_start && !!v.planned_end && v.planned_end <= today,
    ),
)
async function search() {
  source.value = null
  items.value = []
  await loadMore()
}
async function loadMore() {
  const current = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await memoryApi.sources(query.value, items.value.length)
    if (current === generation) {
      items.value.push(...result.items)
      total.value = result.total
    }
  } catch (e) {
    if (current === generation) error.value = (e as Error).message
  } finally {
    if (current === generation) loading.value = false
  }
}
async function choose(kind: string, id: string) {
  const current = ++generation
  loading.value = true
  error.value = ''
  try {
    const value = await memoryApi.source(kind, id)
    if (current === generation) {
      source.value = value
      selectedIds.value = []
      sameDates.value = false
    }
  } catch (e) {
    if (current === generation) error.value = (e as Error).message
  } finally {
    if (current === generation) loading.value = false
  }
}
function confirm() {
  if (!source.value) return
  const selected = source.value.visits.filter((v) =>
    selectedIds.value.includes(v.id),
  )
  const useDates = sameDates.value && pastDates.value
  const visits: MemoryVisit[] = selected.map(
    ({ planned_start, planned_end, ...visit }) => ({
      ...visit,
      when: useDates
        ? { precision: 'day', start: planned_start, end: planned_end }
        : unknownDate(),
    }),
  )
  const dates = selected.flatMap((v) => [v.planned_start, v.planned_end]).sort()
  const { kind, id, title, basis } = source.value
  emit(
    'select',
    { kind, id, title, basis },
    visits,
    useDates
      ? { precision: 'day', start: dates[0], end: dates[dates.length - 1] }
      : unknownDate(),
  )
}
onMounted(() =>
  props.initialKind && props.initialId
    ? choose(props.initialKind, props.initialId)
    : search(),
)
onBeforeUnmount(() => {
  generation++
})
</script>

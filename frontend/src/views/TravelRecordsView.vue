<template>
  <main class="memory-page memory-library">
    <header class="memory-heading">
      <div>
        <p class="memory-eyebrow">MY TRAVEL MEMORIES</p>
        <h1>把旅行，留在生活里。</h1>
        <p class="memory-muted">去过的地方，和那些想再想起的瞬间。</p>
      </div>
      <div class="memory-actions">
        <router-link class="memory-button" to="/travel-records/new?from=plan"
          >从行程补记</router-link
        ><router-link
          class="memory-button memory-primary"
          to="/travel-records/new"
          >＋ 记录旅行</router-link
        >
      </div>
    </header>
    <p v-if="error" class="memory-error" role="alert">
      {{ error }}
      <button class="memory-link" type="button" @click="load">重试</button>
    </p>
    <details v-if="drafts.length" class="memory-local-drafts">
      <summary>继续本机未完成的记录（{{ drafts.length }}）</summary>
      <div class="memory-source-list">
        <router-link
          v-for="draft in drafts"
          :key="draft.key"
          :to="
            draft.serverId
              ? '/travel-records/' + draft.serverId + '/edit'
              : '/travel-records/new?draft=' + draft.id
          "
          class="memory-source-item"
          ><strong>{{
            draft.form.title ||
            draft.form.visits.map((v) => v.city).join(' · ') ||
            '未命名旅行'
          }}</strong
          ><span
            >{{
              draft.pending.length
                ? draft.pending.length + ' 张照片待上传 · '
                : ''
            }}{{ new Date(draft.updated).toLocaleString() }}</span
          ></router-link
        >
      </div>
    </details>
    <div class="memory-toolbar">
      <div class="memory-tabs" aria-label="回看方式">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          type="button"
          :aria-pressed="view === tab.value"
          @click="view = tab.value"
        >
          {{ tab.label
          }}{{
            tab.value === 'trash' ? '（' + deletedRecords.length + '）' : ''
          }}
        </button>
      </div>
      <div class="memory-actions">
        <label
          >年份<select v-model="year">
            <option value="">全部年份</option>
            <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
            <option value="unknown">日期未记</option>
          </select></label
        ><label
          >查找回忆<input
            v-model="query"
            type="search"
            placeholder="城市、标题或一句话"
        /></label>
      </div>
    </div>
    <p v-if="loading" class="memory-muted" role="status">正在翻开旅行记录…</p>
    <section v-if="view === 'globe'" class="memory-atlas">
      <MemoryGlobe :places="points" :selected-key="selectedCity" />
      <div class="memory-atlas-copy">
        <div class="memory-stats">
          <div>
            <strong>{{ points.length }}</strong
            ><span>座去过的城市</span>
          </div>
          <div>
            <strong>{{ filteredByDate.length }}</strong
            ><span>次旅行回忆</span>
          </div>
          <div>
            <strong>{{ photoCount }}</strong
            ><span>张照片</span>
          </div>
        </div>
        <p class="memory-eyebrow">从一座城市，打开一段回忆</p>
        <div class="memory-city-pills">
          <button
            type="button"
            :aria-pressed="selectedCity === null"
            @click="selectedCity = null"
          >
            全部</button
          ><button
            v-for="point in points"
            :key="point.key"
            type="button"
            :aria-pressed="selectedCity === point.key"
            @click="
              selectedCity = selectedCity === point.key ? null : point.key
            "
          >
            {{ point.city }} <small>{{ point.recordIds.length }} 次旅行</small>
          </button>
        </div>
        <div v-if="selectedPoint" class="memory-city-context">
          <h2>
            {{ selectedPoint.city }}，留下了 {{ selectedPoint.visits }} 次到访
          </h2>
          <p class="memory-muted">
            {{ selectedPoint.region }} · {{ selectedPoint.country
            }}{{
              selectedPoint.latitude === null
                ? ' · 位置待补，暂未在地球打点'
                : ''
            }}
          </p>
        </div>
        <div v-else class="memory-city-context">
          <h2>
            {{
              points.length
                ? '每一次重游，都有新的故事。'
                : '从一个到过的地方开始。'
            }}
          </h2>
          <p class="memory-muted">
            {{
              points.length
                ? '选择一座城市，看看不同时间留下的回忆。'
                : '日期不记得也没关系。先记下城市，再慢慢补照片和故事。'
            }}
          </p>
        </div>
        <p v-if="unlocated" class="memory-muted">
          {{ unlocated }} 座城市的位置待补，仍可从列表查看回忆。
        </p>
      </div>
    </section>
    <div class="memory-section-heading">
      <h2>
        {{
          view === 'trash'
            ? '旅行回收站'
            : selectedPoint
              ? selectedPoint.city + '的旅行回忆'
              : '我的旅行相册'
        }}
      </h2>
      <span class="memory-muted"
        >{{ shown.length }} 次旅行
        <button
          v-if="selectedCity"
          class="memory-link"
          type="button"
          @click="selectedCity = null"
        >
          清除城市筛选
        </button></span
      >
    </div>
    <p v-if="view === 'trash'" class="memory-muted">
      移入回收站的旅行暂不计入足迹，照片和文字仍保留在完整备份中。
    </p>
    <div v-if="!loading && !shown.length" class="memory-empty">
      <h3>
        {{
          records.length ? '没有符合条件的回忆' : '你的第一段回忆，从这里开始'
        }}
      </h3>
      <p>
        {{
          records.length
            ? '可以调整年份、城市或搜索条件。'
            : '一个城市、一张照片、一句话，都值得留下。'
        }}
      </p>
      <router-link
        v-if="!records.length"
        class="memory-button memory-primary"
        to="/travel-records/new"
        >记下一次旅行</router-link
      >
    </div>
    <div class="memory-album-grid">
      <article
        v-for="record in shown"
        :key="record.id"
        class="memory-album-card"
      >
        <router-link
          :to="'/travel-records/' + record.id"
          class="memory-album-cover"
          :aria-label="'打开' + record.document.title"
          ><img
            v-if="coverPhoto(record) && !brokenCovers.has(record.id)"
            :src="photoUrl(record.id, coverPhoto(record)!.id)"
            :alt="coverPhoto(record)!.caption || record.document.title"
            :style="{
              objectPosition:
                coverPhoto(record)!.focal_x +
                '% ' +
                coverPhoto(record)!.focal_y +
                '%',
            }"
            loading="lazy"
            @error="brokenCovers.add(record.id)"
          /><span v-else>{{
            coverPhoto(record) ? '照片暂未载入，仍可打开回忆' : '照片可以慢慢补'
          }}</span></router-link
        >
        <div class="memory-album-body">
          <p class="memory-eyebrow">
            {{ formatMemoryDate(record.document.when) }}
          </p>
          <h3>
            <router-link :to="'/travel-records/' + record.id">{{
              record.document.title
            }}</router-link>
          </h3>
          <p class="memory-card-note">
            {{ record.document.note || '先记住到过这里，故事以后再补。' }}
          </p>
          <p class="memory-muted">
            {{
              [...new Set(record.document.visits.map((v) => v.city))].join(
                ' · ',
              )
            }}
            ·
            {{ record.document.photos.filter((p) => !p.deleted).length }} 张照片
          </p>
          <button
            v-if="view === 'trash'"
            class="memory-button"
            type="button"
            :disabled="restoring === record.id"
            @click="restore(record)"
          >
            恢复这次旅行
          </button>
        </div>
      </article>
    </div>
    <MemoryBackup @restored="load" />
  </main>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MemoryGlobe from '@/components/memory/MemoryGlobe.vue'
import MemoryBackup from '@/components/memory/MemoryBackup.vue'
import { memoryApi, photoUrl } from '@/services/travelMemory'
import { memoryDrafts } from '@/services/memoryDrafts'
import {
  cityKey,
  coverPhoto,
  footprints,
  formatMemoryDate,
  recordMatchesYear,
} from '@/utils/travelMemory'
import type { MemoryDraft, TravelMemory } from '@/types/travelMemory'
import '@/styles/travel-memories.css'
const route = useRoute(),
  records = ref<TravelMemory[]>([]),
  drafts = ref<MemoryDraft[]>([]),
  loading = ref(false),
  error = ref(''),
  restoring = ref('')
const view = ref('globe'),
  year = ref(''),
  query = ref(''),
  selectedCity = ref<string | null>(null),
  brokenCovers = ref(new Set<string>())
const tabs = [
  { value: 'globe', label: '我的足迹' },
  { value: 'albums', label: '旅行相册' },
  { value: 'trash', label: '回收站' },
]
const activeRecords = computed(() =>
    records.value.filter((r) => !r.document.deleted),
  ),
  deletedRecords = computed(() =>
    records.value.filter((r) => r.document.deleted),
  )
const years = computed(() => {
  const set = new Set<string>()
  for (const r of records.value) {
    const d = r.document.when
    if (d.precision !== 'unknown')
      for (
        let y = Number(d.start.slice(0, 4));
        y <= Number((d.end || d.start).slice(0, 4));
        y++
      )
        set.add(String(y))
  }
  return [...set].sort().reverse()
})
const filteredByDate = computed(() =>
  (view.value === 'trash' ? deletedRecords.value : activeRecords.value)
    .filter((r) => recordMatchesYear(r, year.value))
    .filter(
      (r) =>
        !query.value.trim() ||
        [
          r.document.title,
          r.document.note,
          ...r.document.visits.map((v) => v.city),
          ...r.document.moments
            .filter((m) => !m.deleted)
            .map((m) => m.text + m.title + m.place),
        ]
          .join(' ')
          .toLocaleLowerCase()
          .includes(query.value.trim().toLocaleLowerCase()),
    ),
)
const points = computed(() => footprints(filteredByDate.value)),
  selectedPoint = computed(() =>
    points.value.find((p) => p.key === selectedCity.value),
  ),
  unlocated = computed(
    () => points.value.filter((p) => p.latitude === null).length,
  )
const shown = computed(() =>
  filteredByDate.value.filter(
    (r) =>
      !selectedCity.value ||
      r.document.visits.some((v) => cityKey(v) === selectedCity.value),
  ),
)
const photoCount = computed(() =>
  filteredByDate.value.reduce(
    (n, r) => n + r.document.photos.filter((p) => !p.deleted).length,
    0,
  ),
)
watch([view, year, query], () => {
  selectedCity.value = null
})
async function load() {
  loading.value = true
  error.value = ''
  brokenCovers.value.clear()
  const results = await Promise.allSettled([
    memoryApi.list(),
    memoryDrafts.list(),
  ])
  if (results[0].status === 'fulfilled') records.value = results[0].value
  else error.value = results[0].reason.message
  if (results[1].status === 'fulfilled')
    drafts.value = results[1].value.sort((a, b) => b.updated - a.updated)
  else error.value += ' 本机草稿暂时无法读取。'
  loading.value = false
}
async function restore(record: TravelMemory) {
  restoring.value = record.id
  try {
    await memoryApi.trash(record, false)
    await load()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    restoring.value = ''
  }
}
onMounted(() => {
  if (route.query.view === 'albums') view.value = 'albums'
  void load()
})
</script>

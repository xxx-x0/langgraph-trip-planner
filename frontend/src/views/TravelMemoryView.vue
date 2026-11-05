<template>
  <main class="memory-page memory-reading">
    <router-link class="memory-link" to="/travel-records"
      >← 旅行记录</router-link
    >
    <p v-if="error" class="memory-error" role="alert">
      {{ error }}
      <button class="memory-link" type="button" @click="load">重试</button>
    </p>
    <p v-if="loading" role="status">正在翻开回忆…</p>
    <template v-if="record">
      <div v-if="record.document.deleted" class="memory-notice">
        这次旅行在回收站中，暂不计入足迹。<button
          class="memory-button"
          type="button"
          :disabled="busy"
          @click="setTrash(false)"
        >
          恢复旅行
        </button>
      </div>
      <header class="memory-heading">
        <div>
          <p class="memory-eyebrow">
            {{ formatMemoryDate(record.document.when) }} ·
            {{
              [...new Set(record.document.visits.map((v) => v.city))].join(
                ' / ',
              )
            }}
          </p>
          <h1>{{ record.document.title }}</h1>
          <p class="memory-muted">
            {{ photos.length }} 张照片 · {{ moments.length }} 段回忆
          </p>
        </div>
        <div v-if="!record.document.deleted" class="memory-actions">
          <router-link
            class="memory-button memory-primary"
            :to="'/travel-records/' + record.id + '/edit'"
            >编辑回忆 / 添加照片</router-link
          ><a-popconfirm
            title="移入回收站？照片和文字会保留，稍后可以恢复。"
            ok-text="移入回收站"
            cancel-text="保留"
            @confirm="setTrash(true)"
            ><button class="memory-button" type="button" :disabled="busy">
              移入回收站
            </button></a-popconfirm
          >
        </div>
      </header>
      <div v-if="record.document.note" class="memory-opening-note">
        {{ record.document.note }}
      </div>
      <div class="memory-visit-strip">
        <article v-for="visit in record.document.visits" :key="visit.id">
          <strong>{{ visit.city }}</strong
          ><span>{{ visit.region }} · {{ visit.country }}</span
          ><small
            >{{ formatMemoryDate(visit.when)
            }}{{ visit.latitude === null ? ' · 地球位置待补' : '' }}</small
          >
        </article>
      </div>
      <section class="memory-photos-section">
        <div class="memory-section-heading">
          <h2>旅行相册</h2>
          <router-link
            v-if="!record.document.deleted"
            class="memory-link"
            :to="'/travel-records/' + record.id + '/edit#memory-photos'"
            >添加或整理照片</router-link
          >
        </div>
        <div v-if="!photos.length" class="memory-empty">
          <h3>照片可以慢慢补</h3>
          <p>先留下文字也很好。以后还能回来添加照片。</p>
        </div>
        <div class="memory-photo-grid">
          <figure v-for="(photo, index) in photos" :key="photo.id">
            <button
              type="button"
              :aria-label="'查看照片：' + (photo.caption || photo.filename)"
              @click="viewer = index"
            >
              <img
                v-if="!failed.has(photo.id)"
                :src="photoUrl(record.id, photo.id)"
                :alt="photo.caption || photo.filename"
                loading="lazy"
                @error="failed.add(photo.id)"
              /><span v-else class="memory-image-fallback"
                >照片暂未载入 · 点击查看原图</span
              >
            </button>
            <figcaption v-if="photo.caption">{{ photo.caption }}</figcaption>
          </figure>
        </div>
      </section>
      <section v-if="moments.length" class="memory-moments-reading">
        <h2>想留下的片段</h2>
        <article
          v-for="moment in moments"
          :key="moment.id"
          class="memory-story"
        >
          <p class="memory-eyebrow">
            {{
              moment.visit_id
                ? record.document.visits.find((v) => v.id === moment.visit_id)
                    ?.city
                : ''
            }}{{ moment.place ? ' · ' + moment.place : '' }} ·
            {{ formatMemoryDate(moment.when) }}
          </p>
          <h3 v-if="moment.title">{{ moment.title }}</h3>
          <p class="memory-prose">{{ moment.text }}</p>
          <div
            v-if="photos.some((p) => p.moment_id === moment.id)"
            class="memory-moment-photos"
          >
            <button
              v-for="photo in photos.filter((p) => p.moment_id === moment.id)"
              :key="photo.id"
              type="button"
              :aria-label="'查看关联照片：' + photo.filename"
              @click="viewer = photos.findIndex((p) => p.id === photo.id)"
            >
              <img
                :src="photoUrl(record.id, photo.id)"
                :alt="photo.caption || photo.filename"
                loading="lazy"
              />
            </button>
          </div>
        </article>
      </section>
      <footer class="memory-record-footer">
        <span>保存于 {{ new Date(record.updated_at).toLocaleString() }}</span
        ><router-link
          v-if="record.document.source && sourceState === 'available'"
          :to="
            record.document.source.kind === 'single'
              ? '/trip/' + record.document.source.id
              : '/multi-trip/' + record.document.source.id
          "
          >查看补记来源：{{ record.document.source.title }}</router-link
        >
        <span v-else-if="record.document.source"
          >补记来源：{{ record.document.source.title }} ·
          {{
            sourceState === 'missing'
              ? '原行程未在本机找到，回忆仍完整保留'
              : sourceState === 'checking'
                ? '正在核对原行程'
                : '暂时无法核对原行程'
          }}</span
        >
      </footer>
      <MemoryPhotoViewer
        v-if="viewer !== null"
        :record-id="record.id"
        :photos="photos"
        :index="viewer"
        @change="viewer = $event"
        @close="viewer = null"
      />
    </template>
  </main>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { memoryApi, MemoryApiError, photoUrl } from '@/services/travelMemory'
import { formatMemoryDate } from '@/utils/travelMemory'
import MemoryPhotoViewer from '@/components/memory/MemoryPhotoViewer.vue'
import type { TravelMemory } from '@/types/travelMemory'
import '@/styles/travel-memories.css'
const route = useRoute(),
  record = ref<TravelMemory | null>(null),
  loading = ref(false),
  error = ref(''),
  busy = ref(false),
  failed = ref(new Set<string>()),
  viewer = ref<number | null>(null)
const sourceState = ref<'checking' | 'available' | 'missing' | 'unknown'>(
  'checking',
)
let generation = 0
const photos = computed(
    () => record.value?.document.photos.filter((p) => !p.deleted) || [],
  ),
  moments = computed(
    () => record.value?.document.moments.filter((m) => !m.deleted) || [],
  )
async function load() {
  const current = ++generation
  loading.value = true
  error.value = ''
  record.value = null
  viewer.value = null
  failed.value.clear()
  sourceState.value = 'checking'
  try {
    const result = await memoryApi.get(String(route.params.id))
    if (current === generation) {
      record.value = result
      if (result.document.source)
        void checkSource(result.document.source, current)
    }
  } catch (e) {
    if (current === generation) error.value = (e as Error).message
  } finally {
    if (current === generation) loading.value = false
  }
}
async function checkSource(
  source: NonNullable<TravelMemory['document']['source']>,
  current: number,
) {
  try {
    await memoryApi.source(source.kind, source.id)
    if (current === generation) sourceState.value = 'available'
  } catch (error) {
    if (current === generation)
      sourceState.value =
        error instanceof MemoryApiError && [404, 409].includes(error.status)
          ? 'missing'
          : 'unknown'
  }
}
async function setTrash(deleted: boolean) {
  if (!record.value) return
  busy.value = true
  error.value = ''
  try {
    record.value = await memoryApi.trash(record.value, deleted)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
watch(() => route.params.id, load, { immediate: true })
onBeforeUnmount(() => {
  generation++
})
</script>

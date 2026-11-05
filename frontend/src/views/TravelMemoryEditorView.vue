<template>
  <main class="memory-page memory-editor">
    <router-link
      class="memory-link"
      :to="serverId ? '/travel-records/' + serverId : '/travel-records'"
      >← {{ serverId ? '返回这次回忆' : '旅行记录' }}</router-link
    >
    <header class="memory-heading">
      <div>
        <p class="memory-eyebrow">KEEP A LITTLE MEMORY</p>
        <h1>{{ serverId ? '让回忆更完整一点。' : '记下一次旅行。' }}</h1>
        <p class="memory-muted">先留下一个到过的城市，照片和文字可以慢慢补。</p>
      </div>
      <span v-if="!loading" class="memory-draft-status" role="status">{{
        storageError
          ? '本机草稿保存失败'
          : draftWriting
            ? '正在保留本机草稿…'
            : localSaved
              ? '本机草稿已保留 · 尚未提交的修改可继续编辑'
              : '准备记录'
      }}</span>
    </header>
    <p v-if="loading" role="status">正在读取记录…</p>
    <p v-if="error" class="memory-error" role="alert">
      {{ error }}
      <button
        v-if="serverId && !record"
        class="memory-link"
        type="button"
        @click="load"
      >
        重新读取已保存内容
      </button>
    </p>
    <p v-if="storageError" class="memory-error" role="alert">
      {{ storageError }} 请暂时保留此页面，可以先保存到服务端或复制文字。<button
        class="memory-link"
        type="button"
        @click="persist"
      >
        重试本机保存
      </button>
    </p>
    <div v-if="localRestored" class="memory-notice">
      已恢复本机未完成编辑及待上传照片。<button
        class="memory-link"
        type="button"
        :disabled="busy"
        @click="discardLocal"
      >
        {{ record ? '放弃本机编辑，使用已保存版本' : '放弃这份本机草稿' }}
      </button>
    </div>
    <section v-if="conflict" class="memory-conflict" role="alert">
      <h2>已保存内容发生了变化</h2>
      <p>本机编辑仍保留。请核对最新保存内容后再决定；继续编辑不会立即写入。</p>
      <details open>
        <summary>最新保存版本：{{ conflict.document.title }}</summary>
        <p>
          {{ formatMemoryDate(conflict.document.when) }} ·
          {{ conflict.document.visits.map((v) => v.city).join(' / ') }} ·
          {{ conflict.document.photos.filter((p) => !p.deleted).length }} 张照片
        </p>
        <p class="memory-prose">
          {{ conflict.document.note || '没有整趟备注' }}
        </p>
        <router-link :to="'/travel-records/' + conflict.id" target="_blank"
          >在新标签查看全部片段和照片</router-link
        >
      </details>
      <p>
        继续后，保存会采用本机的文字、城市和片段；新增的服务端照片会保留，未保留片段的照片关联会解除。
      </p>
      <div class="memory-actions">
        <button class="memory-button" type="button" @click="resolveConflict">
          已核对，以本机内容继续编辑</button
        ><button class="memory-button" type="button" @click="useServer">
          使用最新保存版本
        </button>
      </div>
    </section>
    <div v-if="record?.document.deleted" class="memory-notice">
      这次旅行已移入回收站，请先恢复再编辑。<router-link
        :to="'/travel-records/' + record.id"
        >查看并恢复</router-link
      >
    </div>
    <form v-if="!loading" @submit.prevent="save">
      <fieldset
        :disabled="busy || record?.document.deleted || !!(serverId && !record)"
        class="memory-editor-fields"
      >
        <div
          v-if="!serverId && !source && !form.visits.length"
          class="memory-actions memory-intake-tabs"
        >
          <button
            type="button"
            class="memory-button"
            :aria-pressed="!fromPlan"
            @click="fromPlan = false"
          >
            直接记录</button
          ><button
            type="button"
            class="memory-button"
            :aria-pressed="fromPlan"
            @click="fromPlan = true"
          >
            从已有行程补记
          </button>
        </div>
        <MemorySourcePicker
          v-if="fromPlan && !source && !serverId && !form.visits.length"
          :initial-kind="String(route.query.source_kind || '')"
          :initial-id="String(route.query.source_id || '')"
          @select="adoptSource"
        />
        <section class="memory-editor-section">
          <div class="memory-section-heading">
            <h2>到过的地方</h2>
            <span class="memory-muted">可以记录多座城市或多次到访</span>
          </div>
          <p v-if="source" class="memory-notice">
            补记来源：{{ source.title }}。已确认
            {{ form.visits.length }} 次到访。<button
              v-if="!serverId"
              class="memory-link"
              type="button"
              @click="unlinkSource"
            >
              解除来源，继续独立记录
            </button>
            <button
              v-if="!serverId"
              class="memory-link"
              type="button"
              @click="reselectSource"
            >
              重新核对来源
            </button>
          </p>
          <article
            v-for="(visit, index) in form.visits"
            :key="visit.id"
            class="memory-visit-editor"
          >
            <div class="memory-section-heading">
              <h3>{{ index + 1 }} · {{ visit.city }}</h3>
              <button
                class="memory-link"
                type="button"
                @click="removeVisit(visit.id)"
              >
                移除这次到访
              </button>
            </div>
            <p class="memory-muted">
              {{ visit.region }} · {{ visit.country
              }}{{ visit.latitude === null ? ' · 地球位置待补' : '' }}
            </p>
            <details>
              <summary>调整到访日期和地球位置</summary>
              <MemoryDateEditor v-model="visit.when" label="这次到访时间" />
              <div class="memory-form-grid">
                <label
                  >纬度<input
                    :value="visit.latitude ?? ''"
                    type="number"
                    min="-90"
                    max="90"
                    step="any"
                    @input="coordinate(visit, 'latitude', $event)" /></label
                ><label
                  >经度<input
                    :value="visit.longitude ?? ''"
                    type="number"
                    min="-180"
                    max="180"
                    step="any"
                    @input="coordinate(visit, 'longitude', $event)"
                /></label>
              </div>
              <p class="memory-muted">
                坐标可一起留空。城市名称需要更正时，可移除后重新添加。
              </p>
            </details>
          </article>
          <details
            v-if="!source || serverId"
            :open="!form.visits.length && !fromPlan"
          >
            <summary>
              {{
                form.visits.length
                  ? '再添加一座城市 / 一次到访'
                  : '选择实际去过的城市'
              }}
            </summary>
            <MemoryCityPicker @select="addCity" />
          </details>
        </section>
        <section class="memory-editor-section">
          <h2>给这次旅行留一点文字</h2>
          <label
            >旅行名字 · 可留空<input
              v-model="form.title"
              maxlength="160"
              placeholder="例如 和家人在杭州的周末" /></label
          ><MemoryDateEditor v-model="form.when" /><label
            >最想留下的一幕 · 可留空<textarea
              v-model="form.note"
              maxlength="20000"
              rows="5"
              placeholder="一顿饭、一阵风、一个意外的相遇。一句话也很好。"
            />
          </label>
        </section>
        <section id="memory-photos" class="memory-editor-section">
          <div class="memory-section-heading">
            <h2>照片相册</h2>
            <label class="memory-button memory-file-button"
              >＋ 添加照片<input
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp"
                @change="addPhotos"
            /></label>
          </div>
          <p class="memory-muted">
            保留原图，JPEG / PNG / WebP 每张最多20 MB、4000万像素。HEIC
            可先导出为 JPEG。新增照片会在保存时上传，失败可以重试。
          </p>
          <div v-if="pending.length" class="memory-pending">
            <h3>{{ pending.length }} 张照片待上传</h3>
            <article v-for="photo in pending" :key="photo.id">
              <img :src="pendingUrl(photo)" :alt="photo.file.name" />
              <div>
                <strong>{{ photo.file.name }}</strong
                ><span
                  >{{ (photo.file.size / 1024 / 1024).toFixed(1) }} MB</span
                >
                <p v-if="photo.error" class="memory-error">{{ photo.error }}</p>
              </div>
              <button
                type="button"
                class="memory-link"
                @click="removePending(photo.id)"
              >
                移除
              </button>
            </article>
          </div>
          <div class="memory-photo-edit-grid">
            <article
              v-for="(photo, index) in activePhotoEdits"
              :key="photo.id"
              class="memory-photo-edit"
            >
              <div class="memory-photo-edit-preview">
                <img
                  :src="photoUrl(serverId!, photo.id)"
                  :alt="originalPhoto(photo.id)?.filename || '旅行照片'"
                  :style="{
                    objectPosition: photo.focal_x + '% ' + photo.focal_y + '%',
                  }"
                /><span
                  v-if="form.cover_photo_id === photo.id"
                  class="memory-cover-label"
                  >相册封面</span
                >
              </div>
              <label
                >照片说明<textarea
                  v-model="photo.caption"
                  rows="2"
                  maxlength="2000"
                  placeholder="这张照片背后的故事"
                /></label
              ><label
                >关联回忆片段<select v-model="photo.moment_id">
                  <option :value="null">不关联</option>
                  <option
                    v-if="
                      photo.moment_id &&
                      deletedMoments.some((m) => m.id === photo.moment_id)
                    "
                    :value="photo.moment_id"
                  >
                    已移入回收站的片段（恢复后可见）
                  </option>
                  <option
                    v-for="moment in activeMoments"
                    :key="moment.id"
                    :value="moment.id"
                  >
                    {{
                      moment.title || moment.text.slice(0, 30) || '未命名片段'
                    }}
                  </option>
                </select></label
              >
              <div class="memory-actions">
                <button
                  type="button"
                  class="memory-button"
                  @click="form.cover_photo_id = photo.id"
                >
                  设为封面</button
                ><button
                  type="button"
                  class="memory-link"
                  :disabled="index === 0"
                  @click="movePhoto(photo.id, -1)"
                >
                  向前</button
                ><button
                  type="button"
                  class="memory-link"
                  :disabled="index === activePhotoEdits.length - 1"
                  @click="movePhoto(photo.id, 1)"
                >
                  向后</button
                ><button
                  type="button"
                  class="memory-link"
                  @click="deletePhoto(photo)"
                >
                  移入回收站
                </button>
              </div>
              <details v-if="form.cover_photo_id === photo.id">
                <summary>调整封面取景（原图保留）</summary>
                <label
                  >水平位置<input
                    v-model.number="photo.focal_x"
                    type="range"
                    min="0"
                    max="100" /></label
                ><label
                  >垂直位置<input
                    v-model.number="photo.focal_y"
                    type="range"
                    min="0"
                    max="100"
                /></label>
              </details>
            </article>
          </div>
          <details v-if="deletedPhotoEdits.length" class="memory-photo-trash">
            <summary>照片回收站（{{ deletedPhotoEdits.length }}）</summary>
            <div class="memory-trashed-photos">
              <article v-for="photo in deletedPhotoEdits" :key="photo.id">
                <img
                  :src="photoUrl(serverId!, photo.id)"
                  :alt="originalPhoto(photo.id)?.filename || '已移除照片'"
                /><span>{{ originalPhoto(photo.id)?.filename }}</span
                ><button
                  type="button"
                  class="memory-button"
                  @click="photo.deleted = false"
                >
                  恢复照片
                </button>
              </article>
            </div>
          </details>
        </section>
        <section class="memory-editor-section">
          <div class="memory-section-heading">
            <h2>想留下的片段 · 可选</h2>
            <button class="memory-button" type="button" @click="addMoment">
              ＋ 补一段回忆
            </button>
          </div>
          <article
            v-for="moment in activeMoments"
            :key="moment.id"
            class="memory-moment-editor"
          >
            <label
              >片段标题<input
                v-model="moment.title"
                maxlength="120"
                placeholder="没赶时间的下午"
            /></label>
            <div class="memory-form-grid">
              <label
                >关联城市<select v-model="moment.visit_id">
                  <option :value="null">整趟旅行</option>
                  <option
                    v-for="visit in form.visits"
                    :key="visit.id"
                    :value="visit.id"
                  >
                    {{ visit.city }} · {{ formatMemoryDate(visit.when) }}
                  </option>
                </select></label
              ><label
                >具体地点 · 可留空<input
                  v-model="moment.place"
                  maxlength="200"
                  placeholder="一条街、一家店，或一个地名"
              /></label>
            </div>
            <label
              >想记住什么？<textarea
                v-model="moment.text"
                maxlength="20000"
                rows="4"
              />
            </label>
            <details>
              <summary>补充片段日期</summary>
              <MemoryDateEditor v-model="moment.when" label="片段时间" />
            </details>
            <button
              class="memory-link"
              type="button"
              @click="deleteMoment(moment)"
            >
              移入片段回收站（保留照片）
            </button>
          </article>
          <details v-if="deletedMoments.length">
            <summary>片段回收站（{{ deletedMoments.length }}）</summary>
            <article
              v-for="moment in deletedMoments"
              :key="moment.id"
              class="memory-moment-editor"
            >
              <strong>{{ moment.title || '未命名片段' }}</strong>
              <p class="memory-prose">{{ moment.text }}</p>
              <button
                class="memory-button"
                type="button"
                @click="moment.deleted = false"
              >
                恢复片段
              </button>
            </article>
          </details>
        </section>
      </fieldset>
      <div class="memory-save-bar">
        <div>
          <strong>{{
            progress ||
            (hasChanges
              ? '有修改等待保存'
              : serverId
                ? '内容与已保存版本一致'
                : '记录准备好后即可保存')
          }}</strong
          ><span>{{
            pending.length
              ? pending.length + ' 张照片待上传'
              : '日期、照片和文字都可以以后再补'
          }}</span>
        </div>
        <button
          class="memory-button memory-primary"
          type="submit"
          :disabled="
            busy ||
            loading ||
            !!conflict ||
            !!record?.document.deleted ||
            !!(serverId && !record) ||
            !form.visits.length
          "
        >
          {{
            busy
              ? '正在保存…'
              : pending.length
                ? '保存并上传照片'
                : '保存旅行记录'
          }}
        </button>
      </div>
    </form>
  </main>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, toRaw, watch } from 'vue'
import {
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  useRoute,
  useRouter,
} from 'vue-router'
import MemoryCityPicker from '@/components/memory/MemoryCityPicker.vue'
import MemoryDateEditor from '@/components/memory/MemoryDateEditor.vue'
import MemorySourcePicker from '@/components/memory/MemorySourcePicker.vue'
import { memoryApi, MemoryApiError, photoUrl } from '@/services/travelMemory'
import { memoryDrafts } from '@/services/memoryDrafts'
import {
  emptyMemoryForm,
  formatMemoryDate,
  formFromRecord,
  memoryId,
  mergePhotoEdits,
  unknownDate,
} from '@/utils/travelMemory'
import type {
  MemoryCity,
  MemoryDate,
  MemoryDraft,
  MemoryForm,
  MemoryMoment,
  MemoryPhotoEdit,
  MemorySourceRef,
  MemoryVisit,
  PendingPhoto,
  TravelMemory,
} from '@/types/travelMemory'
import '@/styles/travel-memories.css'
const route = useRoute(),
  router = useRouter(),
  id = ref(''),
  serverId = ref<string | null>(null),
  revision = ref(0),
  record = ref<TravelMemory | null>(null)
const form = ref<MemoryForm>(emptyMemoryForm()),
  source = ref<MemorySourceRef | null>(null),
  pending = ref<PendingPhoto[]>([]),
  operationId = ref(memoryId())
const loading = ref(true),
  busy = ref(false),
  error = ref(''),
  progress = ref(''),
  storageError = ref(''),
  draftWriting = ref(false),
  localSaved = ref(false),
  localRestored = ref(false),
  fromPlan = ref(false),
  conflict = ref<TravelMemory | null>(null)
let generation = 0,
  writeVersion = 0,
  finishing = false,
  writes: Promise<unknown> = Promise.resolve()
const objectUrls = new Map<string, string>()
const activePhotoEdits = computed(() =>
    form.value.photos.filter((p) => !p.deleted),
  ),
  deletedPhotoEdits = computed(() =>
    form.value.photos.filter((p) => p.deleted),
  ),
  activeMoments = computed(() => form.value.moments.filter((m) => !m.deleted)),
  deletedMoments = computed(() => form.value.moments.filter((m) => m.deleted))
const hasChanges = computed(
  () =>
    !!pending.value.length ||
    !record.value ||
    JSON.stringify(form.value) !== JSON.stringify(formFromRecord(record.value)),
)
const draftKey = () => 'memory:' + id.value
const originalPhoto = (photoId: string) =>
  record.value?.document.photos.find((p) => p.id === photoId)
function snapshot(): MemoryDraft {
  return {
    key: draftKey(),
    id: id.value,
    serverId: serverId.value,
    revision: revision.value,
    form: JSON.parse(JSON.stringify(form.value)),
    source: source.value ? JSON.parse(JSON.stringify(source.value)) : null,
    operationId: operationId.value,
    pending: pending.value.map((p) => ({
      id: p.id,
      file: toRaw(p.file),
      error: p.error,
    })),
    updated: Date.now(),
    cachedRecord: record.value
      ? JSON.parse(JSON.stringify(record.value))
      : undefined,
  }
}
function persist() {
  if (loading.value || finishing || !id.value) return writes
  const existingDraft =
    localSaved.value || localRestored.value || draftWriting.value
  if (
    !serverId.value &&
    !form.value.visits.length &&
    !form.value.title &&
    !form.value.note &&
    !form.value.moments.length &&
    !pending.value.length &&
    !existingDraft
  )
    return writes
  if (!hasChanges.value && !existingDraft && !busy.value) return writes
  const data = snapshot(),
    current = ++writeVersion
  draftWriting.value = true
  writes = writes
    .catch(() => {})
    .then(() => memoryDrafts.put(data))
    .then(() => {
      if (current === writeVersion) {
        storageError.value = ''
        localSaved.value = true
        draftWriting.value = false
      }
    })
    .catch(() => {
      if (current === writeVersion) {
        storageError.value = '浏览器未能保留本机草稿，可能是存储空间不足。'
        draftWriting.value = false
      }
    })
  return writes
}
watch(
  [form, pending, source],
  () => {
    if (!loading.value && !finishing) {
      if (!busy.value) operationId.value = memoryId()
      void persist()
    }
  },
  { deep: true },
)
async function load() {
  if (
    !route.params.id &&
    !/^[a-f0-9]{32}$/.test(String(route.query.draft || ''))
  ) {
    await router.replace({
      path: '/travel-records/new',
      query: { ...route.query, draft: memoryId() },
    })
    return
  }
  const current = ++generation
  loading.value = true
  finishing = false
  error.value = ''
  storageError.value = ''
  localRestored.value = false
  localSaved.value = false
  conflict.value = null
  record.value = null
  pending.value = []
  source.value = null
  form.value = emptyMemoryForm()
  id.value = String(route.params.id || route.query.draft)
  serverId.value = route.params.id ? String(route.params.id) : null
  revision.value = 0
  fromPlan.value = route.query.from === 'plan' || !!route.query.source_id
  let local: MemoryDraft | undefined
  try {
    local = await memoryDrafts.get(draftKey())
  } catch {
    storageError.value =
      '本机草稿库暂时无法读取，请保留页面并尽快保存到服务端。'
  }
  if (current !== generation) return
  serverId.value = serverId.value || local?.serverId || null
  if (serverId.value) {
    try {
      const saved = await memoryApi.get(serverId.value)
      if (current !== generation) return
      record.value = saved
      revision.value = record.value.revision
      form.value = formFromRecord(record.value)
      source.value = record.value.document.source
    } catch (e) {
      if (current !== generation) return
      error.value = (e as Error).message
      record.value = local?.cachedRecord || null
    }
  }
  if (current !== generation) return
  if (local) {
    form.value = local.form
    pending.value = local.pending
    source.value = local.source
    revision.value = local.revision
    operationId.value = local.operationId
    localRestored.value = true
    localSaved.value = true
    if (record.value && record.value.revision !== local.revision)
      conflict.value = record.value
  } else operationId.value = memoryId()
  await nextTick()
  if (current === generation) loading.value = false
}
watch(() => [route.params.id, route.query.draft], load, { immediate: true })
function addCity(city: MemoryCity) {
  const { search, ...fields } = city
  form.value.visits.push({ ...fields, id: memoryId(), when: unknownDate() })
}
function adoptSource(
  value: MemorySourceRef,
  visits: MemoryVisit[],
  when: MemoryDate,
) {
  source.value = value
  form.value.visits = visits
  form.value.when = when
  if (!form.value.title) form.value.title = value.title.slice(0, 160)
}
function unlinkSource() {
  source.value = null
  fromPlan.value = false
}
function reselectSource() {
  source.value = null
  fromPlan.value = true
  form.value.visits = []
  for (const moment of form.value.moments) moment.visit_id = null
}
function removeVisit(visitId: string) {
  form.value.visits = form.value.visits.filter((v) => v.id !== visitId)
  for (const m of form.value.moments)
    if (m.visit_id === visitId) m.visit_id = null
}
function coordinate(
  visit: MemoryVisit,
  field: 'latitude' | 'longitude',
  event: Event,
) {
  const value = (event.target as HTMLInputElement).value
  visit[field] = value === '' ? null : Number(value)
}
function addMoment() {
  form.value.moments.push({
    id: memoryId(),
    title: '',
    text: '',
    place: '',
    visit_id: null,
    when: unknownDate(),
    deleted: false,
  })
}
function deleteMoment(moment: MemoryMoment) {
  moment.deleted = true
}
function deletePhoto(photo: MemoryPhotoEdit) {
  photo.deleted = true
  if (form.value.cover_photo_id === photo.id)
    form.value.cover_photo_id =
      activePhotoEdits.value.find((p) => p.id !== photo.id)?.id || null
}
function movePhoto(photoId: string, delta: number) {
  const active = activePhotoEdits.value,
    target = active[active.findIndex((p) => p.id === photoId) + delta]
  if (!target) return
  const a = form.value.photos.findIndex((p) => p.id === photoId),
    b = form.value.photos.findIndex((p) => p.id === target.id)
  ;[form.value.photos[a], form.value.photos[b]] = [
    form.value.photos[b],
    form.value.photos[a],
  ]
}
function addPhotos(event: Event) {
  const input = event.target as HTMLInputElement,
    files = Array.from(input.files || [])
  input.value = ''
  error.value = ''
  for (const file of files) {
    if (
      !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) ||
      file.size > 20 * 1024 * 1024
    ) {
      error.value =
        '部分照片未添加：支持 JPEG、PNG、WebP，每张最多20 MB。HEIC 请先导出为 JPEG。'
      continue
    }
    if (form.value.photos.length + pending.value.length >= 500) {
      error.value = '每次旅行最多500张照片（含回收站）'
      break
    }
    pending.value.push({ id: memoryId(), file, error: '' })
  }
}
function pendingUrl(photo: PendingPhoto) {
  if (!objectUrls.has(photo.id))
    objectUrls.set(photo.id, URL.createObjectURL(toRaw(photo.file)))
  return objectUrls.get(photo.id)
}
function removePending(photoId: string) {
  pending.value = pending.value.filter((p) => p.id !== photoId)
  const url = objectUrls.get(photoId)
  if (url) URL.revokeObjectURL(url)
  objectUrls.delete(photoId)
}
function applySaved(value: TravelMemory) {
  record.value = value
  serverId.value = value.id
  revision.value = value.revision
  form.value = formFromRecord(value)
  source.value = value.document.source
}
async function save() {
  if (
    busy.value ||
    conflict.value ||
    !form.value.visits.length ||
    (serverId.value && !record.value)
  )
    return
  busy.value = true
  error.value = ''
  progress.value = '正在保存旅行文字…'
  await persist()
  try {
    if (!serverId.value)
      applySaved(await memoryApi.create(id.value, form.value, source.value))
    else if (
      !record.value ||
      JSON.stringify(form.value) !==
        JSON.stringify(formFromRecord(record.value))
    )
      applySaved(
        await memoryApi.update(
          serverId.value,
          revision.value,
          form.value,
          operationId.value,
        ),
      )
    await persist()
    const queue = [...pending.value]
    for (let index = 0; index < queue.length; index++) {
      const photo = queue[index]
      progress.value = '正在上传照片 ' + (index + 1) + ' / ' + queue.length
      try {
        applySaved(
          await memoryApi.upload(
            serverId.value!,
            revision.value,
            photo.id,
            toRaw(photo.file),
          ),
        )
        removePending(photo.id)
        await persist()
      } catch (e) {
        photo.error = (e as Error).message
        const entry = pending.value.find((p) => p.id === photo.id)
        if (entry) entry.error = photo.error
        if (e instanceof MemoryApiError && e.status === 409) {
          conflict.value = await memoryApi.get(serverId.value!)
        }
        // Stop here so retrying preserves the user's original selection order.
        break
      }
    }
    if (pending.value.length) {
      await persist()
      error.value =
        '旅行文字已保存，仍有 ' +
        pending.value.length +
        ' 张照片未完成上传。' +
        (storageError.value
          ? '本机草稿未能保存，请保留此页面并重试上传。'
          : '本机已保留，可再次点击保存重试。')
      return
    }
    await nextTick()
    finishing = true
    await writes
    await memoryDrafts.remove(draftKey())
    await router.replace('/travel-records/' + serverId.value)
  } catch (e) {
    finishing = false
    error.value = (e as Error).message
    if (e instanceof MemoryApiError && e.status === 409 && serverId.value) {
      try {
        conflict.value = await memoryApi.get(serverId.value)
      } catch {}
    }
    await persist()
  } finally {
    busy.value = false
    progress.value = ''
  }
}
function resolveConflict() {
  if (!conflict.value) return
  form.value = mergePhotoEdits(form.value, conflict.value)
  record.value = conflict.value
  revision.value = conflict.value.revision
  conflict.value = null
  error.value = ''
  operationId.value = memoryId()
  void persist()
}
function useServer() {
  if (!conflict.value) return
  applySaved(conflict.value)
  conflict.value = null
  error.value = ''
  void persist()
}
async function discardLocal() {
  if (!window.confirm('放弃本机未保存的文字和待上传照片？已保存的回忆会保留。'))
    return
  finishing = true
  await writes
  await memoryDrafts.remove(draftKey())
  if (serverId.value) await router.replace('/travel-records/' + serverId.value)
  else await router.replace('/travel-records')
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (busy.value || draftWriting.value || storageError.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', beforeUnload)
async function canLeaveEditor() {
  if (finishing) return true
  if (busy.value) {
    error.value = '正在保存，请等待本次保存完成后再离开。'
    return false
  }
  await persist()
  return (
    !storageError.value ||
    window.confirm('本机草稿未保存成功。离开可能丢失编辑，仍要离开吗？')
  )
}
onBeforeRouteLeave(canLeaveEditor)
onBeforeRouteUpdate(async (to, from) => {
  if (to.params.id !== from.params.id || to.query.draft !== from.query.draft)
    return canLeaveEditor()
  return true
})
onBeforeUnmount(() => {
  generation++
  window.removeEventListener('beforeunload', beforeUnload)
  objectUrls.forEach((url) => URL.revokeObjectURL(url))
})
</script>

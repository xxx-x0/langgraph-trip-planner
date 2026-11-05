<template>
  <section class="memory-city-picker">
    <label
      >找一座去过的城市<input
        v-model="query"
        type="search"
        placeholder="搜索城市名称或拼音"
        autocomplete="off"
    /></label>
    <p v-if="loading" class="memory-muted" role="status">正在查找城市…</p>
    <p v-if="error" class="memory-error" role="alert">{{ error }}</p>
    <div class="memory-city-options">
      <button
        v-for="(city, index) in options"
        :key="index"
        type="button"
        @click="$emit('select', city)"
      >
        <strong>{{ city.city }}</strong
        ><span>{{ city.region }} · {{ city.country }}</span>
      </button>
    </div>
    <p class="memory-muted memory-city-credit">
      离线城市位置来自
      <a
        href="https://www.geonames.org/"
        target="_blank"
        rel="noopener noreferrer"
        >GeoNames</a
      >（<a
        href="https://creativecommons.org/licenses/by/4.0/"
        target="_blank"
        rel="noopener noreferrer"
        >CC BY 4.0</a
      >）及原地球参考城市库。请核对省州和国家；缺少的城市可以手动添加。
    </p>
    <details class="memory-manual-city">
      <summary>没有找到？手动记录城市</summary>
      <p class="memory-muted">
        可以先保存城市，坐标留空时暂不在地球上打点。以后可以补充城市中心的经纬度。
      </p>
      <div class="memory-form-grid">
        <label>城市名称<input v-model="manual.city" maxlength="100" /></label
        ><label
          >国家 / 地区<input v-model="manual.country" maxlength="100" /></label
        ><label
          >省 / 州 · 可留空<input v-model="manual.region" maxlength="100"
        /></label>
      </div>
      <details>
        <summary>补充地球位置 · 可选</summary>
        <div class="memory-form-grid">
          <label
            >纬度（−90 至 90）<input
              v-model.number="manual.latitude"
              type="number"
              min="-90"
              max="90"
              step="any" /></label
          ><label
            >经度（−180 至 180）<input
              v-model.number="manual.longitude"
              type="number"
              min="-180"
              max="180"
              step="any"
          /></label>
        </div>
      </details>
      <button
        class="memory-button"
        type="button"
        :disabled="!manual.city.trim()"
        @click="addManual"
      >
        添加这个城市
      </button>
    </details>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { memoryApi } from '@/services/travelMemory'
import type { MemoryCity } from '@/types/travelMemory'
const emit = defineEmits<{ select: [city: MemoryCity] }>()
const query = ref(''),
  options = ref<MemoryCity[]>([]),
  error = ref(''),
  loading = ref(false)
const manual = reactive({
  city: '',
  country: '中国',
  region: '',
  latitude: '' as number | string,
  longitude: '' as number | string,
})
let generation = 0,
  timer: ReturnType<typeof setTimeout>
watch(
  query,
  () => {
    clearTimeout(timer)
    const current = ++generation
    timer = setTimeout(async () => {
      loading.value = true
      error.value = ''
      try {
        const data = await memoryApi.cities(query.value)
        if (current === generation) options.value = data
      } catch (e) {
        if (current === generation) error.value = (e as Error).message
      } finally {
        if (current === generation) loading.value = false
      }
    }, 180)
  },
  { immediate: true },
)
function addManual() {
  error.value = ''
  const latitude = manual.latitude === '' ? null : Number(manual.latitude),
    longitude = manual.longitude === '' ? null : Number(manual.longitude)
  if (
    (latitude === null) !== (longitude === null) ||
    (latitude !== null &&
      (!Number.isFinite(latitude) || Math.abs(latitude) > 90)) ||
    (longitude !== null &&
      (!Number.isFinite(longitude) || Math.abs(longitude) > 180))
  ) {
    error.value = '请填写完整、有效的经纬度，或一起留空'
    return
  }
  emit('select', {
    city: manual.city.trim(),
    country: manual.country.trim(),
    region: manual.region.trim(),
    latitude,
    longitude,
  })
  manual.city = ''
  manual.latitude = ''
  manual.longitude = ''
}
onBeforeUnmount(() => {
  clearTimeout(timer)
  generation++
})
</script>

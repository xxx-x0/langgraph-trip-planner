<template>
  <dialog
    ref="dialog"
    class="memory-lightbox"
    aria-label="查看旅行照片"
    @close="$emit('close')"
    @click="backdrop"
    @keydown="keys"
  >
    <div v-if="photo" class="memory-lightbox-body">
      <header>
        <span>{{ index + 1 }} / {{ photos.length }}</span
        ><button type="button" @click="dialog?.close()" aria-label="关闭照片">
          关闭 ×
        </button>
      </header>
      <img
        v-if="!failed"
        :key="photo.id"
        :src="photoUrl(recordId, photo.id, false)"
        :alt="photo.caption || photo.filename"
        @error="failed = true"
      />
      <p v-else role="alert">
        照片原件暂时无法加载。可以重试，或从备份恢复原件。<button
          type="button"
          @click="failed = false"
        >
          重试
        </button>
      </p>
      <footer>
        <button
          type="button"
          :disabled="index === 0"
          @click="$emit('change', index - 1)"
        >
          ← 上一张
        </button>
        <div>
          <p>{{ photo.caption || photo.filename }}</p>
          <a :href="photoUrl(recordId, photo.id, false, true)">下载原图</a>
        </div>
        <button
          type="button"
          :disabled="index === photos.length - 1"
          @click="$emit('change', index + 1)"
        >
          下一张 →
        </button>
      </footer>
    </div>
  </dialog>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { MemoryPhoto } from '@/types/travelMemory'
import { photoUrl } from '@/services/travelMemory'
const props = defineProps<{
  recordId: string
  photos: MemoryPhoto[]
  index: number
}>()
const emit = defineEmits<{ close: []; change: [index: number] }>()
const dialog = ref<HTMLDialogElement>(),
  failed = ref(false),
  photo = computed(() => props.photos[props.index])
watch(
  () => props.index,
  () => {
    failed.value = false
  },
)
onMounted(() => dialog.value?.showModal())
function backdrop(event: MouseEvent) {
  if (event.target === dialog.value) dialog.value?.close()
}
function keys(event: KeyboardEvent) {
  if (event.key === 'ArrowRight' && props.index < props.photos.length - 1)
    emit('change', props.index + 1)
  if (event.key === 'ArrowLeft' && props.index > 0)
    emit('change', props.index - 1)
}
</script>

<template>
  <details class="memory-backup">
    <summary>备份与恢复</summary>
    <p>
      备份包含旅行、文字、照片原件和回收站。恢复会先核对内容，已有回忆始终保留。
    </p>
    <div class="memory-actions">
      <button
        class="memory-button"
        type="button"
        :disabled="busy"
        @click="exportAll"
      >
        {{ action === 'export' ? '正在整理原件…' : '下载完整备份' }}</button
      ><label class="memory-button memory-file-button"
        >选择备份恢复<input
          type="file"
          accept=".zip,application/zip"
          :disabled="busy"
          @change="selectBackup"
      /></label>
    </div>
    <p class="memory-muted">
      JPEG / PNG / WebP 原件随备份保存；单份备份上限512
      MB。本机未保存编辑需要先保存，才会进入备份。
    </p>
    <p v-if="error" class="memory-error" role="alert">{{ error }}</p>
    <p v-if="status" role="status">{{ status }}</p>
    <div v-if="preview" class="memory-restore-preview">
      <h3>恢复前核对</h3>
      <p>
        新增 {{ preview.counts.new }} 条 · 相同
        {{ preview.counts.identical }} 条 · 冲突
        {{ preview.counts.conflict }} 条 · 已恢复过
        {{ preview.counts.already_restored }} 条
      </p>
      <p>
        需要恢复或修复
        {{ preview.photo_files_to_restore }} 个照片原件。预览有效期一小时。
      </p>
      <ul>
        <li v-for="item in preview.items" :key="item.id">
          {{ item.title }}{{ item.deleted ? '（回收站）' : '' }} ·
          {{ labels[item.status] }} · {{ item.photos }} 张照片
        </li>
      </ul>
      <label v-if="preview.counts.conflict"
        >冲突记录如何处理<select v-model="conflicts">
          <option value="copy">保留现有内容，另存恢复副本</option>
          <option value="skip">保留现有内容，跳过冲突</option>
        </select></label
      >
      <div class="memory-actions">
        <button
          class="memory-button memory-primary"
          type="button"
          :disabled="busy"
          @click="confirm"
        >
          {{ action === 'restore' ? '正在恢复…' : '确认恢复' }}</button
        ><button
          class="memory-button"
          type="button"
          :disabled="busy"
          @click="preview = null"
        >
          取消</button
        ><button
          v-if="selectedFile"
          class="memory-link"
          type="button"
          :disabled="busy"
          @click="inspect(selectedFile)"
        >
          重新预览
        </button>
      </div>
    </div>
  </details>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { downloadBlob, memoryApi } from '@/services/travelMemory'
import type { RestorePreview } from '@/types/travelMemory'
const emit = defineEmits<{ restored: [] }>()
const action = ref(''),
  busy = computed(() => !!action.value),
  error = ref(''),
  status = ref(''),
  preview = ref<RestorePreview | null>(null),
  selectedFile = ref<File | null>(null),
  conflicts = ref<'copy' | 'skip'>('copy')
const labels = {
  new: '新增',
  identical: '相同，将跳过',
  conflict: '与现有回忆不同',
  already_restored: '已恢复过，将跳过',
}
async function exportAll() {
  action.value = 'export'
  error.value = ''
  status.value = ''
  try {
    downloadBlob(
      await memoryApi.backup(),
      'travel-memories-' + new Date().toISOString().slice(0, 10) + '.zip',
    )
    status.value = '完整备份已交给浏览器下载，请妥善保存。'
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    action.value = ''
  }
}
async function selectBackup(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0]
  input.value = ''
  if (file) {
    selectedFile.value = file
    await inspect(file)
  }
}
async function inspect(file: File) {
  preview.value = null
  error.value = ''
  status.value = ''
  if (file.size > 512 * 1024 * 1024) {
    error.value = '备份最多512 MB'
    return
  }
  action.value = 'preview'
  status.value = '正在检查记录、照片和校验信息…'
  try {
    preview.value = await memoryApi.previewRestore(file)
    status.value = ''
  } catch (e) {
    error.value = (e as Error).message
    status.value = ''
  } finally {
    action.value = ''
  }
}
async function confirm() {
  if (!preview.value) return
  action.value = 'restore'
  error.value = ''
  try {
    const result = await memoryApi.restore(preview.value.token, conflicts.value)
    status.value =
      '恢复完成：新增 ' +
      result.added +
      ' 条，恢复副本 ' +
      result.copied +
      ' 条，跳过 ' +
      result.skipped +
      ' 条。'
    preview.value = null
    emit('restored')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    action.value = ''
  }
}
</script>

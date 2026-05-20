<template>
  <a-popover trigger="click" placement="bottom">
    <template #content>
      <a-tabs v-model:activeKey="activeCat" size="small" style="width: 320px">
        <a-tab-pane v-for="cat in categories" :key="cat" :tab="catLabel[cat]">
          <div v-if="pool[cat]?.length">
            <div v-for="c in pool[cat]" :key="c.name" class="candidate"
                 @click="onPick(cat, c)">
              <strong>{{ c.name }}</strong>
              <span v-if="c.rating">{{ c.rating }}⭐</span>
              <span v-if="c.avg_cost">¥{{ c.avg_cost }}</span>
              <span v-if="c.distance">{{ c.distance }}</span>
            </div>
          </div>
          <a-empty v-else description="无候选，可自定义" />
          <a-divider />
          <a-input v-model:value="customName" :placeholder="`自定义 ${catLabel[cat]} 名称`" />
          <a-button block @click="onPickCustom(cat)" :disabled="!customName">添加自定义</a-button>
        </a-tab-pane>
      </a-tabs>
    </template>
    <a-button size="small">+ 加用餐</a-button>
  </a-popover>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  pool: any
  insertAfter: string
}>()
const emit = defineEmits<{
  (e: 'add', meal: any): void
}>()

const categories = ['main', 'snack', 'dessert', 'cafe', 'late_night']
const catLabel: Record<string, string> = {
  main: '正餐', snack: '小吃', dessert: '甜品', cafe: '咖啡', late_night: '夜宵',
}
const activeCat = ref('main')
const customName = ref('')

function onPick(cat: string, c: any) {
  emit('add', { ...c, category: cat, insert_after: props.insertAfter })
}

function onPickCustom(cat: string) {
  emit('add', {
    name: customName.value, category: cat,
    source: 'user_custom', insert_after: props.insertAfter,
  })
  customName.value = ''
}
</script>

<style scoped>
.candidate {
  display: flex; gap: 8px; padding: 6px 4px; cursor: pointer;
  border-radius: 4px;
}
.candidate:hover { background: #f0f0f0; }
</style>

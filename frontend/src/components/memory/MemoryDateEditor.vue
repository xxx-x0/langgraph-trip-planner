<template>
  <div class="memory-date-editor">
    <label
      >{{ label
      }}<select :value="modelValue.precision" @change="precisionChanged">
        <option value="unknown">日期不记得</option>
        <option value="year">只记得年份</option>
        <option value="month">记得月份</option>
        <option value="day">记得具体日期</option>
      </select></label
    >
    <template v-if="modelValue.precision !== 'unknown'">
      <label
        >{{ modelValue.precision === 'year' ? '开始年份' : '开始'
        }}<input
          :type="inputType"
          :value="modelValue.start"
          :max="maximum"
          :placeholder="modelValue.precision === 'year' ? '例如 2024' : ''"
          :maxlength="modelValue.precision === 'year' ? 4 : undefined"
          @input="change('start', $event)"
      /></label>
      <label
        >{{
          modelValue.precision === 'year'
            ? '结束年份 · 可留空'
            : '结束 · 可留空'
        }}<input
          :type="inputType"
          :value="modelValue.end"
          :max="maximum"
          :maxlength="modelValue.precision === 'year' ? 4 : undefined"
          @input="change('end', $event)"
      /></label>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { DatePrecision, MemoryDate } from '@/types/travelMemory'
const props = withDefaults(
  defineProps<{ modelValue: MemoryDate; label?: string }>(),
  { label: '旅行时间' },
)
const emit = defineEmits<{ 'update:modelValue': [value: MemoryDate] }>()
const inputType = computed(() =>
  props.modelValue.precision === 'day'
    ? 'date'
    : props.modelValue.precision === 'month'
      ? 'month'
      : 'text',
)
const today = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date())
const maximum = computed(() =>
  today.slice(
    0,
    { unknown: 0, year: 4, month: 7, day: 10 }[props.modelValue.precision],
  ),
)
function precisionChanged(event: Event) {
  const precision = (event.target as HTMLSelectElement).value as DatePrecision
  const length = { unknown: 0, year: 4, month: 7, day: 10 }[precision]
  emit('update:modelValue', {
    precision,
    start:
      props.modelValue.start.length >= length
        ? props.modelValue.start.slice(0, length)
        : '',
    end:
      props.modelValue.end.length >= length
        ? props.modelValue.end.slice(0, length)
        : '',
  })
}
function change(key: 'start' | 'end', event: Event) {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: (event.target as HTMLInputElement).value,
  })
}
</script>

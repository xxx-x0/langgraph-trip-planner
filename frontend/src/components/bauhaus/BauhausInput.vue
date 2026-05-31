<script setup lang="ts">
interface Props {
  modelValue: string
  placeholder?: string
  disabled?: boolean
  type?: 'text' | 'number' | 'email'
}

withDefaults(defineProps<Props>(), {
  placeholder: '',
  disabled: false,
  type: 'text'
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <input
    class="bauhaus-input"
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="handleInput"
  />
</template>

<style scoped>
/* 组件使用全局定义的 bauhaus-input 样式类 */
</style>

<script setup lang="ts">
interface Props {
  variant?: 'primary' | 'secondary' | 'yellow' | 'outline'
  shape?: 'square' | 'pill'
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  shape: 'square',
  disabled: false
})
</script>

<template>
  <button
    class="bauhaus-btn"
    :class="[
      `bauhaus-btn-${variant}`,
      `bauhaus-btn-${shape}`
    ]"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<style scoped>
/* 组件使用全局定义的 bauhaus-btn 样式类 */
/* 无需额外样式，所有样式已在 bauhaus-components.css 中定义 */
</style>

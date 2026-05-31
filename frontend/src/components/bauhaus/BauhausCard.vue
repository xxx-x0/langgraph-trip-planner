<script setup lang="ts">
interface Props {
  decoration?: 'circle' | 'square' | 'none'
  accentColor?: 'red' | 'blue' | 'yellow'
}

withDefaults(defineProps<Props>(), {
  decoration: 'circle',
  accentColor: 'blue'
})
</script>

<template>
  <div
    class="bauhaus-card"
    :class="[
      decoration !== 'none' ? `decoration-${decoration}` : '',
      decoration !== 'none' ? `decoration-${accentColor}` : ''
    ]"
  >
    <slot />
  </div>
</template>

<style scoped>
/* 组件使用全局定义的 bauhaus-card 样式类 */
</style>

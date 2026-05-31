<script setup lang="ts">
interface Props {
  shape: 'circle' | 'square'
  color: 'red' | 'blue' | 'yellow'
  size?: number
}

withDefaults(defineProps<Props>(), {
  size: 40
})
</script>

<template>
  <div
    :class="`geometric-${shape}`"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      background: `var(--primary-${color})`
    }"
  />
</template>

<style scoped>
/* 组件使用全局定义的 geometric-* 样式类 */
</style>

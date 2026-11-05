<template>
  <section ref="wrapper" class="memory-globe" aria-label="旅行足迹地球">
    <div class="memory-globe-heading">
      <span>MY TRAVEL GLOBE</span
      ><button type="button" :disabled="reducedMotion" @click="toggleRotation">
        {{
          reducedMotion ? '减少动态已开启' : rotating ? '暂停转动' : '自动转动'
        }}
      </button>
    </div>
    <canvas
      ref="canvas"
      tabindex="0"
      role="img"
      aria-label="旅行地球，可拖动或用方向键旋转；通过城市列表选择回忆"
      :data-render-state="ready ? 'ready' : 'loading'"
      @keydown="keyboard"
      @pointerdown="pointerDown"
      @pointermove="pointerMove"
      @pointerup="pointerUp"
      @pointercancel="pointerUp"
      @webglcontextlost.prevent="lostContext"
    />
    <p v-if="error" class="memory-globe-fallback" role="status">{{ error }}</p>
    <div class="memory-globe-controls">
      <button type="button" aria-label="向左旋转地球" @click="rotate(-0.2, 0)">
        ←</button
      ><span>{{
        selected
          ? '拖动查看周边 · 选择城市回看旅行'
          : '拖动地球 · 选择城市打开回忆'
      }}</span
      ><button type="button" aria-label="向右旋转地球" @click="rotate(0.2, 0)">
        →
      </button>
    </div>
  </section>
</template>
<script setup lang="ts">
// Visual settings and camera math adapted from finn-digital/TravelGlobe (COBE 2.0.1).
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Globe, Marker } from 'cobe'
import type { MemoryFootprint } from '@/types/travelMemory'
import {
  clamp,
  createFocusedGlobeView,
  easeAngle,
  easeNumber,
} from '@/utils/memoryGlobe'
const props = defineProps<{
  places: MemoryFootprint[]
  selectedKey: string | null
}>()
const canvas = ref<HTMLCanvasElement>(),
  wrapper = ref<HTMLElement>(),
  error = ref(''),
  ready = ref(false),
  rotating = ref(true),
  reducedMotion = ref(false)
const selected = computed(() =>
  props.places.find(
    (p) =>
      p.key === props.selectedKey &&
      p.latitude !== null &&
      p.longitude !== null,
  ),
)
let globe: Globe | null = null,
  frame = 0,
  mounted = false,
  visible = true,
  reduced = false,
  manual = false,
  warmFrames = 20
let phi = ((270 - 115) * Math.PI) / 180,
  theta = 0.4,
  size = 360,
  drag: { id: number; x: number; y: number } | null = null
let resize: ResizeObserver | undefined,
  intersection: IntersectionObserver | undefined,
  motion: MediaQueryList
const markers = (): Marker[] =>
  props.places
    .filter((p) => p.latitude !== null && p.longitude !== null)
    .map((p, i) => ({
      location: [p.latitude!, p.longitude!],
      id: 'memory-city-' + i,
      size: p.key === props.selectedKey ? 0.1 : 0.065,
      color: p.key === props.selectedKey ? [1, 0.75, 0.45] : [0.25, 0.95, 0.68],
    }))
function wake() {
  if (error.value) return
  if (mounted && globe && !frame && visible && !document.hidden)
    frame = requestAnimationFrame(draw)
}
function draw() {
  frame = 0
  if (error.value) return
  if (!mounted || !globe || !visible || document.hidden) return
  let moving = false
  if (selected.value && !manual && !drag) {
    const focus = createFocusedGlobeView({
      latitude: selected.value.latitude!,
      longitude: selected.value.longitude!,
    })
    const nextPhi = reduced ? focus.phi : easeAngle(phi, focus.phi, 0.08)
    const nextTheta = reduced
      ? focus.theta
      : easeNumber(theta, focus.theta, 0.08)
    moving = Math.abs(nextPhi - phi) + Math.abs(nextTheta - theta) > 0.00001
    phi = nextPhi
    theta = nextTheta
  } else if (rotating.value && !drag && !reduced) {
    phi += 0.0025
    moving = true
  }
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  globe.update({
    phi,
    theta,
    width: Math.round(size * ratio),
    height: Math.round(size * ratio),
    markers: markers(),
  })
  if (moving || warmFrames-- > 0) wake()
}
function rotate(x: number, y: number) {
  phi += x
  theta = clamp(theta + y, -1.1, 1.1)
  manual = true
  rotating.value = false
  wake()
}
function toggleRotation() {
  rotating.value = !rotating.value
  manual = true
  wake()
}
function keyboard(event: KeyboardEvent) {
  const steps: Record<string, [number, number]> = {
    ArrowLeft: [-0.12, 0],
    ArrowRight: [0.12, 0],
    ArrowUp: [0, -0.08],
    ArrowDown: [0, 0.08],
  }
  if (steps[event.key]) {
    event.preventDefault()
    rotate(...steps[event.key])
  }
}
function pointerDown(event: PointerEvent) {
  canvas.value?.setPointerCapture(event.pointerId)
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY }
}
function pointerMove(event: PointerEvent) {
  if (!drag || drag.id !== event.pointerId) return
  rotate((event.clientX - drag.x) * 0.005, (event.clientY - drag.y) * 0.0035)
  drag.x = event.clientX
  drag.y = event.clientY
}
function pointerUp(event: PointerEvent) {
  if (canvas.value?.hasPointerCapture(event.pointerId))
    canvas.value.releasePointerCapture(event.pointerId)
  drag = null
  wake()
}
function lostContext() {
  error.value = '地球暂时无法显示，城市列表和回忆仍可使用。'
  cancelAnimationFrame(frame)
  frame = 0
}
function visibilityChanged() {
  wake()
}
function motionChanged() {
  reduced = motion.matches
  reducedMotion.value = reduced
  wake()
}
watch(
  () => props.selectedKey,
  () => {
    manual = false
    rotating.value = !props.selectedKey
    wake()
  },
)
watch(() => props.places, wake, { deep: true })
onMounted(async () => {
  mounted = true
  motion = window.matchMedia('(prefers-reduced-motion: reduce)')
  reduced = motion.matches
  reducedMotion.value = reduced
  motion.addEventListener('change', motionChanged)
  document.addEventListener('visibilitychange', visibilityChanged)
  try {
    const { default: createGlobe } = await import('cobe')
    if (!mounted || !canvas.value || !wrapper.value) return
    // COBE returns a no-op renderer when neither WebGL context is available.
    const contextOptions = {
      alpha: true,
      stencil: false,
      antialias: true,
      depth: false,
      preserveDrawingBuffer: false,
    }
    if (
      !canvas.value.getContext('webgl2', contextOptions) &&
      !canvas.value.getContext('webgl', contextOptions)
    )
      throw new Error('WebGL unavailable')
    size = Math.max(240, wrapper.value.clientWidth)
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    globe = createGlobe(canvas.value, {
      baseColor: [0.07, 0.17, 0.22],
      dark: 1,
      devicePixelRatio: ratio,
      diffuse: 1.1,
      glowColor: [0.21, 0.78, 0.86],
      height: size * ratio,
      mapBaseBrightness: 0.04,
      mapBrightness: 6,
      mapSamples: 16000,
      markerColor: [0.45, 0.95, 1],
      markerElevation: 0.04,
      markers: markers(),
      offset: [0, 0],
      opacity: 0.98,
      phi,
      scale: 1,
      theta,
      width: size * ratio,
    })
    ready.value = true
    resize = new ResizeObserver(() => {
      size = Math.max(240, wrapper.value?.clientWidth || 360)
      wake()
    })
    resize.observe(wrapper.value)
    intersection = new IntersectionObserver((entries) => {
      visible = entries[0]?.isIntersecting ?? true
      wake()
    })
    intersection.observe(wrapper.value)
    wake()
  } catch {
    error.value = '地球暂时无法显示，城市列表和回忆仍可使用。'
  }
})
onBeforeUnmount(() => {
  mounted = false
  cancelAnimationFrame(frame)
  resize?.disconnect()
  intersection?.disconnect()
  globe?.destroy()
  motion?.removeEventListener('change', motionChanged)
  document.removeEventListener('visibilitychange', visibilityChanged)
})
</script>

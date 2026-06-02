<template>
  <div v-if="state.phase !== 'idle'" class="bh-loader" role="status" aria-live="polite">
    <!-- CONSTRUCTION 海报 -->
    <div v-if="state.poster === 'construction'" ref="posterRef" class="bh-poster">
      <!-- 贯穿垂直轴线 -->
      <div ref="axisRef" class="bh-axis"></div>

      <!-- 左上：旋转黄圆 -->
      <div ref="circleRef" class="bh-circle"></div>

      <!-- 右上：corner tag -->
      <div ref="cornerRef" class="bh-corner">CONSTRUCTING · {{ stepIndexLabel }}</div>

      <!-- 中左：巨型天数 -->
      <div ref="megaRef" class="bh-mega">{{ ctx.days }}</div>

      <!-- 中右：Flip 源（红色 Hero 块） -->
      <div ref="heroRef" class="bh-hero" data-flip-source="loader-hero">
        <div class="bh-hero-cn">{{ ctx.city }}</div>
        <div class="bh-hero-en">{{ cityEn }}</div>
        <div class="bh-hero-line"></div>
        <div class="bh-hero-meta">{{ ctx.weatherSummary || 'YOUR TRIP' }}</div>
      </div>

      <!-- 左下：蓝三角 -->
      <div ref="triangleRef" class="bh-triangle"></div>

      <!-- 右下：黄方块（景点数） -->
      <div ref="squareRef" class="bh-square">
        <div class="bh-square-n">{{ ctx.attractionCount }}</div>
        <div class="bh-square-lbl">SPOTS</div>
      </div>

      <!-- 底部状态条 -->
      <div ref="statusRef" class="bh-status">
        <span class="bh-status-node">▶ {{ statusText }}</span>
        <div class="bh-status-bar"><div class="bh-status-fill" :style="{ width: progressPct + '%' }"></div></div>
        <span class="bh-status-pct">{{ progressPct }}%</span>
      </div>
    </div>

    <!-- REFINEMENT 海报：Phase B 实现，暂留占位 -->
    <div v-else class="bh-poster bh-poster--placeholder"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTripLoader, type LoaderContext } from '@/composables/useTripLoader'
import { labelForNode, progressForNode, CONSTRUCTION_STEPS, CONSTRUCTION_TOTAL } from './constructionSteps'

const { state } = useTripLoader()

// 元素 ref（GSAP Task 用得到，先声明）
const posterRef = ref<HTMLElement | null>(null)
const axisRef = ref<HTMLElement | null>(null)
const circleRef = ref<HTMLElement | null>(null)
const cornerRef = ref<HTMLElement | null>(null)
const megaRef = ref<HTMLElement | null>(null)
const heroRef = ref<HTMLElement | null>(null)
const triangleRef = ref<HTMLElement | null>(null)
const squareRef = ref<HTMLElement | null>(null)
const statusRef = ref<HTMLElement | null>(null)

// context 兜底，避免 null 解构崩溃
const ctx = computed<LoaderContext>(() => state.context ?? { city: '', days: 0, attractionCount: 0 })

const cityEn = computed(() => (ctx.value.city ? ctx.value.city.toUpperCase() : ''))

const nodeLabel = computed(() => labelForNode(state.currentNode))

// 状态条文案：优先用后端事件自带的 message（更具体），否则用节点标签
const statusText = computed(() => state.currentMessage || nodeLabel.value)

// 进度：优先用后端事件自带的 progress；缺失时才按节点序号兜底推算
const progressPct = computed(() => state.progress || progressForNode(state.currentNode))

const stepIndexLabel = computed(() => {
  const idx = CONSTRUCTION_STEPS.findIndex((s) => s.key === state.currentNode)
  const human = idx < 0 ? 0 : idx + 1
  return `${String(human).padStart(2, '0')}/${String(CONSTRUCTION_TOTAL).padStart(2, '0')}`
})
</script>

<style scoped>
.bh-loader {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: #faf8f3;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.bh-poster {
  position: relative;
  width: 100%;
  height: 100%;
  font-family: var(--font-family);
}

.bh-axis {
  position: absolute;
  left: 38%;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--foreground);
  opacity: 0.85;
}

.bh-circle {
  position: absolute;
  top: 5vh;
  left: 5vw;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--primary-yellow);
  border: 3px solid var(--foreground);
  box-shadow: 4px 4px 0 var(--foreground);
}
.bh-circle::after {
  content: '';
  position: absolute;
  inset: 9px;
  border-radius: 50%;
  border: 3px solid var(--foreground);
  border-right-color: transparent;
  animation: bh-spin 2.5s linear infinite;
}
@keyframes bh-spin { to { transform: rotate(360deg); } }

.bh-corner {
  position: absolute;
  top: 5vh;
  right: 5vw;
  background: var(--foreground);
  color: #fff;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

.bh-mega {
  position: absolute;
  left: 6vw;
  top: 50%;
  transform: translateY(-50%);
  font-size: clamp(160px, 32vw, 360px);
  line-height: 0.8;
  font-weight: 900;
  color: var(--foreground);
  letter-spacing: -0.06em;
}

.bh-hero {
  position: absolute;
  right: 8vw;
  top: 50%;
  transform: translateY(-50%);
  background: var(--primary-red);
  color: #fff;
  padding: 32px 44px 28px;
  border: 3px solid var(--foreground);
  box-shadow: 8px 8px 0 var(--foreground);
  min-width: 260px;
}
.bh-hero-cn { font-size: 52px; font-weight: 900; line-height: 1; letter-spacing: -0.02em; }
.bh-hero-en { font-size: 16px; letter-spacing: 0.42em; margin-top: 8px; opacity: 0.92; }
.bh-hero-line { height: 2px; background: #fff; opacity: 0.5; margin: 18px 0 14px; }
.bh-hero-meta { font-size: 13px; letter-spacing: 0.14em; font-weight: 700; }

.bh-triangle {
  position: absolute;
  bottom: 12vh;
  left: 8vw;
  width: 0;
  height: 0;
  border-left: 34px solid transparent;
  border-right: 34px solid transparent;
  border-bottom: 58px solid var(--primary-blue);
  transform: rotate(15deg);
  filter: drop-shadow(3px 3px 0 var(--foreground));
}

.bh-square {
  position: absolute;
  bottom: 12vh;
  right: 8vw;
  width: 104px;
  height: 104px;
  background: var(--primary-yellow);
  border: 3px solid var(--foreground);
  box-shadow: 4px 4px 0 var(--foreground);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.bh-square-n { font-size: 44px; font-weight: 900; line-height: 1; }
.bh-square-lbl { font-size: 10px; letter-spacing: 0.16em; margin-top: 3px; }

.bh-status {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--foreground);
  color: #fff;
  padding: 14px 5vw;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.12em;
}
.bh-status-bar { flex: 1; height: 4px; background: rgba(255,255,255,0.18); margin: 0 24px; }
.bh-status-fill { height: 100%; background: var(--primary-yellow); transition: width 0.4s ease; }

.bh-poster--placeholder { background: #faf8f3; }

@media (max-width: 640px) {
  .bh-hero { right: 5vw; padding: 20px 24px; min-width: 180px; }
  .bh-hero-cn { font-size: 34px; }
  .bh-circle { width: 52px; height: 52px; }
  .bh-square { width: 76px; height: 76px; }
}
</style>

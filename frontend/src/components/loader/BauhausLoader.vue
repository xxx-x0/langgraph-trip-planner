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
        <div class="bh-hero-meta">{{ ctx.metaLine || 'YOUR TRIP' }}</div>
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
import { computed, ref, watch, onUnmounted, nextTick } from 'vue'
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'
import { useTripLoader, type LoaderContext } from '@/composables/useTripLoader'
import { labelForNode, progressForNode, CONSTRUCTION_STEPS, CONSTRUCTION_TOTAL } from './constructionSteps'

const { state, setSteady, finishFlip } = useTripLoader()

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

// ===== GSAP 动画句柄与清理 =====
let entranceTl: gsap.core.Timeline | null = null
let steadyTl: gsap.core.Timeline | null = null
let splitInstance: SplitText | null = null
// 用 ReturnType 推导，避免依赖具体类型名（不同 gsap 版本类型导出名不一）
let mm: ReturnType<typeof gsap.matchMedia> | null = null
// Flip 收束安全兜底计时器：进入 flipping 后若超时仍未完成（如目标锚点意外缺失），强制复位
let flipSafety: number | null = null

function killAll() {
  entranceTl?.kill(); entranceTl = null
  steadyTl?.kill(); steadyTl = null
  splitInstance?.revert(); splitInstance = null
  mm?.revert(); mm = null
  if (flipSafety !== null) { window.clearTimeout(flipSafety); flipSafety = null }
}

onUnmounted(killAll)

// finishFlip 包装：清掉安全兜底计时器后再复位，避免兜底与正常完成重复触发
function doFinish() {
  if (flipSafety !== null) { window.clearTimeout(flipSafety); flipSafety = null }
  finishFlip()
}

// ===== 幕1-4：入场 + steady =====
function playEntrance() {
  killAll()
  if (!posterRef.value) return

  mm = gsap.matchMedia()

  mm.add('(prefers-reduced-motion: no-preference)', () => {
    const tl = gsap.timeline({
      defaults: { ease: 'power3.out' },
      onComplete: () => {
        setSteady()
        startSteady()
      },
    })
    entranceTl = tl

    // 幕1 SCAFFOLD：轴线划下
    tl.from(axisRef.value, { scaleY: 0, transformOrigin: 'top', duration: 0.6 })

    // 幕2 SHAPES IN：几何件入场
    tl.from(circleRef.value, { y: -120, opacity: 0, duration: 0.5, ease: 'back.out(1.7)' }, 0.5)
      .from(triangleRef.value, { rotation: -90, opacity: 0, duration: 0.5 }, 0.6)
      .from(squareRef.value, { x: 120, y: 120, opacity: 0, duration: 0.5 }, 0.7)
      .from(cornerRef.value, { opacity: 0, y: -10, duration: 0.4 }, 0.7)

    // 幕3 DATA REVEAL：大数字、红块、城市名、状态条
    tl.from(megaRef.value, { scale: 0.6, opacity: 0, duration: 0.6, ease: 'back.out(1.7)' }, 1.0)
      .from(heroRef.value, { x: 160, opacity: 0, duration: 0.6 }, 1.2)
      .from(statusRef.value, { y: 60, opacity: 0, duration: 0.5 }, 1.3)

    // 城市名字符级浮现
    if (heroRef.value) {
      const cnEl = heroRef.value.querySelector('.bh-hero-cn')
      if (cnEl) {
        splitInstance = SplitText.create(cnEl as HTMLElement, { type: 'chars' })
        tl.from(splitInstance.chars, { opacity: 0, y: 20, stagger: 0.05, duration: 0.4 }, 1.5)
      }
    }

    return () => { tl.kill(); entranceTl = null }
  })

  // reduced-motion：直接静态显示，立刻 steady
  mm.add('(prefers-reduced-motion: reduce)', () => {
    setSteady()
    return () => {}
  })
}

function startSteady() {
  if (!circleRef.value) return
  // 红块极轻微 breathing + 三角 floaty（仅 no-preference 下；reduce 模式不调用此函数路径动画）
  steadyTl = gsap.timeline({ repeat: -1, yoyo: true })
  steadyTl.to(heroRef.value, { scale: 1.005, duration: 3, ease: 'sine.inOut' })
    .to(triangleRef.value, { y: -8, duration: 2.4, ease: 'sine.inOut' }, 0)
}

// ===== 幕5：Flip 收束 =====
async function playFlipDismiss() {
  // 安全兜底：进入收束后若 2.5s 仍未完成（如目标锚点意外缺失），强制复位。
  // 正常链路 ≈ 装饰淡出(~0.54s)+Flip(0.7s)+淡出(0.2s)≈1.44s，2.5s 留足余量不误杀。
  flipSafety = window.setTimeout(doFinish, 2500)

  const dest = document.querySelector<HTMLElement>('[data-flip-id="loader-hero"]')

  // 找不到目标（异常）：直接结束
  if (!dest || !heroRef.value) {
    doFinish()
    return
  }

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (reduce) {
    // 降级：整屏淡出，不做位置变形
    gsap.to('.bh-loader', { opacity: 0, duration: 0.2, onComplete: doFinish })
    return
  }

  steadyTl?.kill(); steadyTl = null

  // 装饰元素先飞散/淡出
  const decor = [axisRef.value, circleRef.value, cornerRef.value, megaRef.value, triangleRef.value, squareRef.value, statusRef.value].filter(Boolean)
  await gsap.to(decor, { opacity: 0, scale: 0.9, duration: 0.3, stagger: 0.04, ease: 'power2.in' })

  // 让 loader 背景透出底层草稿页
  gsap.to('.bh-loader', { backgroundColor: 'rgba(250,248,243,0)', duration: 0.4 })

  // 把 loader 红块吸附到草稿页锚点（FLIP fit）
  Flip.fit(heroRef.value, dest, {
    duration: 0.7,
    ease: 'power3.inOut',
    absolute: true,
    scale: true,
    onComplete: () => {
      gsap.to(heroRef.value, {
        opacity: 0,
        duration: 0.2,
        onComplete: doFinish,
      })
    },
  })
}

// ===== phase 驱动动画 =====
watch(
  () => state.phase,
  async (phase, prev) => {
    if (phase === 'entering' && prev === 'idle') {
      await nextTick()
      playEntrance()
    } else if (phase === 'flipping') {
      await nextTick()
      playFlipDismiss()
    }
  },
)
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

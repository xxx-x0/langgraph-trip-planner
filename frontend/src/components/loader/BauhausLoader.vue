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

    <!-- REFINEMENT 海报：定稿打磨 / FINAL PROOF -->
    <div v-else ref="posterRef" class="bh-poster bh-poster--refine">
      <!-- ① 顶部红横幅（Flip 源） -->
      <div ref="bannerRef" class="pb-banner" data-flip-source="loader-hero">
        <span class="pb-banner-cn">{{ ctx.city }}</span>
        <span v-if="cityEnRefine" class="pb-banner-en">{{ cityEnRefine }} · {{ ctx.days }}日</span>
        <span class="pb-banner-badge">FINAL PROOF</span>
        <div class="pb-crop tl"></div>
        <div class="pb-crop tr"></div>
      </div>

      <!-- ② 左栏 日程校样台账 -->
      <div ref="ledgerRef" class="pb-ledger">
        <div class="pb-ledger-hd">DAYS · 日程校样</div>
        <div
          v-for="(num, i) in ledgerRows"
          :key="num"
          class="pb-dayrow"
          :style="{ '--d': rowDelay(i) }"
        >
          <span class="pb-dayrow-num">{{ String(num).padStart(2, '0') }}</span>
          <span class="pb-dayrow-ln"></span>
          <span class="pb-dayrow-chk"></span>
        </div>
        <div v-if="foldedCount > 0" class="pb-dayrow pb-dayrow--fold">
          <span class="pb-dayrow-num">…</span>
          <span class="pb-fold-label">+{{ foldedCount }}</span>
        </div>
      </div>

      <!-- 几何三件（Poster A 几何件的「归位」回响） -->
      <div ref="geoRef" class="pb-geo">
        <span class="pb-geo-tri"></span>
        <span class="pb-geo-cir"></span>
        <span class="pb-geo-sq"></span>
      </div>

      <!-- ③ 右栏 总体建议排版区 -->
      <div ref="spreadRef" class="pb-spread">
        <div class="pb-spread-hd">
          <span class="pb-spread-t">OVERVIEW · 总体建议</span>
          <span class="pb-mark">✳</span>
        </div>
        <div class="pb-lines">
          <div v-for="n in 6" :key="n" class="pb-line">
            <span class="pb-line-cap"></span>
            <span class="pb-line-bar"></span>
          </div>
        </div>
        <div class="pb-stamp">定稿中<small>FINALIZING</small></div>
        <div class="pb-sweep"></div>
      </div>

      <!-- ④ 底部黑色状态条 -->
      <div ref="statusRefB" class="pb-status">
        <span class="pb-status-lbl">▶ {{ statusTextRefine }}</span>
        <span class="pb-barber"></span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted, nextTick } from 'vue'
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'
import { useTripLoader, type LoaderContext } from '@/composables/useTripLoader'
import { labelForNode, progressForNode, CONSTRUCTION_STEPS, CONSTRUCTION_TOTAL } from './constructionSteps'
import { romanizeCity } from './cityRomanization'

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

// refinement 专用 ref（Flip 源 + 收束前淡出的装饰组）
const bannerRef = ref<HTMLElement | null>(null)   // 顶部红横幅 = Flip 源
const ledgerRef = ref<HTMLElement | null>(null)
const spreadRef = ref<HTMLElement | null>(null)
const statusRefB = ref<HTMLElement | null>(null)
const geoRef = ref<HTMLElement | null>(null)

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

// ===== REFINEMENT 海报数据 =====
const REFINE_CYCLE = 5      // 绿勾点亮循环周期（秒），与 pbCheck/pbTick 一致
const MAX_LEDGER_ROWS = 8   // 台账最多渲染行数，超出折叠

// refinement 英文副标题：命中映射显示，未命中（中文）返回 null → 模板省略英文行
const cityEnRefine = computed(() => romanizeCity(ctx.value.city))

// 状态条文案：绑定后端真实 SSE step 文案，缺省回退「定稿中…」
const statusTextRefine = computed(() => state.currentMessage || '定稿中…')

const dayCount = computed(() => Math.max(0, ctx.value.days || 0))
const shownDayCount = computed(() => Math.min(dayCount.value, MAX_LEDGER_ROWS))
// 渲染的台账行号 [1..shownDayCount]
const ledgerRows = computed(() =>
  Array.from({ length: shownDayCount.value }, (_, i) => i + 1),
)
// N>8 时折叠的剩余天数（用于「…+N」行）；N<=8 时为 0
const foldedCount = computed(() => Math.max(0, dayCount.value - MAX_LEDGER_ROWS))

// 绿勾逐行点亮的 animation-delay（按行号在一个循环周期内等分）
function rowDelay(i: number): string {
  const n = shownDayCount.value || 1
  return `${((i / n) * REFINE_CYCLE).toFixed(2)}s`
}

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
function playEntranceConstruction() {
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

// REFINEMENT 入场为纯 CSS（pbBannerIn 等 keyframes），GSAP 不参与；
// 这里只把状态机从 entering 推进到 steady。reduce 与 no-preference 共用本路径，
// 动/静差异完全由 CSS @media 决定。
function playEntranceRefinement() {
  setSteady()
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

  // 按海报选择 Flip 源（顶部红块）与收束前先淡出的装饰组
  const isRefine = state.poster === 'refinement'
  const src = isRefine ? bannerRef.value : heroRef.value
  const decor = (isRefine
    ? [ledgerRef.value, spreadRef.value, statusRefB.value, geoRef.value]
    : [axisRef.value, circleRef.value, cornerRef.value, megaRef.value, triangleRef.value, squareRef.value, statusRef.value]
  ).filter(Boolean)

  const dest = document.querySelector<HTMLElement>('[data-flip-id="loader-hero"]')

  // 找不到目标或源（异常）：直接结束
  if (!dest || !src) {
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
  await gsap.to(decor, { opacity: 0, scale: 0.9, duration: 0.3, stagger: 0.04, ease: 'power2.in' })

  // 让 loader 背景透出底层页面
  gsap.to('.bh-loader', { backgroundColor: 'rgba(250,248,243,0)', duration: 0.4 })

  // 把 loader 红块吸附到目标页锚点（FLIP fit）
  Flip.fit(src, dest, {
    duration: 0.7,
    ease: 'power3.inOut',
    absolute: true,
    scale: true,
    onComplete: () => {
      gsap.to(src, {
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
      if (state.poster === 'refinement') playEntranceRefinement()
      else playEntranceConstruction()
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
  /* Poster B 扩展色：绿（精修/通过）、橙（旋转校样标）、奶油（排版区底） */
  --bh-green: #0E9F6E;
  --bh-orange: #E8772E;
  --bh-cream: #f1ece0;
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

/* ===== REFINEMENT (Poster B) ===== */
.bh-poster--refine { background: #faf8f3; }

/* ① 顶部红横幅（Flip 源） */
.pb-banner {
  position: absolute; top: 0; left: 0; right: 0; height: 17%;
  background: var(--primary-red); border-bottom: 4px solid var(--foreground);
  color: #fff; display: flex; align-items: center; gap: 18px; padding: 0 5vw; z-index: 6;
}
.pb-banner-cn { font-size: clamp(28px, 4vw, 56px); font-weight: 900; line-height: 1; letter-spacing: -0.02em; }
.pb-banner-en { font-size: clamp(11px, 1vw, 15px); letter-spacing: 0.4em; opacity: 0.92; }
.pb-banner-badge {
  margin-left: auto; font-size: clamp(10px, 0.9vw, 13px); font-weight: 800; letter-spacing: 0.18em;
  border: 2px solid #fff; padding: 4px 12px;
}
.pb-crop { position: absolute; width: 16px; height: 16px; z-index: 7; }
.pb-crop::before, .pb-crop::after { content: ''; position: absolute; background: var(--foreground); }
.pb-crop::before { width: 16px; height: 2px; top: 7px; }
.pb-crop::after { width: 2px; height: 16px; left: 7px; }
.pb-crop.tl { top: 4px; left: 4px; }
.pb-crop.tr { top: 4px; right: 4px; }

/* ② 左栏 日程校样台账 */
.pb-ledger {
  position: absolute; left: 0; top: 17%; width: 37%; bottom: 12%;
  border-right: 3px solid var(--foreground); padding: 2vh 2vw 0; box-sizing: border-box; overflow: hidden;
}
.pb-ledger-hd {
  font-size: clamp(10px, 1vw, 14px); font-weight: 800; letter-spacing: 0.2em; color: var(--foreground);
  border-bottom: 2px solid var(--foreground); padding-bottom: 8px; margin-bottom: 2vh;
}
.pb-dayrow { display: flex; align-items: center; gap: 12px; margin-bottom: clamp(6px, 1.6vh, 16px); }
.pb-dayrow-num { font-size: clamp(14px, 1.7vw, 22px); font-weight: 900; width: 34px; color: var(--foreground); }
.pb-dayrow-ln { flex: 1; height: 8px; background: rgba(18, 18, 18, .12); }
.pb-dayrow-chk {
  position: relative; width: 20px; height: 20px; border: 2px solid var(--foreground); background: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 13px; color: #fff; font-weight: 900; flex: 0 0 auto;
}
.pb-dayrow-chk::after { content: '✓'; position: absolute; opacity: 0; }
.pb-dayrow--fold .pb-dayrow-num { width: auto; }
.pb-fold-label { font-size: clamp(12px, 1.3vw, 16px); font-weight: 800; letter-spacing: 0.1em; color: var(--foreground); opacity: 0.7; }

/* 几何三件 */
.pb-geo { position: absolute; left: 2vw; bottom: 13.5%; display: flex; align-items: flex-end; gap: 14px; z-index: 4; }
.pb-geo-tri {
  width: 0; height: 0; border-left: 15px solid transparent; border-right: 15px solid transparent;
  border-bottom: 26px solid var(--primary-blue); filter: drop-shadow(2px 2px 0 var(--foreground));
}
.pb-geo-cir { width: 26px; height: 26px; border-radius: 50%; background: var(--bh-green); border: 2px solid var(--foreground); box-shadow: 2px 2px 0 var(--foreground); }
.pb-geo-sq { width: 24px; height: 24px; background: var(--primary-yellow); border: 2px solid var(--foreground); box-shadow: 2px 2px 0 var(--foreground); }

/* ③ 右栏 总体建议排版区 */
.pb-spread { position: absolute; left: 37%; right: 0; top: 17%; bottom: 12%; background: var(--bh-cream); overflow: hidden; }
.pb-spread-hd { display: flex; align-items: center; justify-content: space-between; padding: 2vh 2vw 1vh; }
.pb-spread-t { font-size: clamp(10px, 1vw, 14px); font-weight: 800; letter-spacing: 0.2em; color: var(--foreground); }
.pb-mark { width: 28px; height: 28px; color: var(--bh-orange); font-size: 28px; line-height: 28px; text-align: center; font-weight: 900; }
.pb-lines { padding: 1vh 2vw; }
.pb-line { height: 11px; margin-bottom: clamp(6px, 1.6vh, 14px); display: flex; align-items: center; gap: 10px; }
.pb-line-cap { width: 16px; height: 11px; flex: 0 0 auto; }
.pb-line-bar { height: 9px; background: rgba(18, 18, 18, .16); }
.pb-line:nth-child(1) .pb-line-cap { background: var(--foreground); } .pb-line:nth-child(1) .pb-line-bar { width: 88%; }
.pb-line:nth-child(2) .pb-line-cap { background: var(--primary-blue); } .pb-line:nth-child(2) .pb-line-bar { width: 70%; }
.pb-line:nth-child(3) .pb-line-cap { background: var(--bh-green); } .pb-line:nth-child(3) .pb-line-bar { width: 80%; }
.pb-line:nth-child(4) .pb-line-cap { background: var(--primary-yellow); } .pb-line:nth-child(4) .pb-line-bar { width: 62%; }
.pb-line:nth-child(5) .pb-line-cap { background: var(--foreground); } .pb-line:nth-child(5) .pb-line-bar { width: 76%; }
.pb-line:nth-child(6) .pb-line-cap { background: var(--primary-blue); } .pb-line:nth-child(6) .pb-line-bar { width: 54%; }
.pb-sweep {
  position: absolute; top: 0; bottom: 0; width: 42%; left: -55%;
  background: linear-gradient(100deg, transparent, rgba(255, 255, 255, .9) 46%, rgba(14, 159, 110, .35) 56%, transparent);
  transform: skewX(-12deg); pointer-events: none; z-index: 3;
}
.pb-stamp {
  position: absolute; right: 8%; bottom: 16%; transform: rotate(-9deg);
  border: 3px solid var(--bh-green); color: var(--bh-green); padding: 6px 14px;
  font-size: clamp(13px, 1.4vw, 18px); font-weight: 900; letter-spacing: 0.12em; opacity: 0.85; z-index: 4;
}
.pb-stamp small { display: block; font-size: 0.6em; letter-spacing: 0.3em; text-align: center; }

/* ④ 底部黑色状态条 */
.pb-status {
  position: absolute; left: 0; right: 0; bottom: 0; height: 12%; background: var(--foreground); color: #fff;
  display: flex; align-items: center; padding: 0 5vw; gap: 18px; z-index: 6;
}
.pb-status-lbl { font-size: clamp(12px, 1.2vw, 16px); font-weight: 700; letter-spacing: 0.12em; white-space: nowrap; }
.pb-barber {
  flex: 1; height: 10px;
  background: repeating-linear-gradient(45deg, var(--primary-yellow) 0 9px, transparent 9px 18px);
  background-size: 25px 100%; opacity: 0.85;
}

/* 循环 / 入场动画：仅在允许动效时启用（reduce 用户看到静止海报） */
@media (prefers-reduced-motion: no-preference) {
  .pb-banner { animation: pbBannerIn 0.7s cubic-bezier(.16, 1, .3, 1) both; }
  .pb-dayrow-chk { animation: pbCheck 5s infinite; animation-delay: var(--d, 0s); }
  .pb-dayrow-chk::after { animation: pbTick 5s infinite; animation-delay: var(--d, 0s); }
  .pb-mark { animation: pbSpin 6s linear infinite; }
  .pb-sweep { animation: pbSweep 2.4s infinite linear; }
  .pb-stamp { animation: pbStamp 5s infinite; }
  .pb-barber { animation: pbBarber 0.7s infinite linear; }
}

@keyframes pbBannerIn { from { transform: translateY(-100%); } to { transform: translateY(0); } }
@keyframes pbCheck { 0%, 8% { background: #fff; } 14%, 84% { background: var(--bh-green); } 90%, 100% { background: #fff; } }
@keyframes pbTick { 0%, 10% { opacity: 0; } 16%, 84% { opacity: 1; } 90%, 100% { opacity: 0; } }
@keyframes pbSpin { to { transform: rotate(360deg); } }
@keyframes pbSweep { 0% { left: -55%; } 100% { left: 115%; } }
@keyframes pbStamp { 0%, 100% { transform: rotate(-9deg) scale(1); } 50% { transform: rotate(-9deg) scale(1.05); } }
@keyframes pbBarber { from { background-position: 0 0; } to { background-position: 25px 0; } }

</style>

<template>
  <div class="result-hero" :style="heroStyle">
    <div class="hero-overlay"></div>
    <div class="hero-inner">
      <div class="hero-top">
        <button class="hero-back" @click="$emit('goBack')">
          <span class="back-arrow">←</span>
          <span class="back-text">返回</span>
        </button>
        <div class="hero-actions">
          <a-button v-if="!isSaved" @click="$emit('save')" type="primary" ghost :loading="savingTrip" class="hero-btn">
            保存行程
          </a-button>
          <a-button v-else type="default" disabled class="hero-btn">已保存</a-button>
          <a-button v-if="!editMode" @click="$emit('edit')" type="default" ghost class="hero-btn">
            编辑行程
          </a-button>
          <template v-else>
            <a-button @click="$emit('saveChanges')" type="primary" class="hero-btn">保存修改</a-button>
            <a-button @click="$emit('cancelEdit')" type="default" ghost class="hero-btn">取消</a-button>
          </template>
          <a-dropdown v-if="!editMode">
            <template #overlay>
              <a-menu>
                <a-menu-item key="image" @click="$emit('exportImage')">导出为图片</a-menu-item>
                <a-menu-item key="pdf" @click="$emit('exportPdf')">导出为PDF</a-menu-item>
              </a-menu>
            </template>
            <a-button type="default" ghost class="hero-btn">导出 <DownOutlined /></a-button>
          </a-dropdown>
        </div>
      </div>
      <div class="hero-content">
        <h1 class="hero-title">{{ heroTitle }}</h1>
        <div class="hero-tags">
          <span class="hero-tag">📅 {{ tripPlan.start_date }} 出发</span>
          <span class="hero-tag-divider">|</span>
          <span class="hero-tag">💰 预估 ¥{{ totalBudget }}</span>
          <span class="hero-tag-divider">|</span>
          <span class="hero-tag">☀️ {{ weatherSummary }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { DownOutlined } from '@ant-design/icons-vue'
import type { TripPlan } from '@/types'

const props = defineProps<{
  tripPlan: TripPlan
  isSaved: boolean
  savingTrip: boolean
  editMode: boolean
}>()

defineEmits<{
  goBack: []
  save: []
  edit: []
  saveChanges: []
  cancelEdit: []
  exportImage: []
  exportPdf: []
}>()

const cityPhoto = ref('')

const nights = computed(() => {
  const days = props.tripPlan.days?.length || 1
  return days > 1 ? days - 1 : 0
})

const heroTitle = computed(() => {
  const city = props.tripPlan.city
  const days = props.tripPlan.days?.length || 1
  const duration = nights.value > 0 ? `${days}天${nights.value}晚` : `${days}天`
  const tagline = props.tripPlan.trip_tagline
  return tagline ? `${city} ${duration} ${tagline}` : `${city} ${duration}`
})

const totalBudget = computed(() => {
  return props.tripPlan.budget?.total || '—'
})

const weatherSummary = computed(() => {
  if (props.tripPlan.weather_summary) return props.tripPlan.weather_summary
  if (props.tripPlan.weather_info?.length) {
    return props.tripPlan.weather_info[0].day_weather || '暂无天气信息'
  }
  return '暂无天气信息'
})

const heroStyle = computed(() => {
  if (cityPhoto.value) {
    return { backgroundImage: `url(${cityPhoto.value})` }
  }
  return {}
})

onMounted(async () => {
  try {
    const res = await fetch(`/api/poi/photo?name=${encodeURIComponent(props.tripPlan.city + ' city skyline')}`)
    const data = await res.json()
    if (data.success && data.data?.photo_url) {
      cityPhoto.value = data.data.photo_url
    }
  } catch {
    // fallback to gradient
  }
})
</script>

<style scoped>
.result-hero {
  position: relative;
  overflow: hidden;
  min-height: 320px;
  display: flex;
  align-items: stretch;
  background: var(--color-bg-hero);
  background-size: cover;
  background-position: center;
  transition: background-image 0.6s ease;
}

.hero-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(0, 0, 0, 0.35) 0%,
    rgba(0, 0, 0, 0.25) 40%,
    rgba(0, 0, 0, 0.55) 100%
  );
  z-index: 0;
}

.hero-inner {
  max-width: var(--content-max-width);
  margin: 0 auto;
  position: relative;
  z-index: 1;
  width: 100%;
  padding: var(--space-8) var(--space-6) var(--space-10);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-8);
}

.hero-back {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-pill);
  padding: var(--space-2) var(--space-4);
  color: rgba(255, 255, 255, 0.9);
  font-size: var(--font-size-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  backdrop-filter: blur(8px);
}

.hero-back:hover {
  background: rgba(255, 255, 255, 0.25);
  color: #fff;
}

.back-arrow {
  font-size: var(--font-size-lg);
}

.hero-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.hero-btn {
  border-radius: var(--radius-pill) !important;
  border-color: rgba(255, 255, 255, 0.3) !important;
  color: rgba(255, 255, 255, 0.9) !important;
  backdrop-filter: blur(8px);
}

.hero-btn:hover {
  border-color: rgba(255, 255, 255, 0.5) !important;
  color: #fff !important;
  background: rgba(255, 255, 255, 0.15) !important;
}

.hero-content {
  text-align: center;
}

.hero-title {
  font-size: clamp(1.8rem, 4vw, 3rem);
  font-weight: var(--font-weight-bold);
  color: #fff;
  margin: 0 0 var(--space-5);
  letter-spacing: 0.03em;
  text-shadow: 0 2px 24px rgba(0, 0, 0, 0.4);
  animation: fadeInUp var(--transition-normal);
  line-height: 1.3;
}

.hero-tags {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  animation: fadeInUp var(--transition-normal);
  animation-delay: 0.15s;
  animation-fill-mode: both;
}

.hero-tag {
  display: inline-flex;
  align-items: center;
  padding: var(--space-1) var(--space-3);
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: var(--radius-pill);
  color: rgba(255, 255, 255, 0.95);
  font-size: var(--font-size-md);
  backdrop-filter: blur(10px);
  white-space: nowrap;
}

.hero-tag-divider {
  color: rgba(255, 255, 255, 0.4);
  font-size: var(--font-size-md);
}

@media (max-width: 768px) {
  .result-hero {
    min-height: 260px;
  }
  .hero-inner {
    padding: var(--space-5) var(--space-4) var(--space-8);
  }
  .hero-top {
    flex-direction: column;
    gap: var(--space-3);
    align-items: flex-start;
  }
  .hero-actions {
    flex-wrap: wrap;
  }
  .hero-title {
    font-size: clamp(1.4rem, 5vw, 2rem);
  }
  .hero-tags {
    gap: var(--space-2);
  }
  .hero-tag-divider {
    display: none;
  }
  .back-text {
    display: none;
  }
}
</style>

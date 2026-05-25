<template>
  <div class="bauhaus-home">
    <!-- 蓝色背景 Hero 区域 -->
    <div class="hero-section">
      <!-- 几何装饰 -->
      <GeometricDecoration
        shape="circle"
        color="yellow"
        :size="80"
        class="decoration decoration-1"
      />
      <GeometricDecoration
        shape="square"
        color="red"
        :size="60"
        class="decoration decoration-2"
      />
      <GeometricDecoration
        shape="circle"
        color="yellow"
        :size="40"
        class="decoration decoration-3"
      />

      <!-- Hero 内容 -->
      <div class="hero-content">
        <h1 class="bauhaus-title bauhaus-title-xl hero-title">
          智能旅行助手
        </h1>
        <p class="hero-subtitle">
          基于 AI 的个性化旅行规划，让每一次出行都完美无忧
        </p>

        <!-- 热门城市快选 -->
        <div class="hot-cities">
          <span class="hot-label">🔥 热门目的地</span>
          <div class="city-pills">
            <button
              v-for="city in hotCities"
              :key="city.name"
              class="city-pill"
              :class="{ active: formData.city === city.name }"
              @click="selectCity(city.name)"
            >
              {{ city.emoji }} {{ city.name }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 表单区域 -->
    <div class="form-section">
      <a-form
        :model="formData"
        layout="vertical"
        @finish="handleSubmit"
      >
        <!-- Form cards will be added in subsequent tasks -->
      </a-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { TripFormData } from '@/types'
import type { Dayjs } from 'dayjs'
import GeometricDecoration from '@/components/bauhaus/GeometricDecoration.vue'

const router = useRouter()

const hotCities = [
  { name: '北京', emoji: '🏯' },
  { name: '上海', emoji: '🌃' },
  { name: '成都', emoji: '🐼' },
  { name: '西安', emoji: '🏛️' },
  { name: '杭州', emoji: '🌸' },
  { name: '三亚', emoji: '🏖️' },
  { name: '重庆', emoji: '🌶️' },
  { name: '丽江', emoji: '🏔️' },
]

const formData = reactive<{
  city: string
  start_date: Dayjs | undefined
  end_date: Dayjs | undefined
  travel_days: number
  transportation: string
  accommodation: string
  food_preference: string
  preferences: string[]
  free_text_input: string
  default_day_start_time: string
  budget?: number
  companions: { count: number; type: string }
}>({
  city: '',
  start_date: undefined,
  end_date: undefined,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  food_preference: '本地特色',
  preferences: [],
  free_text_input: '',
  default_day_start_time: '08:00',
  budget: undefined,
  companions: { count: 1, type: 'solo' }
})

const selectCity = (city: string) => {
  formData.city = city
}

watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, 'day') + 1
    if (days > 0 && days <= 30) {
      formData.travel_days = days
    } else if (days > 30) {
      message.warning('旅行天数不能超过30天')
      formData.end_date = undefined
    } else {
      message.warning('结束日期不能早于开始日期')
      formData.end_date = undefined
    }
  }
})

const handleSubmit = () => {
  if (!formData.start_date || !formData.end_date) {
    message.error('请选择日期')
    return
  }

  const requestData: TripFormData = {
    city: formData.city,
    start_date: formData.start_date.format('YYYY-MM-DD'),
    end_date: formData.end_date.format('YYYY-MM-DD'),
    travel_days: formData.travel_days,
    transportation: formData.transportation,
    accommodation: formData.accommodation,
    food_preference: formData.food_preference,
    preferences: formData.preferences,
    free_text_input: formData.free_text_input,
    default_day_start_time: formData.default_day_start_time,
    budget: formData.budget || undefined,
    companions: formData.companions,
  }

  sessionStorage.setItem('tripFormData', JSON.stringify(requestData))
  router.push('/discover')
}
</script>

<style scoped>
.bauhaus-home {
  min-height: 100vh;
  background: var(--primary-blue);
  padding: var(--space-8) var(--space-4);
}

/* Hero 区域 */
.hero-section {
  position: relative;
  max-width: 1200px;
  margin: 0 auto var(--space-16);
  text-align: center;
}

/* 几何装饰定位 */
.decoration {
  position: absolute;
  z-index: 1;
}

.decoration-1 {
  top: -40px;
  left: 10%;
}

.decoration-2 {
  top: 100px;
  right: 15%;
}

.decoration-3 {
  bottom: -20px;
  left: 20%;
}

/* Hero 内容 */
.hero-content {
  position: relative;
  z-index: 2;
}

.hero-title {
  color: var(--white);
  margin-bottom: var(--space-4);
  text-shadow: 4px 4px 0px rgba(0, 0, 0, 0.2);
}

.hero-subtitle {
  color: var(--white);
  font-size: var(--text-xl);
  font-weight: var(--font-medium);
  margin-bottom: var(--space-8);
  opacity: 0.95;
}

/* 热门城市 */
.hot-cities {
  display: inline-block;
  background: rgba(255, 255, 255, 0.1);
  border: var(--border-main) solid var(--white);
  padding: var(--space-4);
  backdrop-filter: blur(10px);
}

.hot-label {
  color: var(--white);
  font-weight: var(--font-bold);
  font-size: var(--text-base);
  display: block;
  margin-bottom: var(--space-3);
}

.city-pills {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.city-pill {
  background: var(--white);
  color: var(--foreground);
  border: var(--border-2) solid var(--foreground);
  padding: 8px 16px;
  font-weight: var(--font-bold);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.city-pill:hover {
  background: var(--primary-yellow);
  transform: translateY(-2px);
}

.city-pill.active {
  background: var(--primary-yellow);
  box-shadow: var(--shadow-md);
}

/* 表单区域 */
.form-section {
  max-width: 900px;
  margin: 0 auto;
}

/* 移动端适配 */
@media (max-width: 640px) {
  .bauhaus-home {
    padding: var(--space-4) var(--space-2);
  }

  .hero-title {
    font-size: var(--text-4xl) !important;
  }

  .hero-subtitle {
    font-size: var(--text-base);
  }

  .decoration {
    display: none;
  }

  .city-pills {
    justify-content: center;
  }
}
</style>

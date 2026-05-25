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
        <!-- 卡片 1: 目的地与日期 - 黄色背景 -->
        <div class="form-card card-yellow">
          <div class="card-decoration decoration-circle decoration-red"></div>
          <h3 class="card-title">📍 目的地与日期</h3>

          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
                <template #label>
                  <span class="form-label">目的地城市</span>
                </template>
                <a-input
                  v-model:value="formData.city"
                  placeholder="例如: 北京"
                  size="large"
                />
              </a-form-item>
            </a-col>

            <a-col :xs="12" :md="6">
              <a-form-item name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
                <template #label>
                  <span class="form-label">开始日期</span>
                </template>
                <a-date-picker
                  v-model:value="formData.start_date"
                  style="width: 100%"
                  size="large"
                />
              </a-form-item>
            </a-col>

            <a-col :xs="12" :md="6">
              <a-form-item name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
                <template #label>
                  <span class="form-label">结束日期</span>
                </template>
                <a-date-picker
                  v-model:value="formData.end_date"
                  style="width: 100%"
                  size="large"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <div class="days-display">
            <span class="days-label">旅行天数：</span>
            <span class="days-value">{{ formData.travel_days }}</span>
            <span class="days-unit">天</span>
          </div>
        </div>

        <!-- 卡片 2: 偏好设置 - 白色背景 -->
        <div class="form-card">
          <div class="card-decoration decoration-square decoration-blue"></div>
          <h3 class="card-title">⚙️ 偏好设置</h3>

          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item name="transportation">
                <template #label>
                  <span class="form-label">交通方式</span>
                </template>
                <a-select
                  v-model:value="formData.transportation"
                  size="large"
                >
                  <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                  <a-select-option value="自驾">🚗 自驾</a-select-option>
                  <a-select-option value="步行">🚶 步行</a-select-option>
                  <a-select-option value="混合">🔀 混合</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>

            <a-col :xs="24" :md="12">
              <a-form-item name="accommodation">
                <template #label>
                  <span class="form-label">住宿偏好</span>
                </template>
                <a-select
                  v-model:value="formData.accommodation"
                  size="large"
                >
                  <a-select-option value="经济型酒店">💰 经济型酒店</a-select-option>
                  <a-select-option value="舒适型酒店">🏨 舒适型酒店</a-select-option>
                  <a-select-option value="豪华酒店">⭐ 豪华酒店</a-select-option>
                  <a-select-option value="民宿">🏡 民宿</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>

            <a-col :xs="24" :md="12">
              <a-form-item name="food_preference">
                <template #label>
                  <span class="form-label">美食偏好</span>
                </template>
                <a-select
                  v-model:value="formData.food_preference"
                  size="large"
                >
                  <a-select-option value="本地特色">🍜 本地特色</a-select-option>
                  <a-select-option value="川菜">🌶️ 川菜</a-select-option>
                  <a-select-option value="粤菜">🥘 粤菜</a-select-option>
                  <a-select-option value="日料">🍣 日料</a-select-option>
                  <a-select-option value="西餐">🥩 西餐</a-select-option>
                  <a-select-option value="火锅">🍲 火锅</a-select-option>
                  <a-select-option value="烧烤">🍢 烧烤</a-select-option>
                  <a-select-option value="海鲜">🦐 海鲜</a-select-option>
                  <a-select-option value="小吃">🥟 小吃</a-select-option>
                  <a-select-option value="无特殊要求">❌ 无特殊要求</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>

            <a-col :xs="24" :md="12">
              <a-form-item name="default_day_start_time">
                <template #label>
                  <span class="form-label">每日开始时间</span>
                </template>
                <a-input
                  v-model:value="formData.default_day_start_time"
                  type="time"
                  size="large"
                />
              </a-form-item>
            </a-col>

            <a-col :xs="24">
              <a-form-item name="preferences">
                <template #label>
                  <span class="form-label">感兴趣的景点类型（可选）</span>
                </template>
                <a-checkbox-group v-model:value="formData.preferences" class="preference-group">
                  <a-checkbox value="历史文化">🏛️ 历史文化</a-checkbox>
                  <a-checkbox value="自然风光">🏞️ 自然风光</a-checkbox>
                  <a-checkbox value="都市地标">🌃 都市地标</a-checkbox>
                  <a-checkbox value="购物">🛍️ 购物</a-checkbox>
                  <a-checkbox value="艺术">🎨 艺术</a-checkbox>
                  <a-checkbox value="休闲">☕ 休闲</a-checkbox>
                  <a-checkbox value="夜生活">🌙 夜生活</a-checkbox>
                  <a-checkbox value="户外徒步">🥾 户外徒步</a-checkbox>
                  <a-checkbox value="祈福朝圣">🛐 祈福朝圣</a-checkbox>
                </a-checkbox-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 卡片 3: 预算与同伴 - 红色背景 -->
        <div class="form-card card-red">
          <div class="card-decoration decoration-circle decoration-yellow"></div>
          <h3 class="card-title">💰 预算与同伴</h3>

          <a-row :gutter="16">
            <a-col :xs="24" :md="8">
              <a-form-item name="budget">
                <template #label>
                  <span class="form-label">预算上限（元）</span>
                </template>
                <a-input-number
                  v-model:value="formData.budget"
                  :min="0"
                  :step="100"
                  style="width: 100%"
                  size="large"
                  placeholder="不限预算"
                />
              </a-form-item>
            </a-col>

            <a-col :xs="12" :md="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">出行人数</span>
                </template>
                <a-input-number
                  v-model:value="formData.companions!.count"
                  :min="1"
                  :max="20"
                  style="width: 100%"
                  size="large"
                />
              </a-form-item>
            </a-col>

            <a-col :xs="12" :md="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">同伴类型</span>
                </template>
                <a-select
                  v-model:value="formData.companions!.type"
                  size="large"
                >
                  <a-select-option value="solo">🧑 独自</a-select-option>
                  <a-select-option value="couple">💑 情侣</a-select-option>
                  <a-select-option value="family">👨‍👩‍👧‍👦 家庭</a-select-option>
                  <a-select-option value="friends">👥 朋友</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 卡片 4: 额外要求 - 白色背景 -->
        <div class="form-card">
          <div class="card-decoration decoration-square decoration-red"></div>
          <h3 class="card-title">💬 额外要求</h3>

          <a-form-item name="free_text_input">
            <a-textarea
              v-model:value="formData.free_text_input"
              placeholder="告诉我们您的特殊需求或偏好..."
              :rows="4"
              size="large"
            />
          </a-form-item>
        </div>

        <!-- 提交按钮 -->
        <div class="submit-section">
          <button
            type="submit"
            class="bauhaus-btn bauhaus-btn-yellow bauhaus-btn-square submit-btn"
          >
            🚀 开始探索景点
          </button>
        </div>
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

/* 表单卡片基础样式 */
.form-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  padding: var(--space-6);
  margin-bottom: var(--space-6);
  position: relative;
}

/* 黄色卡片 */
.card-yellow {
  background: var(--primary-yellow);
}

/* 红色卡片 */
.card-red {
  background: var(--primary-red);
}

.card-red .card-title,
.card-red .form-label {
  color: var(--white);
}

/* 卡片装饰 */
.card-decoration {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
}

.decoration-circle {
  border-radius: var(--radius-full);
}

.decoration-square {
  border-radius: var(--radius-none);
}

.decoration-red {
  background: var(--primary-red);
}

.decoration-blue {
  background: var(--primary-blue);
}

.decoration-yellow {
  background: var(--primary-yellow);
}

/* 卡片标题 */
.card-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-4);
  color: var(--foreground);
}

/* 表单标签 */
.form-label {
  font-weight: var(--font-bold);
  font-size: var(--text-base);
  color: var(--foreground);
}

/* 统一所有输入框和选择框的高度 */
:deep(.ant-input-lg),
:deep(.ant-select-lg .ant-select-selector),
:deep(.ant-picker-large),
:deep(.ant-input-number-lg) {
  min-height: 40px !important;
  height: 40px !important;
}

:deep(.ant-input[type="time"]) {
  min-height: 40px !important;
  height: 40px !important;
}

/* 天数显示 */
.days-display {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  padding: var(--space-3);
  text-align: center;
  margin-top: var(--space-4);
}

.days-label {
  font-weight: var(--font-bold);
  margin-right: var(--space-2);
}

.days-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-black);
  color: var(--primary-blue);
  margin: 0 var(--space-1);
}

.days-unit {
  font-weight: var(--font-bold);
}

/* 偏好选择组 */
.preference-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* 提交按钮区域 */
.submit-section {
  text-align: center;
  margin-top: var(--space-8);
}

.submit-btn {
  min-width: 300px;
  padding: 16px 48px;
  font-size: var(--text-lg);
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

  .form-card {
    padding: var(--space-4);
    margin-bottom: var(--space-4);
  }

  .card-title {
    font-size: var(--text-lg);
  }

  .submit-btn {
    min-width: 100%;
  }
}
</style>

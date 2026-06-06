<template>
  <div class="home-container">
    <div class="hero-section">
      <div class="hero-bg">
        <div class="hero-glow hero-glow-1"></div>
        <div class="hero-glow hero-glow-2"></div>
        <div class="hero-glow hero-glow-3"></div>
        <div class="hero-pattern"></div>
      </div>
      <div class="hero-content">
        <div class="hero-badge animate-fade-in-up">✨ AI 驱动</div>
        <h1 class="hero-title animate-fade-in-up stagger-1">智能旅行助手</h1>
        <p class="hero-subtitle animate-fade-in-up stagger-2">基于AI的个性化旅行规划，让每一次出行都完美无忧</p>
        <div class="hot-cities animate-fade-in-up stagger-3">
          <span class="hot-label">🔥 热门目的地</span>
          <div class="city-pills">
            <button
              v-for="city in hotCities"
              :key="city.name"
              class="city-pill"
              :class="{ active: formData.city === city.name }"
              @click="selectCity(city.name)"
            >
              <span class="city-emoji">{{ city.emoji }}</span>
              <span class="city-name">{{ city.name }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section-wrapper">
      <a-card class="form-card" :bordered="false">
        <a-form
          :model="formData"
          layout="vertical"
          @finish="handleSubmit"
        >
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">📍</span>
              <span class="section-title">目的地与日期</span>
            </div>

            <a-row :gutter="24">
              <a-col :xs="24" :sm="24" :md="8">
                <a-form-item name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
                  <template #label>
                    <span class="form-label">目的地城市</span>
                  </template>
                  <a-input
                    v-model:value="formData.city"
                    placeholder="例如: 北京"
                    size="large"
                    class="custom-input"
                  >
                    <template #prefix>
                      <span class="input-prefix-icon">🏙️</span>
                    </template>
                  </a-input>
                </a-form-item>
              </a-col>
              <a-col :xs="12" :sm="12" :md="6">
                <a-form-item name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
                  <template #label>
                    <span class="form-label">开始日期</span>
                  </template>
                  <a-date-picker
                    v-model:value="formData.start_date"
                    style="width: 100%"
                    size="large"
                    class="custom-input"
                    placeholder="选择日期"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="12" :sm="12" :md="6">
                <a-form-item name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
                  <template #label>
                    <span class="form-label">结束日期</span>
                  </template>
                  <a-date-picker
                    v-model:value="formData.end_date"
                    style="width: 100%"
                    size="large"
                    class="custom-input"
                    placeholder="选择日期"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :sm="24" :md="4">
                <a-form-item>
                  <template #label>
                    <span class="form-label">旅行天数</span>
                  </template>
                  <div class="days-display">
                    <span class="days-value">{{ formData.travel_days }}</span>
                    <span class="days-unit">天</span>
                  </div>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">⚙️</span>
              <span class="section-title">偏好设置</span>
            </div>

            <a-row :gutter="24">
              <a-col :xs="24" :sm="12" :md="8">
                <a-form-item name="transportation">
                  <template #label>
                    <span class="form-label">交通方式</span>
                  </template>
                  <a-select v-model:value="formData.transportation" size="large" class="custom-select">
                    <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                    <a-select-option value="自驾">🚗 自驾</a-select-option>
                    <a-select-option value="步行">🚶 步行</a-select-option>
                    <a-select-option value="混合">🔀 混合</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :xs="24" :sm="12" :md="8">
                <a-form-item name="accommodation">
                  <template #label>
                    <span class="form-label">住宿偏好</span>
                  </template>
                  <a-select v-model:value="formData.accommodation" size="large" class="custom-select">
                    <a-select-option value="经济型酒店">💰 经济型酒店</a-select-option>
                    <a-select-option value="舒适型酒店">🏨 舒适型酒店</a-select-option>
                    <a-select-option value="豪华酒店">⭐ 豪华酒店</a-select-option>
                    <a-select-option value="民宿">🏡 民宿</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :xs="24" :sm="12" :md="8">
                <a-form-item name="food_preference">
                  <template #label>
                    <span class="form-label">美食偏好</span>
                  </template>
                  <a-select v-model:value="formData.food_preference" size="large" class="custom-select">
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
              <a-col :xs="24" :sm="12" :md="8">
                <a-form-item name="default_day_start_time">
                  <template #label>
                    <span class="form-label">每日开始时间</span>
                  </template>
                  <a-input
                    v-model:value="formData.default_day_start_time"
                    type="time"
                    size="large"
                    class="custom-input"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :sm="24" :md="24">
                <a-form-item name="preferences">
                  <template #label>
                    <span class="form-label">感兴趣的景点类型（可选）</span>
                  </template>
                  <div class="preference-hint">勾选后会用来筛选发现页的景点，并影响酒店、餐饮推荐的方向</div>
                  <div class="preference-tags">
                    <a-checkbox-group v-model:value="formData.preferences" class="custom-checkbox-group">
                      <a-checkbox value="历史文化" class="preference-tag">🏛️ 历史文化</a-checkbox>
                      <a-checkbox value="自然风光" class="preference-tag">🏞️ 自然风光</a-checkbox>
                      <a-checkbox value="都市地标" class="preference-tag">🌃 都市地标</a-checkbox>
                      <a-checkbox value="购物" class="preference-tag">🛍️ 购物</a-checkbox>
                      <a-checkbox value="艺术" class="preference-tag">🎨 艺术</a-checkbox>
                      <a-checkbox value="休闲" class="preference-tag">☕ 休闲</a-checkbox>
                      <a-checkbox value="夜生活" class="preference-tag">🌙 夜生活</a-checkbox>
                      <a-checkbox value="户外徒步" class="preference-tag">🥾 户外徒步</a-checkbox>
                      <a-checkbox value="祈福朝圣" class="preference-tag">🛐 祈福朝圣</a-checkbox>
                    </a-checkbox-group>
                  </div>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">💰</span>
              <span class="section-title">预算与同伴</span>
            </div>

            <a-row :gutter="24">
              <a-col :xs="24" :sm="24" :md="12">
                <a-form-item name="budget">
                  <template #label>
                    <span class="form-label">预算上限（元）</span>
                  </template>
                  <div class="budget-input-wrapper">
                    <a-input-number
                      v-model:value="formData.budget"
                      :min="0"
                      :step="500"
                      :max="100000"
                      placeholder="不限预算"
                      size="large"
                      class="budget-input"
                    >
                      <template #prefix>
                        <span class="input-prefix-icon">¥</span>
                      </template>
                      <template #suffix>
                        <span class="input-suffix-text">元</span>
                      </template>
                    </a-input-number>
                    <a-button
                      v-if="formData.budget"
                      type="link"
                      size="small"
                      @click="formData.budget = undefined"
                      class="budget-clear-btn"
                    >
                      清除
                    </a-button>
                  </div>
                  <div class="budget-hint">
                    <span v-if="!formData.budget" class="hint-text">💡 不设置预算将推荐最佳方案</span>
                    <span v-else class="hint-text active">
                      💰 预计分配：酒店{{ Math.round((formData.budget || 0) * 0.45) }}元 ·
                      餐饮{{ Math.round((formData.budget || 0) * 0.30) }}元 ·
                      门票{{ Math.round((formData.budget || 0) * 0.15) }}元 ·
                      交通{{ Math.round((formData.budget || 0) * 0.10) }}元
                    </span>
                  </div>
                </a-form-item>
              </a-col>
              <a-col :xs="12" :sm="12" :md="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">出行人数</span>
                  </template>
                  <a-input-number
                    v-model:value="formData.companions!.count"
                    :min="1"
                    :max="20"
                    size="large"
                    class="custom-input"
                    style="width: 100%"
                  >
                    <template #suffix>
                      <span class="input-suffix-text">人</span>
                    </template>
                  </a-input-number>
                </a-form-item>
              </a-col>
              <a-col :xs="12" :sm="12" :md="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">同伴类型</span>
                  </template>
                  <a-select v-model:value="formData.companions!.type" size="large" class="custom-select">
                    <a-select-option value="solo">🧑 独自出行</a-select-option>
                    <a-select-option value="couple">💑 情侣出行</a-select-option>
                    <a-select-option value="family">👨‍👩‍👧 家庭亲子</a-select-option>
                    <a-select-option value="friends">👫 朋友出行</a-select-option>
                    <a-select-option value="elderly">👴 带老人出行</a-select-option>
                    <a-select-option value="group">👥 团队出行</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">💬</span>
              <span class="section-title">额外要求</span>
            </div>

            <a-form-item name="free_text_input">
              <a-textarea
                v-model:value="formData.free_text_input"
                placeholder="请输入您的额外要求,例如:想去看升旗、需要无障碍设施、对海鲜过敏等..."
                :rows="3"
                size="large"
                class="custom-textarea"
              />
            </a-form-item>
          </div>

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              block
              class="submit-button"
            >
              <span class="button-icon">🚀</span>
              <span>开始探索景点</span>
            </a-button>
          </a-form-item>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { TripFormData } from '@/types'
import type { Dayjs } from 'dayjs'

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
.home-container {
  min-height: 100vh;
  background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
  transition: background var(--transition-normal);
}

.hero-section {
  position: relative;
  padding: var(--space-16) var(--space-6) var(--space-10);
  overflow: hidden;
}

.hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hero-glow {
  position: absolute;
  border-radius: var(--radius-circle);
  filter: blur(80px);
  opacity: 0.4;
}

.hero-glow-1 {
  width: 400px;
  height: 400px;
  top: -100px;
  left: -100px;
  background: #667eea;
  animation: float 8s ease-in-out infinite;
}

.hero-glow-2 {
  width: 300px;
  height: 300px;
  top: 50%;
  right: -50px;
  background: #764ba2;
  animation: float 10s ease-in-out infinite 2s;
}

.hero-glow-3 {
  width: 200px;
  height: 200px;
  bottom: -50px;
  left: 40%;
  background: #f093fb;
  animation: float 12s ease-in-out infinite 4s;
}

.hero-pattern {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px);
  background-size: 24px 24px;
}

.hero-content {
  position: relative;
  z-index: 1;
  text-align: center;
  max-width: 800px;
  margin: 0 auto;
}

.hero-badge {
  display: inline-block;
  padding: var(--space-1) var(--space-4);
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-pill);
  color: var(--color-text-inverse);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  backdrop-filter: blur(8px);
  margin-bottom: var(--space-4);
}

.hero-title {
  font-size: var(--font-size-7xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-inverse);
  margin: 0 0 var(--space-4);
  letter-spacing: -0.03em;
  text-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

.hero-subtitle {
  font-size: var(--font-size-xl);
  color: rgba(255, 255, 255, 0.9);
  margin: 0 0 var(--space-8);
  font-weight: 300;
  letter-spacing: 0.02em;
}

.hot-cities {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}

.hot-label {
  font-size: var(--font-size-sm);
  color: rgba(255, 255, 255, 0.7);
  font-weight: var(--font-weight-medium);
}

.city-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
}

.city-pill {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.1);
  color: var(--color-text-inverse);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-fast);
  backdrop-filter: blur(4px);
}

.city-pill:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.4);
  transform: translateY(-1px);
}

.city-pill:active {
  transform: scale(0.97);
}

.city-pill.active {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 12px rgba(255, 255, 255, 0.2);
}

.city-emoji {
  font-size: var(--font-size-base);
}

.form-section-wrapper {
  max-width: 1400px;
  margin: -40px auto 0;
  padding: 0 var(--space-6) var(--space-10);
  position: relative;
  z-index: 1;
}

.form-card {
  border-radius: var(--radius-xl) !important;
  box-shadow: var(--shadow-elevated) !important;
  border: 1px solid var(--color-border-light) !important;
  background: var(--color-bg-elevated) !important;
  animation: fadeInUp var(--transition-slow);
}

.form-section {
  margin-bottom: var(--space-6);
  padding: var(--space-5);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  transition: all var(--transition-normal);
}

.form-section:hover {
  box-shadow: var(--shadow-card);
}

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: var(--space-5);
  padding-bottom: var(--space-3);
  border-bottom: 2px solid var(--color-primary);
}

.section-icon {
  font-size: var(--font-size-2xl);
  margin-right: var(--space-3);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.form-label {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.input-prefix-icon {
  color: var(--color-primary);
}

.input-suffix-text {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.custom-input :deep(.ant-input),
.custom-input :deep(.ant-picker) {
  border-radius: var(--radius-sm);
  border: 1.5px solid var(--color-border-strong);
  transition: all var(--transition-fast);
}

.custom-input :deep(.ant-input:hover),
.custom-input :deep(.ant-picker:hover) {
  border-color: var(--color-primary);
}

.custom-input :deep(.ant-input:focus),
.custom-input :deep(.ant-picker-focused) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-bg);
}

.custom-select :deep(.ant-select-selector) {
  border-radius: var(--radius-sm) !important;
  border: 1.5px solid var(--color-border-strong) !important;
  transition: all var(--transition-fast);
}

.custom-select:hover :deep(.ant-select-selector) {
  border-color: var(--color-primary) !important;
}

.custom-select :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--color-primary) !important;
  box-shadow: 0 0 0 3px var(--color-primary-bg) !important;
}

.days-display {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: var(--space-2) var(--space-4);
  background: var(--color-gradient);
  border-radius: var(--radius-sm);
  color: var(--color-text-inverse);
}

.days-display .days-value {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  margin-right: 4px;
}

.days-display .days-unit {
  font-size: var(--font-size-base);
}

.preference-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.preference-hint {
  font-size: var(--font-size-xs, 12px);
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-2);
  line-height: 1.5;
}

.custom-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  width: 100%;
}

.preference-tag :deep(.ant-checkbox-wrapper) {
  margin: 0 !important;
  padding: var(--space-2) var(--space-4);
  border: 1.5px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  transition: all var(--transition-fast);
  background: var(--color-bg-elevated);
  font-size: var(--font-size-base);
}

.preference-tag :deep(.ant-checkbox-wrapper:hover) {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.preference-tag :deep(.ant-checkbox-wrapper-checked) {
  border-color: var(--color-primary);
  background: var(--color-gradient);
  color: var(--color-text-inverse);
}

.custom-textarea :deep(.ant-input) {
  border-radius: var(--radius-sm);
  border: 1.5px solid var(--color-border-strong);
  transition: all var(--transition-fast);
}

.custom-textarea :deep(.ant-input:hover) {
  border-color: var(--color-primary);
}

.custom-textarea :deep(.ant-input:focus) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-bg);
}

.budget-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.budget-input {
  flex: 1;
}

.budget-input :deep(.ant-input-number) {
  border-radius: var(--radius-sm);
  border: 1.5px solid var(--color-border-strong);
  width: 100%;
}

.budget-input :deep(.ant-input-number:hover) {
  border-color: var(--color-primary);
}

.budget-input :deep(.ant-input-number-focused) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-bg);
}

.budget-clear-btn {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.budget-hint {
  margin-top: var(--space-2);
}

.hint-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.hint-text.active {
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.submit-button {
  height: 56px;
  border-radius: var(--radius-pill) !important;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  background: var(--color-gradient) !important;
  border: none !important;
  box-shadow: var(--shadow-button) !important;
  transition: all var(--transition-normal);
}

.submit-button:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-button-hover) !important;
}

.submit-button:active {
  transform: translateY(0) scale(0.98);
}

.button-icon {
  margin-right: var(--space-2);
  font-size: var(--font-size-xl);
}

@media (max-width: 768px) {
  .hero-section {
    padding: var(--space-10) var(--space-4) var(--space-8);
  }

  .hero-title {
    font-size: var(--font-size-5xl);
  }

  .hero-subtitle {
    font-size: var(--font-size-base);
  }

  .form-section-wrapper {
    padding: 0 var(--space-4) var(--space-8);
  }

  .form-section {
    padding: var(--space-4);
  }

  .city-pills {
    gap: var(--space-1);
  }

  .city-pill {
    padding: var(--space-1) var(--space-3);
    font-size: var(--font-size-xs);
  }
}

@media (max-width: 480px) {
  .hero-title {
    font-size: var(--font-size-4xl);
  }
}
</style>

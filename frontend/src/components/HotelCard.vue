<template>
  <div class="hotel-card">
    <!-- 酒店图片 -->
    <div v-if="showImage" class="hotel-image-wrapper">
      <img :src="hotel.image_url" :alt="hotel.name" class="hotel-image" @error="handleImageError" />
    </div>

    <div class="hotel-header">
      <div class="hotel-icon">🏨</div>
      <div class="hotel-title-area">
        <h4 class="hotel-name">{{ hotel.name }}</h4>
        <div class="hotel-tags">
          <span v-if="hotel.type" class="hotel-type">{{ hotel.type }}</span>
          <span v-if="hotel.star_rating" class="hotel-star-badge">
            {{ getStarRatingText(hotel.star_rating) }}
          </span>
        </div>
      </div>
      <div v-if="hotel.rating || hotel.star_rating" class="hotel-rating">
        <span v-if="hotel.rating" class="rating-score">{{ hotel.rating }}</span>
        <span v-if="hotel.star_rating" class="rating-stars">{{ getStars(hotel.star_rating) }}</span>
      </div>
    </div>

    <div class="hotel-body">
      <!-- 地址 -->
      <div class="info-item address-item">
        <span class="info-icon">📍</span>
        <span class="info-text">{{ hotel.address }}</span>
      </div>

      <div v-if="hotel.recommendation" class="recommendation">
        <strong>为什么把它放在这里</strong>
        <p v-for="reason in hotel.recommendation.reasons" :key="reason">{{ reason }}</p>
        <details><summary>选之前再确认</summary><p v-for="note in hotel.recommendation.cautions" :key="note">{{ note }}</p></details>
      </div>
      <!-- 价格区域 -->
      <div class="hotel-price-section">
        <template v-if="hotel.quote">
          <div class="price-main" v-if="hotel.quote.amount != null">
            <span>{{ costKind }}</span>
            <span class="price-value">{{ hotel.quote.currency || '币种待确认' }} {{ hotel.quote.amount.toFixed(2) }}</span>
            <span class="price-unit">{{ priceUnit }}</span>
          </div>
          <div v-else class="price-pending">房型价格待确认</div>
          <p>{{ hotel.quote.check_in }} 入住 → {{ hotel.quote.check_out }} 退房 · {{ hotel.quote.nights }} 晚</p>
          <p>{{ hotel.quote.occupancy.room_count }} 间房，每间 {{ hotel.quote.occupancy.adults_per_room }} 位成人<span v-if="hotel.quote.occupancy.children_ages.length">，儿童 {{ hotel.quote.occupancy.children_ages.join('、') }} 岁</span></p>
          <p v-if="hotel.quote.room_name">{{ hotel.quote.room_name }} · {{ hotel.quote.bed_type || '床型待确认' }}</p>
          <p>{{ hotel.quote.meal_plan || '早餐条件待确认' }} · {{ hotel.quote.taxes_included === true ? '含税费' : hotel.quote.taxes_included === false ? '不含税费' : '税费待确认' }}</p>
          <p>{{ hotel.quote.cancellation_policy || '退改条件待确认' }}</p>
          <p>{{ availability }}，提交预订前需重新核价。</p>
          <ul v-if="hotel.quote.unsupported_conditions.length" role="alert">
            <li v-for="item in hotel.quote.unsupported_conditions" :key="item">{{ item }}</li>
          </ul>
          <small>来源：AIGoHotel · 查询时间 {{ queryTime }}</small>
        </template>
        <div v-else class="price-pending">历史住宿价格未核对入住条件，当前房型价格待确认</div>
      </div>

      <!-- 距离 -->
      <div class="info-item">
        <span class="info-icon">📏</span>
        <span class="info-text">{{ hotel.distance }}</span>
        <span v-if="hotel.distance_in_meters" class="distance-meters">
          ({{ formatDistance(hotel.distance_in_meters) }})
        </span>
      </div>

      <!-- 设施标签 -->
      <div v-if="hotel.hotel_amenities && hotel.hotel_amenities.length > 0" class="amenities-section">
        <div class="amenities-label">设施</div>
        <div class="amenities-tags">
          <span
            v-for="amenity in hotel.hotel_amenities.slice(0, 6)"
            :key="amenity"
            class="amenity-tag"
          >
            {{ amenity }}
          </span>
        </div>
      </div>

      <!-- 房间设施 -->
      <div v-if="hotel.room_amenities && hotel.room_amenities.length > 0" class="amenities-section">
        <div class="amenities-label">房间</div>
        <div class="amenities-tags">
          <span
            v-for="amenity in hotel.room_amenities.slice(0, 4)"
            :key="amenity"
            class="amenity-tag room-tag"
          >
            {{ amenity }}
          </span>
        </div>
      </div>

      <!-- 详细描述 -->
      <details v-if="cleanedDescription" class="description-section"><summary>供应方酒店介绍（未经独立验证）</summary>
        <div class="description-content" :class="{ expanded: isDescExpanded }">
          {{ cleanedDescription }}
        </div>
        <button
          v-if="cleanedDescription.length > 80"
          class="desc-toggle"
          @click="isDescExpanded = !isDescExpanded"
        >
          {{ isDescExpanded ? '收起' : '展开' }}
        </button>
      </details>

      <!-- 操作按钮 -->
      <div v-if="hotel.detail_url" class="hotel-actions">
        <a
          :href="hotel.detail_url"
          target="_blank"
          rel="noopener noreferrer"
          class="detail-link"
        >
          查看详情 →
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Hotel } from '@/types'

const props = defineProps<{
  hotel: Hotel
}>()

const costKind = computed(() => props.hotel.quote?.unsupported_conditions.length ? '条件未匹配的参考价（未计入预算）' : ({ query_quote: '查询参考报价', user_estimate: '用户估算', system_estimate: '系统估算', paid: '已付金额', unknown: '价格待确认' }[props.hotel.quote?.cost_kind || 'unknown']))
const priceUnit = computed(() => ({ average_per_room_night: '/间/晚（整段均价）', total_stay: '/整段住宿', unknown: '（计价单位待确认）' }[props.hotel.quote?.unit || 'unknown']))
const availability = computed(() => ({ returned: '本次查询返回房型，尚未预订', on_request: '房型需供应方确认', unavailable: '未返回可售房型', unknown: '可售状态待确认' }[props.hotel.quote?.availability || 'unknown']))
const queryTime = computed(() => props.hotel.quote?.queried_at ? new Date(props.hotel.quote.queried_at).toLocaleString('zh-CN', { hour12: false }) : '未记录')

const isDescExpanded = ref(false)

const imageFailed = ref(false)
const showImage = computed(() => !!props.hotel.image_url && !imageFailed.value)
const cleanedDescription = computed(() => {
  const description = props.hotel.description?.trim()
  if (!description) return ''

  const document = new DOMParser().parseFromString(
    description.replace(/<br\s*\/?>/gi, ' '),
    'text/html',
  )
  return (document.body.textContent || '').replace(/\s+/g, ' ').trim()
})

const handleImageError = () => {
  imageFailed.value = true
}

const getStars = (rating: number): string => {
  const full = Math.floor(rating)
  const half = rating % 1 >= 0.5 ? 1 : 0
  return '★'.repeat(full) + (half ? '☆' : '') + '☆'.repeat(Math.max(0, 5 - full - half))
}

const getStarRatingText = (rating: number): string => {
  if (rating >= 5) return '五星级'
  if (rating >= 4.5) return '豪华型'
  if (rating >= 4) return '四星级'
  if (rating >= 3.5) return '高档型'
  if (rating >= 3) return '三星级'
  return '经济型'
}

const formatDistance = (meters: number): string => {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)}km`
  }
  return `${meters}m`
}
</script>

<style>
.hotel-card {
  color: var(--color-text-primary);
  background: var(--white);
  border-radius: 0;
  overflow: hidden;
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  transition: all var(--transition-fast);
  position: relative;
}

.hotel-card:hover {
  transform: translateY(-2px);
  box-shadow: 8px 8px 0px 0px var(--border);
}

/* 右上角蓝色装饰 */
.hotel-card::after {
  content: '';
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--primary-blue);
  z-index: 10;
}
</style>

<style scoped>
.hotel-image-wrapper {
  width: 100%;
  height: 160px;
  overflow: hidden;
  background: var(--color-bg-secondary);
}

.hotel-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.hotel-card:hover .hotel-image {
  transform: scale(1.03);
}

.hotel-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4) var(--space-2);
}

.hotel-icon {
  font-size: var(--font-size-3xl);
  flex-shrink: 0;
}

.hotel-title-area {
  flex: 1;
  min-width: 0;
}

.hotel-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-black);
  text-transform: uppercase;
  color: var(--foreground);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.05em;
}

.hotel-tags {
  display: flex;
  gap: var(--space-1);
  margin-top: 4px;
  flex-wrap: wrap;
}

.hotel-type {
  display: inline-block;
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: 1px var(--space-2);
  border-radius: 9999px;
}

.hotel-star-badge {
  display: inline-block;
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  background: var(--color-warning-bg);
  padding: 1px var(--space-2);
  border-radius: 9999px;
}

.hotel-rating {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
}

.rating-score {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
}

.rating-stars {
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  letter-spacing: 1px;
}

.hotel-body {
  padding: 0 var(--space-4) var(--space-4);
}

.info-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.address-item .info-text {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  line-height: 1.5;
}

.info-icon {
  font-size: var(--font-size-sm);
  flex-shrink: 0;
}

.info-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-text.price {
  color: var(--color-warning);
  font-weight: var(--font-weight-medium);
}

.hotel-price-section p, .hotel-price-section li {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  margin: 6px 0;
  overflow-wrap: anywhere;
}

.hotel-price-section {
  margin-bottom: var(--space-2);
}

.price-main {
  display: flex;
  align-items: baseline;
  gap: 4px;
  flex-wrap: wrap;
}

.price-currency {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.price-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-warning);
}

.price-unit {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.price-original {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  text-decoration: line-through;
}

.price-save {
  font-size: var(--font-size-xs);
  color: var(--color-success);
  background: var(--color-success-bg);
  padding: 0 6px;
  border-radius: 4px;
}

.price-estimated {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.price-pending {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.distance-meters {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-left: 4px;
}

.amenities-section {
  margin-bottom: var(--space-2);
}

.amenities-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.amenities-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.amenity-tag {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: 2px 8px;
  border-radius: 9999px;
  white-space: nowrap;
}

.room-tag {
  color: var(--color-success);
  background: var(--color-success-bg);
}

.description-section {
  margin-bottom: var(--space-2);
}

.description-content {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.description-content.expanded {
  -webkit-line-clamp: unset;
  display: block;
}

.desc-toggle {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: none;
  border: none;
  padding: 0;
  margin-top: 4px;
  cursor: pointer;
}

.desc-toggle:hover {
  text-decoration: underline;
}

.hotel-actions {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.detail-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  text-decoration: none;
  font-weight: var(--font-weight-medium);
}

.detail-link:hover {
  text-decoration: underline;
}
</style>

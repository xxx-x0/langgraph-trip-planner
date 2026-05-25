<template>
  <div class="my-trips-page">
    <!-- Bauhaus Three-Color Mosaic Header -->
    <div class="mosaic-header">
      <div class="mosaic-red"></div>
      <div class="mosaic-blue"></div>
      <div class="mosaic-yellow"></div>
    </div>

    <div class="page-header">
      <h1 class="page-title">我的行程</h1>
      <p class="page-subtitle">查看和管理你的旅行计划</p>
    </div>

    <div class="toolbar">
      <div class="filter-pills">
        <button
          v-for="filter in filters"
          :key="filter.value"
          class="filter-pill"
          :class="{ active: currentFilter === filter.value }"
          @click="setFilter(filter.value)"
        >
          <span class="pill-icon">{{ filter.icon }}</span>
          <span class="pill-label">{{ filter.label }}</span>
        </button>
      </div>
      <div class="search-box">
        <a-input-search
          v-model:value="searchKeyword"
          placeholder="搜索城市、标题..."
          @search="handleSearch"
          style="width: 260px"
          allow-clear
        />
      </div>
    </div>

    <a-spin :spinning="loading" tip="加载中...">
      <div v-if="trips.length === 0 && !loading" class="empty-state">
        <div class="empty-icon">📋</div>
        <div class="empty-text">还没有行程记录</div>
        <div class="empty-hint">去首页创建你的第一个旅行计划吧！</div>
        <a-button type="primary" @click="goHome" size="large" class="empty-btn">
          ✨ 开始规划
        </a-button>
      </div>

      <div v-else class="trips-grid">
        <div
          v-for="(trip, idx) in trips"
          :key="trip.id"
          class="trip-card animate-fade-in-up"
          :class="`stagger-${Math.min(idx + 1, 8)}`"
          @click="viewTrip(trip)"
        >
          <div class="card-cover" :style="getCoverStyle(trip)">
            <div class="card-cover-overlay"></div>
            <div class="card-status-badge" :class="trip.status">
              {{ getStatusLabel(trip.status) }}
            </div>
            <div class="card-city">{{ trip.city }}</div>
          </div>
          <div class="card-body">
            <div class="card-title">{{ trip.title }}</div>
            <div class="card-meta">
              <span class="meta-item">📅 {{ formatDateRange(trip) }}</span>
              <span class="meta-item">⏱️ {{ trip.travel_days }}天</span>
            </div>
            <div class="card-meta">
              <span v-if="trip.total_cost" class="meta-item cost">💰 ¥{{ trip.total_cost }}</span>
              <span v-if="trip.companion_type" class="meta-item">{{ getCompanionLabel(trip.companion_type) }}</span>
            </div>
            <div v-if="trip.tags && trip.tags.length" class="card-tags">
              <span v-for="tag in trip.tags.slice(0, 3)" :key="tag" class="tag-pill">{{ tag }}</span>
            </div>
          </div>
          <div class="card-actions" @click.stop>
            <button
              class="action-btn"
              :class="{ 'fav-active': trip.status === 'favorite' }"
              @click="toggleFavorite(trip)"
              :title="trip.status === 'favorite' ? '取消收藏' : '收藏'"
            >
              {{ trip.status === 'favorite' ? '⭐' : '☆' }}
            </button>
            <button
              class="action-btn"
              @click="toggleArchive(trip)"
              :title="trip.status === 'archived' ? '取消归档' : '归档'"
            >
              {{ trip.status === 'archived' ? '📂' : '📁' }}
            </button>
            <a-popconfirm title="确定删除此行程？" @confirm="handleDelete(trip)" ok-text="删除" cancel-text="取消">
              <button class="action-btn danger" title="删除">🗑️</button>
            </a-popconfirm>
          </div>
        </div>
      </div>

      <div v-if="total > pageSize" class="pagination-wrapper">
        <a-pagination
          v-model:current="currentPage"
          :total="total"
          :page-size="pageSize"
          @change="handlePageChange"
          show-less-items
        />
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { TripRecord } from '@/types'
import { getTripList, deleteTripFromHistory, updateTripStatus, searchTrips } from '@/services/api'

const router = useRouter()

const trips = ref<TripRecord[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(12)
const currentFilter = ref('')
const searchKeyword = ref('')

const filters = [
  { value: '', label: '全部', icon: '📋' },
  { value: 'favorite', label: '收藏', icon: '⭐' },
  { value: 'archived', label: '归档', icon: '📦' },
]

const setFilter = (value: string) => {
  currentFilter.value = value
  currentPage.value = 1
  searchKeyword.value = ''
  loadTrips()
}

const loadTrips = async () => {
  loading.value = true
  try {
    const res = await getTripList({
      status: currentFilter.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value,
    })
    trips.value = res.data
    total.value = res.total
  } catch (e: any) {
    message.error('加载行程列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = async (value: string) => {
  if (!value.trim()) {
    loadTrips()
    return
  }
  loading.value = true
  try {
    const res = await searchTrips(value, currentPage.value, pageSize.value)
    trips.value = res.data
    total.value = res.total
  } catch {
    message.error('搜索失败')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadTrips()
}

const viewTrip = (trip: TripRecord) => {
  router.push(`/trip/${trip.id}`)
}

const goHome = () => { router.push('/') }

const toggleFavorite = async (trip: TripRecord) => {
  const newStatus = trip.status === 'favorite' ? 'completed' : 'favorite'
  try {
    await updateTripStatus(trip.id, newStatus)
    trip.status = newStatus as any
    message.success(newStatus === 'favorite' ? '已收藏' : '已取消收藏')
  } catch {
    message.error('操作失败')
  }
}

const toggleArchive = async (trip: TripRecord) => {
  const newStatus = trip.status === 'archived' ? 'completed' : 'archived'
  try {
    await updateTripStatus(trip.id, newStatus)
    trip.status = newStatus as any
    message.success(newStatus === 'archived' ? '已归档' : '已取消归档')
  } catch {
    message.error('操作失败')
  }
}

const handleDelete = async (trip: TripRecord) => {
  try {
    await deleteTripFromHistory(trip.id)
    message.success('行程已删除')
    loadTrips()
  } catch {
    message.error('删除失败')
  }
}

const getCoverStyle = (trip: TripRecord) => {
  if (trip.cover_image) {
    return { backgroundImage: `url(${trip.cover_image})` }
  }
  const colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#43e97b', '#fa709a']
  const idx = trip.id % colors.length
  return { background: `linear-gradient(135deg, ${colors[idx]}, ${colors[(idx + 1) % colors.length]})` }
}

const formatDateRange = (trip: TripRecord) => `${trip.start_date} ~ ${trip.end_date}`

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { completed: '已完成', favorite: '⭐ 收藏', archived: '📦 归档' }
  return map[status] || status
}

const getCompanionLabel = (type: string) => {
  const map: Record<string, string> = {
    solo: '🧑 独自', couple: '💑 情侣', family: '👨‍👩‍👧 亲子',
    friends: '👫 朋友', elderly: '👴 带老人', group: '👥 团队'
  }
  return map[type] || type
}

onMounted(loadTrips)
</script>

<style scoped>
.my-trips-page {
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: 0;
  background: var(--white, #fff);
}

/* Bauhaus Three-Color Mosaic Header */
.mosaic-header {
  display: flex;
  height: 120px;
  border-bottom: var(--border-main, 4px) solid var(--border, #121212);
}

.mosaic-red {
  flex: 1;
  background: var(--primary-red, #D02020);
}

.mosaic-blue {
  flex: 1;
  background: var(--primary-blue, #1040C0);
  border-left: var(--border-main, 4px) solid var(--border, #121212);
  border-right: var(--border-main, 4px) solid var(--border, #121212);
}

.mosaic-yellow {
  flex: 1;
  background: var(--primary-yellow, #F0C020);
}

.page-header {
  text-align: center;
  margin-bottom: var(--space-8);
  padding: var(--space-8, 32px) var(--space-6, 24px) 0;
}

.page-title {
  font-size: var(--font-size-4xl);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
  margin-bottom: var(--space-2);
  letter-spacing: 0.02em;
}

.page-subtitle {
  color: var(--foreground, #121212);
  font-size: var(--font-size-base);
  font-weight: var(--font-medium, 500);
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-6);
  padding: 0 var(--space-6, 24px);
  flex-wrap: wrap;
  gap: var(--space-4);
}

.filter-pills {
  display: flex;
  gap: var(--space-2);
}

.filter-pill {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  color: var(--foreground, #121212);
  font-size: var(--font-size-sm);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
}

.filter-pill:hover {
  transform: translate(1px, 1px);
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

.filter-pill:active {
  transform: translate(3px, 3px);
  box-shadow: none;
}

.filter-pill.active {
  background: var(--primary-blue, #1040C0);
  color: var(--white, #fff);
}

.pill-icon {
  font-size: var(--font-size-sm);
}

.trips-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-5);
  padding: 0 var(--space-6, 24px) var(--space-8, 32px);
}

.trip-card {
  background: var(--white, #fff);
  border: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--transition-normal);
  position: relative;
}

.trip-card:hover {
  transform: translate(-2px, -2px);
  box-shadow: 10px 10px 0px 0px var(--border, #121212);
}

/* Colorful left border (8px) - cycles through red/blue/yellow */
.trip-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  z-index: 1;
}

.trip-card:nth-child(3n+1)::before {
  background: var(--primary-red, #D02020);
}

.trip-card:nth-child(3n+2)::before {
  background: var(--primary-blue, #1040C0);
}

.trip-card:nth-child(3n+3)::before {
  background: var(--primary-yellow, #F0C020);
}

.card-cover {
  height: 140px;
  background-size: cover;
  background-position: center;
  position: relative;
  display: flex;
  align-items: flex-end;
  padding: var(--space-3);
  border-bottom: var(--border-main, 4px) solid var(--border, #121212);
}

.card-cover-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.6) 0%, transparent 60%);
}

.card-status-badge {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  padding: 4px var(--space-3);
  border: 2px solid var(--border, #121212);
  font-size: var(--font-size-xs);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  background: var(--white, #fff);
  color: var(--foreground, #121212);
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

.card-status-badge.favorite {
  background: var(--primary-yellow, #F0C020);
  color: var(--foreground, #121212);
}

.card-status-badge.archived {
  background: var(--background, #F0F0F0);
  color: var(--foreground, #121212);
}

.card-city {
  position: relative;
  z-index: 1;
  color: var(--white, #fff);
  font-size: var(--font-size-2xl);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  text-shadow: 2px 2px 0px rgba(0, 0, 0, 0.8);
}

.card-body {
  padding: var(--space-4);
  padding-left: calc(var(--space-4) + 8px); /* Account for left border */
}

.card-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-black, 900);
  color: var(--foreground, #121212);
  margin-bottom: var(--space-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-transform: uppercase;
}

.card-meta {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--foreground, #121212);
  font-weight: var(--font-medium, 500);
}

.meta-item.cost {
  color: var(--primary-red, #D02020);
  font-weight: var(--font-black, 900);
}

.card-tags {
  margin-top: var(--space-2);
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.tag-pill {
  display: inline-block;
  padding: 2px var(--space-2);
  border: 2px solid var(--border, #121212);
  font-size: var(--font-size-xs);
  color: var(--foreground, #121212);
  background: var(--background, #F0F0F0);
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  padding: var(--space-2) var(--space-3);
  padding-left: calc(var(--space-3) + 8px); /* Account for left border */
  border-top: 2px solid var(--border, #121212);
  gap: var(--space-1);
  background: var(--background, #F0F0F0);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  cursor: pointer;
  font-size: var(--font-size-base);
  transition: all var(--transition-fast);
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

.action-btn:hover {
  transform: translate(1px, 1px);
  box-shadow: 1px 1px 0px 0px var(--border, #121212);
}

.action-btn:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

.action-btn.fav-active {
  background: var(--primary-yellow, #F0C020);
}

.action-btn.danger:hover {
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
}

.empty-state {
  text-align: center;
  padding: var(--space-16) var(--space-5);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: var(--space-4);
}

.empty-text {
  font-size: var(--font-size-xl);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
  margin-bottom: var(--space-2);
}

.empty-hint {
  color: var(--foreground, #121212);
  font-weight: var(--font-medium, 500);
  margin-bottom: var(--space-6);
}

.empty-btn {
  border: 2px solid var(--border, #121212) !important;
  border-radius: 0 !important;
  height: 44px;
  padding: 0 var(--space-8);
  background: var(--primary-blue, #1040C0) !important;
  color: var(--white, #fff) !important;
  font-weight: var(--font-black, 900) !important;
  text-transform: uppercase !important;
  box-shadow: 4px 4px 0px 0px var(--border, #121212) !important;
}

.empty-btn:hover {
  transform: translate(1px, 1px);
  box-shadow: 3px 3px 0px 0px var(--border, #121212) !important;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: var(--space-8);
  padding-bottom: var(--space-8);
}

@media (max-width: 768px) {
  .my-trips-page {
    padding: 0;
  }

  .mosaic-header {
    height: 80px;
  }

  .page-header {
    padding: var(--space-6, 24px) var(--space-3, 12px) 0;
  }

  .toolbar {
    flex-direction: column;
    align-items: stretch;
    padding: 0 var(--space-3, 12px);
  }

  .filter-pills {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .search-box {
    width: 100%;
  }

  .search-box :deep(.ant-input-search) {
    width: 100% !important;
  }

  .trips-grid {
    grid-template-columns: 1fr;
    padding: 0 var(--space-3, 12px) var(--space-6, 24px);
  }
}
</style>

<template>
  <div class="tab-budget">
    <div class="glass-card">
      <div class="card-header">
        <span class="card-icon">💰</span>
        <span class="card-title">预算明细</span>
      </div>
      <div class="budget-body">
        <div class="budget-grid">
          <div class="budget-item">
            <div class="budget-label">景点门票</div>
            <div class="budget-value">¥{{ budget.total_attractions }}</div>
          </div>
          <div class="budget-item">
            <div class="budget-label">酒店住宿</div>
            <div class="budget-value">¥{{ budget.total_hotels }}</div>
          </div>
          <div class="budget-item">
            <div class="budget-label">餐饮费用</div>
            <div class="budget-value">¥{{ budget.total_meals }}</div>
          </div>
          <div class="budget-item">
            <div class="budget-label">交通费用</div>
            <div class="budget-value">¥{{ budget.total_transportation }}</div>
          </div>
        </div>
        <div class="budget-total" :class="{ 'over-budget': budget.budget_limit && !budget.is_within_budget }">
          <span class="total-label">预估总费用</span>
          <span class="total-value">¥{{ budget.total }}</span>
        </div>
        <div v-if="budget.budget_limit" class="budget-limit-info">
          <div class="budget-limit-bar">
            <div
              class="budget-limit-fill"
              :style="{ width: Math.min((budget.total / budget.budget_limit) * 100, 100) + '%' }"
              :class="{ 'over': budget.total > budget.budget_limit }"
            ></div>
          </div>
          <div class="budget-limit-text">
            <span>预算上限: ¥{{ budget.budget_limit }}</span>
            <span :class="budget.is_within_budget ? 'within-budget' : 'over-budget-text'">
              {{ budget.is_within_budget ? '✅ 在预算范围内' : '⚠️ 超出预算 ¥' + (budget.total - budget.budget_limit) }}
            </span>
          </div>
        </div>
        <BudgetChart v-if="budget.total > 0" :budget="budget" class="budget-chart-section" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Budget } from '@/types'
import BudgetChart from '@/components/BudgetChart.vue'

defineProps<{
  budget: Budget
}>()
</script>

<style scoped>
.tab-budget {
  max-width: 800px;
  margin: 0 auto;
  animation: fadeInUp var(--transition-normal);
}

.glass-card {
  background: var(--color-glass-bg);
  backdrop-filter: blur(var(--blur-glass));
  -webkit-backdrop-filter: blur(var(--blur-glass));
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  transition: box-shadow var(--transition-normal);
}

.glass-card:hover {
  box-shadow: var(--shadow-card-hover);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  background: var(--color-gradient);
  color: #fff;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.card-icon {
  font-size: var(--font-size-xl);
}

.budget-body {
  padding: var(--space-5);
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.budget-item {
  text-align: center;
  padding: var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.budget-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}

.budget-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  background: var(--color-gradient);
  border-radius: var(--radius-sm);
  color: #fff;
}

.budget-total.over-budget {
  background: linear-gradient(135deg, #ff4d4f 0%, #cf1322 100%);
}

.total-label {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.total-value {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
}

.budget-limit-info {
  margin-top: var(--space-3);
  padding: var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
}

.budget-limit-bar {
  height: 8px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-pill);
  overflow: hidden;
  margin-bottom: var(--space-2);
}

.budget-limit-fill {
  height: 100%;
  background: linear-gradient(90deg, #52c41a, #73d13d);
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}

.budget-limit-fill.over {
  background: linear-gradient(90deg, #ff4d4f, #cf1322);
}

.budget-limit-text {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.within-budget { color: var(--color-success); font-weight: var(--font-weight-semibold); }
.over-budget-text { color: var(--color-error); font-weight: var(--font-weight-semibold); }

.budget-chart-section {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
}

@media (max-width: 480px) {
  .budget-grid {
    grid-template-columns: 1fr;
  }
}
</style>

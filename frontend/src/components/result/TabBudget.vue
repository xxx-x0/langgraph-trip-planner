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

/* Bauhaus card styling */
.glass-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  overflow: hidden;
  transition: all var(--transition-fast);
}

.glass-card:hover {
  transform: translateY(-2px);
  box-shadow: 6px 6px 0px 0px var(--border);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-6);
  background: var(--primary-yellow);
  color: var(--foreground);
  border-bottom: var(--border-main) solid var(--border);
}

.card-title {
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.card-icon {
  font-size: var(--text-2xl);
}

.budget-body {
  padding: var(--space-6);
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.budget-item {
  text-align: center;
  padding: var(--space-4);
  background: var(--background);
  border: var(--border-2) solid var(--border);
  transition: all var(--transition-fast);
}

.budget-item:hover {
  transform: translateY(-2px);
  box-shadow: 3px 3px 0px 0px var(--border);
}

.budget-label {
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
  text-transform: uppercase;
  color: var(--muted-foreground);
  margin-bottom: var(--space-2);
}

.budget-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-black);
  color: var(--primary-blue);
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-5);
  background: var(--primary-blue);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  color: var(--white);
}

.budget-total.over-budget {
  background: var(--primary-red);
}

.total-label {
  font-size: var(--text-lg);
  font-weight: var(--font-black);
  text-transform: uppercase;
}

.total-value {
  font-size: var(--text-4xl);
  font-weight: var(--font-black);
}

.budget-limit-info {
  margin-top: var(--space-4);
  padding: var(--space-4);
  background: var(--background);
  border: var(--border-2) solid var(--border);
}

.budget-limit-bar {
  height: 12px;
  background: var(--muted);
  border: var(--border-2) solid var(--border);
  overflow: hidden;
  margin-bottom: var(--space-3);
}

.budget-limit-fill {
  height: 100%;
  background: var(--primary-blue);
  transition: width 0.5s ease;
}

.budget-limit-fill.over {
  background: var(--primary-red);
}

.budget-limit-text {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
  color: var(--foreground);
}

.within-budget {
  color: var(--primary-blue);
  font-weight: var(--font-black);
  text-transform: uppercase;
}

.over-budget-text {
  color: var(--primary-red);
  font-weight: var(--font-black);
  text-transform: uppercase;
}

.budget-chart-section {
  margin-top: var(--space-6);
  padding-top: var(--space-6);
  border-top: var(--border-main) solid var(--border);
}

@media (max-width: 480px) {
  .budget-grid {
    grid-template-columns: 1fr;
  }
}
</style>

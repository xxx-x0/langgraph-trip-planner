<template>
  <div class="tab-budget">
    <div class="glass-card">
      <div class="card-header">
        <span class="card-icon">💰</span>
        <span class="card-title">预算明细</span>
      </div>
      <div class="budget-body">
        <div class="budget-total" :class="{ 'over-budget': budget.is_within_budget === false }">
          <span class="total-label">{{ budget.is_complete === true ? '预估总费用' : '已知费用预估小计' }}</span>
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
            <span :class="budget.is_within_budget === true ? 'within-budget' : 'over-budget-text'">
              {{ budget.is_within_budget === true ? '✅ 在预算范围内' : budget.is_within_budget === false ? '⚠️ 已知费用超出预算 ¥' + (budget.total - budget.budget_limit) : '费用有缺项，暂不能判断是否在预算内' }}
            </span>
          </div>
        </div>

        <div v-if="budget.is_complete !== true" role="alert" class="budget-limit-info">
          费用尚不完整，所示金额仅为已知费用的预估小计。
          <details v-if="budget.unknown_cost_items?.length" :open="expanded"><summary>查看 {{ budget.unknown_cost_items.length }} 项费用缺项</summary><ul>
            <li v-for="item in budget.unknown_cost_items" :key="item">{{ item }}：待确认</li>
          </ul></details>
          <span v-else>历史预算未记录缺项状态，请重新核对费用。</span>
        </div>
        <p>大交通仅计入已填写的已知费用；市内交通按每人每天50元估算。酒店未核对的报价不计入小计，未知不代表免费。</p>
        <p v-if="budget.total_intercity">交通合计中，往返大交通 {{ budget.total_intercity }} 元，市内交通估算 {{ Math.round((budget.total_transportation-budget.total_intercity)*100)/100 }} 元，均按全体同行人合计。</p>
        <div class="budget-grid">
          <div class="budget-item">
            <div class="budget-label">已知景点门票</div>
            <div class="budget-value">¥{{ budget.total_attractions }}</div>
          </div>
          <div class="budget-item">
            <div class="budget-label">已核对住宿参考价</div>
            <div class="budget-value">¥{{ budget.total_hotels }}</div>
          </div>
          <div class="budget-item">
            <div class="budget-label">餐饮费用</div>
            <div class="budget-value">¥{{ budget.total_meals }}</div>
          </div>
          <div class="budget-item">
            <div class="budget-label">交通费用合计</div>
            <div class="budget-value">¥{{ budget.total_transportation }}</div>
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
  expanded?: boolean
  budget: Budget
}>()
</script>

<style scoped>
.tab-budget { color: var(--color-text-primary); }
.glass-card { border: 1px solid var(--color-border); background: var(--color-bg-primary); border-radius: 18px; overflow: hidden; }
.card-header { display: flex; align-items: center; gap: 10px; padding: 24px 24px 0; }
.card-icon { display: none; }.card-title { font-size: 24px; font-weight: 500; }
.budget-body { padding: 24px; }.budget-body > p { color: var(--color-text-secondary); font-size: 12px; line-height: 1.8; }
.budget-total { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 22px; background: var(--color-bg-secondary); border-radius: 14px; }
.total-label { font-size: 14px; }.total-value { font-size: 36px; color: var(--color-primary); font-weight: 500; font-variant-numeric: tabular-nums; }
.budget-total.over-budget .total-value { color: var(--color-error); }
.budget-limit-info { margin: 18px 0; font-size: 13px; line-height: 1.8; }
.budget-limit-info[role=alert] { background: var(--color-warning-bg); color: var(--color-warning); padding: 16px 18px; border-radius: 12px; }
.budget-limit-info summary { cursor: pointer; margin-top: 8px; }.budget-limit-info ul { padding-left: 20px; margin-bottom: 0; }
.budget-limit-bar { height: 5px; border-radius: 8px; background: var(--color-bg-tertiary); overflow: hidden; margin-bottom: 12px; }
.budget-limit-fill { height: 100%; background: var(--color-primary); }.budget-limit-fill.over { background: var(--color-error); }
.budget-limit-text { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; color: var(--color-text-secondary); }
.over-budget-text { color: var(--color-warning); }.within-budget { color: var(--color-success); }
.budget-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; margin-top: 24px; }
.budget-item { border: 1px solid var(--color-border); padding: 20px 16px; border-radius: 12px; }.budget-label { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 10px; }.budget-value { font-size: 25px; color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.budget-chart-section { margin-top: 28px; padding-top: 24px; border-top: 1px solid var(--color-border); }
@media(max-width:800px) { .budget-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media(max-width:480px) { .budget-body { padding: 18px; }.card-header { padding: 20px 18px 0; }.budget-total { padding: 18px; }.total-value { font-size: 29px; }.total-label { font-size: 12px; } }
</style>

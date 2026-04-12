<template>
  <div class="budget-chart-container">
    <div ref="barChartRef" class="chart-box"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { Budget } from '@/types'

const props = defineProps<{
  budget: Budget
}>()

const barChartRef = ref<HTMLElement>()
let barChart: echarts.ECharts | null = null

const initChart = () => {
  if (!props.budget) return

  if (barChartRef.value) {
    barChart = echarts.init(barChartRef.value)
    barChart.setOption(getBarOption())
  }
}

const getBarOption = () => {
  const b = props.budget
  const categories = ['景点门票', '酒店住宿', '餐饮费用', '交通费用']
  const values = [b.total_attractions, b.total_hotels, b.total_meals, b.total_transportation]
  const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666']

  const budgetLimit = b.budget_limit

  return {
    title: {
      text: budgetLimit ? '费用 vs 预算' : '费用明细',
      left: 'center',
      top: 10,
      textStyle: { fontSize: 14, color: '#333', fontWeight: 600 }
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let tip = ''
        params.forEach((p: any) => {
          tip += `${p.marker} ${p.seriesName}: ¥${p.value}<br/>`
        })
        return tip
      }
    },
    grid: {
      left: 60,
      right: 30,
      top: 50,
      bottom: 40
    },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: { fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '¥{value}', fontSize: 11 }
    },
    series: [
      {
        name: '实际费用',
        type: 'bar',
        data: values.map((v, i) => ({
          value: v,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: colors[i] },
              { offset: 1, color: colors[i] + '80' }
            ]),
            borderRadius: [4, 4, 0, 0]
          }
        })),
        barWidth: '40%',
        label: {
          show: true,
          position: 'top',
          formatter: '¥{c}',
          fontSize: 11,
          color: '#666'
        }
      },
      ...(budgetLimit ? [{
        name: '预算参考',
        type: 'line',
        data: categories.map((_, i) => {
          const ratios = [0.15, 0.45, 0.30, 0.10]
          return Math.round(budgetLimit * ratios[i])
        }),
        lineStyle: { color: '#ff4d4f', type: 'dashed', width: 2 },
        itemStyle: { color: '#ff4d4d' },
        symbol: 'diamond',
        symbolSize: 8,
        label: {
          show: true,
          position: 'top',
          formatter: '¥{c}',
          fontSize: 10,
          color: '#ff4d4f'
        }
      }] : [])
    ]
  }
}

const handleResize = () => {
  barChart?.resize()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  barChart?.dispose()
})

watch(() => props.budget, () => {
  if (barChart) barChart.setOption(getBarOption())
}, { deep: true })
</script>

<style scoped>
.budget-chart-container {
  width: 100%;
}

.chart-box {
  width: 100%;
  height: 300px;
}
</style>

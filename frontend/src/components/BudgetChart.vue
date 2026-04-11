<template>
  <div class="budget-chart-container">
    <div class="chart-row">
      <div class="chart-item">
        <div ref="pieChartRef" class="chart-box"></div>
      </div>
      <div class="chart-item">
        <div ref="barChartRef" class="chart-box"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { Budget } from '@/types'

const props = defineProps<{
  budget: Budget
}>()

const pieChartRef = ref<HTMLElement>()
const barChartRef = ref<HTMLElement>()
let pieChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null

const initCharts = () => {
  if (!props.budget) return

  if (pieChartRef.value) {
    pieChart = echarts.init(pieChartRef.value)
    pieChart.setOption(getPieOption())
  }

  if (barChartRef.value) {
    barChart = echarts.init(barChartRef.value)
    barChart.setOption(getBarOption())
  }
}

const getPieOption = () => {
  const b = props.budget
  const data = [
    { value: b.total_attractions, name: '景点门票', itemStyle: { color: '#5470c6' } },
    { value: b.total_hotels, name: '酒店住宿', itemStyle: { color: '#91cc75' } },
    { value: b.total_meals, name: '餐饮费用', itemStyle: { color: '#fac858' } },
    { value: b.total_transportation, name: '交通费用', itemStyle: { color: '#ee6666' } }
  ].filter(d => d.value > 0)

  return {
    title: {
      text: '费用占比',
      left: 'center',
      top: 10,
      textStyle: { fontSize: 14, color: '#333', fontWeight: 600 }
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: ¥{c} ({d}%)'
    },
    legend: {
      orient: 'horizontal',
      bottom: 10,
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { fontSize: 12 }
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderRadius: 6,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: true,
        formatter: '{b}\n¥{c}',
        fontSize: 11
      },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold' },
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.3)' }
      },
      data
    }]
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
  pieChart?.resize()
  barChart?.resize()
}

onMounted(() => {
  initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  barChart?.dispose()
})

watch(() => props.budget, () => {
  if (pieChart) pieChart.setOption(getPieOption())
  if (barChart) barChart.setOption(getBarOption())
}, { deep: true })
</script>

<style scoped>
.budget-chart-container {
  width: 100%;
}

.chart-row {
  display: flex;
  gap: 16px;
}

.chart-item {
  flex: 1;
  min-width: 0;
}

.chart-box {
  width: 100%;
  height: 300px;
}
</style>

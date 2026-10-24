<template>
  <div class="budget-chart-container">
    <div ref="barChartRef" class="chart-box"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { Budget } from '@/types'
import {useTheme} from '@/composables/useTheme'
const {resolvedTheme}=useTheme()

const props = defineProps<{
  budget: Budget
}>()

const barChartRef = ref<HTMLElement>()
let barChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | undefined

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
  const colors = ['#8a9da3', '#9aa58c', '#c6ac82', '#a18d7a']

  const dark=resolvedTheme.value==='dark'
  const text=dark?'#c7c9cb':'#555b62'
  const grid=dark?'#42464b':'#e0e2e5'

  return {
    title: {
      text: '已知费用预估构成',
      left: 'center',
      top: 10,
      textStyle: { fontSize: 14, color: text, fontWeight: 600 }
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
      axisLabel: { fontSize: 11, color: text },
      axisLine: {lineStyle:{color:grid}}
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '¥{value}', fontSize: 11, color:text },
      splitLine: {lineStyle:{color:grid}}
    },
    series: [
      {
        name: '已知费用预估',
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
          color: text
        }
      },
    ]
  }
}

const handleResize = () => {
  if (barChartRef.value?.clientWidth) barChart?.resize()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
  if (typeof ResizeObserver !== 'undefined' && barChartRef.value) {
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(barChartRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  resizeObserver?.disconnect()
  barChart?.dispose()
})

watch(() => props.budget, () => {
  if (barChart) barChart.setOption(getBarOption(), true)
}, { deep: true })
watch(resolvedTheme,()=>barChart?.setOption(getBarOption(),true))
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

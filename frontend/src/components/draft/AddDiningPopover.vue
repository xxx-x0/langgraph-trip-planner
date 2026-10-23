<template>
  <a-popover trigger="click" placement="bottom" v-model:open="open">
    <template #content>
      <div class="dining-picker">
        <p>先选用餐时段，再比较位置和价格。选择后会核对实际路线与营业时间。</p>
        <label>用餐时段 <select v-model="slot" aria-label="用餐时段"><option value="lunch">午餐</option><option value="dinner">晚餐</option></select></label>
        <label>筛选 <select v-model="style" aria-label="用餐位置偏好"><option value="all">全部备选</option><option value="on_route">附近少绕路</option><option value="dedicated">考虑专程前往</option></select></label>
        <a-tabs v-model:activeKey="activeCat" size="small">
          <a-tab-pane v-for="cat in categories" :key="cat" :tab="catLabel[cat]">
            <div v-for="c in options(cat)" :key="c.poi_id || c.name" class="candidate">
              <strong>{{ c.name }}</strong>
              <p>{{ c.cuisine || '菜系未提供' }} · {{ c.avg_cost != null ? `参考 ¥${c.avg_cost}/人` : '人均待确认' }}<span v-if="c.rating"> · 高德 {{ c.rating }}</span></p>
              <p v-if="match(c)">{{ match(c).before ? `从${match(c).before}出发` : '出发位置待确认' }}<span v-if="match(c).after">，之后去{{ match(c).after }}</span>；{{ match(c).distance_km != null ? `直线约${match(c).distance_km}公里` : '距离未知' }}</p>
              <p v-if="match(c)?.extra_walk_minutes != null">{{ match(c).after ? '比直达多走' : '往返' }}约 {{ match(c).extra_walk_minutes }} 分钟（直线按步行折算，非导航）</p>
              <p v-if="match(c)?.hours_fit === false" role="alert">当前参考用餐时段与已知营业时间不匹配</p>
              <p v-if="intent?.meal_budget_per_person && c.avg_cost != null && c.avg_cost > intent.meal_budget_per_person">高于本次每人每餐 {{ intent.meal_budget_per_person }} 元的预算</p>
              <p v-for="reason in c.recommendation?.reasons" :key="reason">{{ reason }}</p>
              <details><summary>营业与待确认事项</summary><p>{{ c.open_hours || '营业时间未知' }}</p><p v-for="note in c.recommendation?.cautions" :key="note">{{ note }}</p></details>
              <small>{{ c.recommendation?.source || '来源未记录' }} · {{ c.recommendation?.queried_at ? new Date(c.recommendation.queried_at).toLocaleString('zh-CN') : '查询时间未记录' }}</small>
              <a-button block @click="onPick(cat, c)" :disabled="disabled || match(c)?.hours_fit === false">{{ replaceName ? '换成这家' : '加入用餐安排' }}</a-button>
            </div>
            <a-empty v-if="!options(cat).length" description="没有匹配的备选，试试全部备选或自定义" />
            <a-divider />
            <a-input v-model:value="customName" :placeholder="`自定义${catLabel[cat]}名称，价格与位置待补充`" />
            <a-button block @click="onPickCustom(cat)" :disabled="disabled || !customName.trim()">使用自定义餐厅</a-button>
          </a-tab-pane>
        </a-tabs>
      </div>
    </template>
    <a-button size="small" :disabled="disabled">{{ replaceName ? '换一家' : '+ 选餐厅' }}</a-button>
  </a-popover>
</template>
<script setup lang="ts">
import { ref } from 'vue'
const props = defineProps<{ pool: any; insertAfter?: string; intent?: any; replaceName?: string; preferredSlot?: string; disabled?: boolean; excludedNames?: string[] }>()
const emit = defineEmits<{ (e: 'add', meal: any): void }>()
const open = ref(false)
const categories = ['main', 'snack', 'dessert', 'cafe', 'late_night']
const catLabel: Record<string, string> = { main: '正餐', snack: '小吃', dessert: '甜品', cafe: '咖啡', late_night: '夜宵' }
const activeCat = ref('main'), customName = ref(''), slot = ref(props.preferredSlot || 'lunch'), style = ref('all')
function match(c: any) { return c.recommendation?.matches?.find((m: any) => m.slot === slot.value) }
function options(cat: string) {
  return [...(props.pool[cat] || [])].filter(c => c.name !== props.replaceName && !(props.excludedNames || []).includes(c.name) && (style.value === 'all' || match(c)?.style === style.value)).sort((a,b) => {
    const cap = props.intent?.meal_budget_per_person
    const cuisinePenalty = (c: any) => props.intent?.dining_style === 'dedicated' && props.intent?.food_preference && c.cuisine?.includes(props.intent.food_preference) ? 0 : 1000
    const score = (c: any) => cuisinePenalty(c) + (match(c)?.hours_fit === false ? 100000 : 0) + (cap && (c.avg_cost == null || c.avg_cost > cap) ? 10000 : 0) + (match(c)?.extra_walk_minutes ?? 999)
    return score(a)-score(b)
  }).slice(0,3)
}
function onPick(cat: string, c: any) {
  emit('add', { ...c, category: cat, type: cat === 'main' ? slot.value : cat,
    preferred_slot: cat === 'main' ? slot.value : undefined, schedule_mode: 'manual',
    insert_after: props.insertAfter || match(c)?.before || 'hotel_start' })
  open.value = false
}
function onPickCustom(cat: string) {
  onPick(cat,{ name: customName.value.trim(), source:'user_custom' }); customName.value=''
}
</script>
<style scoped>
.dining-picker { width: min(360px, calc(100vw - 48px)); max-height: 70vh; overflow-y: auto; }
.dining-picker label { display: block; margin: 8px 0; }
.candidate { padding: 12px 4px; border-bottom: 1px solid #ddd; overflow-wrap: anywhere; }
.candidate p { margin: 6px 0; }
.candidate small { display: block; margin: 8px 0; }
</style>

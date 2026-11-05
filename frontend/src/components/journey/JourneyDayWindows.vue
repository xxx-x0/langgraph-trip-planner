<template>
  <div class="day-windows">
    <component :is="interactive?'button':'article'" v-for="(day,index) in days" :key="day.date" :type="interactive?'button':undefined"
      class="window-card" :class="{active:activeDate===day.date}" :aria-expanded="interactive?activeDate===day.date:undefined"
      :aria-label="interactive?`查看${day.date}的时间安排`:undefined" @click="interactive&&emit('select',day.date)">
      <div class="window-top"><span>第 {{day.dayNumber||index+1}} 天 <small>{{dateLabel(day.date)}}</small></span><span class="window-detail">{{interactive?(activeDate===day.date?'收起 ↑':'时间轴 ↗'):'游玩时间'}}</span></div>
      <strong>{{windowLabel(day.window)}}</strong>
      <div class="window-bar" aria-hidden="true"><span :style="barStyle(day.window)"></span></div>
      <div class="window-bottom"><span>{{day.window?.provisional?'时间暂定':day.window?.unavailable?'在途日':`含接驳预留${day.activityCount==null?'':` · ${day.activityCount} 个景点`}`}}</span><small>08 — 22 时</small></div>
    </component>
  </div>
</template>
<script setup lang="ts">
defineProps<{days:Array<{date:string;window?:Record<string,any>;activityCount?:number;dayNumber?:number}>;interactive?:boolean;activeDate?:string}>()
const emit=defineEmits<{(e:'select',date:string):void}>()
function dateLabel(value:string){return `${Number(value.slice(5,7))}月${Number(value.slice(8,10))}日`}
function clock(n:number){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
function windowLabel(w?:Record<string,any>){
  if(!w||w.provisional&&w.start_minutes==null&&w.end_minutes==null)return '抵离时间待定'
  const start=w.start_minutes??0,end=w.end_minutes??1440
  if(w.unavailable||end<=start)return '当天在途，暂不安排游玩'
  if(start>0&&end<1440)return `${clock(start)} — ${clock(end)} 可安排`
  if(start>0)return `${clock(start)} 后可安排`
  if(end<1440)return `${clock(end)} 前结束活动`
  return w.provisional?'全天暂可安排':'全天可安排活动'
}
function barStyle(w?:Record<string,any>){const start=Math.max(480,Math.min(1320,w?.start_minutes??480)),end=Math.max(start,Math.min(1320,w?.end_minutes??1320));return {left:`${(start-480)/840*100}%`,width:`${w?.unavailable?0:(end-start)/840*100}%`}}
</script>
<style scoped>
.day-windows{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.window-card{display:flex;flex-direction:column;text-align:left;gap:13px;min-width:0;padding:17px 18px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-bg-primary);font:inherit;color:var(--color-text-primary)}button.window-card{cursor:pointer;transition:border-color .18s,background .18s}button.window-card:hover,.window-card.active{border-color:var(--color-primary);background:color-mix(in srgb,var(--color-primary) 4%,var(--color-bg-primary))}.window-top,.window-bottom{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:12px}.window-top>span:first-child{font-weight:500}.window-top small{font-size:11px;color:var(--color-text-secondary);margin-left:8px;font-weight:400}.window-detail{font-size:11px;color:var(--color-primary)}.window-card strong{font-size:16px;font-weight:500;font-variant-numeric:tabular-nums}.window-bar{height:5px;border-radius:10px;position:relative;background:var(--color-bg-tertiary);overflow:hidden}.window-bar span{position:absolute;height:100%;border-radius:10px;background:var(--window-accent,#728d7c)}.window-bottom{font-size:11px;color:var(--color-text-secondary)}.window-bottom small{font-size:9px;white-space:nowrap;opacity:.7}:focus-visible{outline:2px solid var(--color-primary);outline-offset:3px}@media(max-width:550px){.day-windows{grid-template-columns:1fr}.window-card{gap:11px}}
</style>

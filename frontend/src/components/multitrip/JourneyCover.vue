<template>
  <div class="journey-cover" aria-label="旅行路线">
    <Transition name="cover-photo"><img v-if="photo && failedPhoto!==photo" :key="photo" class="cover-photo" :src="photo" alt="" referrerpolicy="no-referrer" @error="failedPhoto=photo" /></Transition><div class="cover-shade"></div><div class="cover-top"><span><i></i> YOUR JOURNEY</span><span>{{ days }} DAYS / {{ stops.length }} CITIES</span></div>
    <svg class="route-orbit" viewBox="0 0 600 180" fill="none" aria-hidden="true"><path d="M-20 150C140 150 120 20 280 55S440 180 620 30"/><path d="M-20 160C140 160 120 30 280 65S440 190 620 40"/></svg>
    <div class="cover-route">
      <button :disabled="!interactive" class="cover-end" @click="$emit('transport',0)"><span>出发</span><strong>{{ origin || '出发地' }}</strong><b>↗</b></button>
      <template v-for="(stop,i) in stops" :key="stop.id">
        <button class="route-connection" :disabled="!interactive" :aria-label="'查看第'+(i+1)+'段交通'" @click="$emit('transport',i)"><span>···</span></button>
        <button class="cover-city" :class="{selected:selected===stop.id}" :disabled="!interactive" :aria-label="'查看'+(stop.city.name || '待选城市')+'行程'" @click="$emit('select',stop.id)"><small>停留 0{{i+1}}</small><strong>{{stop.city.name || '待选城市'}}</strong><span>{{shortDate(stop.start_date)}} — {{shortDate(stop.end_date)}}</span></button>
      </template>
      <button :disabled="!interactive" class="cover-end return" @click="$emit('transport',stops.length)"><span>返程</span><strong>{{destination || '返家'}}</strong><b>↗</b></button>
    </div>
    <div class="cover-bottom"><span>{{interactive?'选择一站，或探索两城之间的路':'把目的地连起来，旅程就开始了'}}</span><span>路线示意 · 非地图</span></div>
  </div>
</template>
<script setup lang="ts">
import {computed,ref} from 'vue'
const props=defineProps<{stops:any[];origin:string;destination:string;days:number|string;interactive:boolean;selected?:string;photos?:Record<string,string>}>()
const failedPhoto=ref('')
const photo=computed(()=>props.photos?.[props.selected||props.stops[0]?.id]||'')
defineEmits<{(e:'select',id:string):void;(e:'transport',index:number):void}>()
const shortDate=(date:string)=>date?.slice(5).replace('-','.') || '待定'
</script>
<style scoped>
.journey-cover{position:relative;isolation:isolate;overflow:hidden;min-height:245px;color:#f7f2ec;padding:25px 26px;border-radius:24px;border:1px solid #ffffff20;background:linear-gradient(135deg,#ffffff12,#ffffff03);box-shadow:inset 0 1px #ffffff12;display:flex;flex-direction:column;justify-content:space-between}
.cover-top,.cover-bottom{display:flex;justify-content:space-between;gap:12px;color:#b9b4b0;font-size:10px;letter-spacing:.1em}.cover-top>span:first-child{display:flex;align-items:center;gap:8px}.cover-top i{height:5px;width:5px;border-radius:50%;background:#e4b88a;box-shadow:0 0 15px #f5bd77}.cover-bottom{letter-spacing:0;font-size:10px;line-height:1.6}.route-orbit{position:absolute;z-index:-1;inset:25px 0;width:100%;height:180px;stroke:#e9bf8c;stroke-width:.8;opacity:.22}.route-orbit path:last-child{opacity:.3}.route-orbit path{stroke-dasharray:900;animation:trace 1.2s cubic-bezier(.22,1,.36,1) both}.cover-route{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:24px 0}.cover-city,.cover-end,.route-connection{font:inherit;cursor:pointer;border:0;color:inherit;background:transparent;padding:12px 8px;min-width:0}.cover-city{display:flex;flex-direction:column;text-align:left;gap:10px;border-radius:14px;transition:background .25s,transform .3s;flex:1}.cover-city small{font-size:10px;color:#b9b4b0}.cover-city strong{font-size:32px;font-weight:500;letter-spacing:.05em}.cover-city span{font-size:10px;color:#c8c1b9;white-space:nowrap}.cover-city.selected,.cover-city:hover:not(:disabled){background:#ffffff0c;box-shadow:inset 0 0 0 1px #e8bf8a30}.cover-city:hover:not(:disabled){transform:translateY(-3px)}.cover-end{display:flex;flex-direction:column;gap:8px;font-size:11px}.cover-end span{font-size:9px;color:#aaa6a0}.cover-end strong{font-weight:400}.cover-end b{color:#e8bf8a;font-size:16px}.route-connection{color:#e8bf8a;font-size:20px;padding:10px 0}.cover-city:focus-visible,.cover-end:focus-visible,.route-connection:focus-visible{outline:2px solid #e8bf8a;outline-offset:3px}button:disabled{cursor:default}
@keyframes trace{from{stroke-dashoffset:900}to{stroke-dashoffset:0}}
@media(max-width:600px){.journey-cover{padding:20px 16px;min-height:210px}.cover-city strong{font-size:27px}.cover-route{gap:3px}.cover-city{padding:12px 6px}.cover-bottom{font-size:9px}.cover-top{font-size:9px}.cover-end{padding:10px 3px;font-size:10px}.return{display:none}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}.cover-city:hover:not(:disabled){transform:none}}

.cover-photo{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-3;opacity:.58}.cover-shade{position:absolute;inset:0;background:linear-gradient(100deg,#171b20c9,#171b2060),linear-gradient(0deg,#171b20b5,transparent 70%);z-index:-2}.cover-photo-enter-active,.cover-photo-leave-active{transition:opacity .65s ease,transform .8s ease}.cover-photo-enter-from,.cover-photo-leave-to{opacity:0;transform:scale(1.04)}.journey-cover .cover-city{background:#17191b36;backdrop-filter:blur(12px);border:1px solid #ffffff12}.journey-cover .cover-city.selected{background:#ffffff0d;border-color:#e8ba8844}.journey-cover .cover-end,.journey-cover .route-connection{background:transparent;border:0}.cover-top,.cover-bottom{color:#d4d1cb}
@media(prefers-reduced-motion:reduce){.cover-photo-enter-active,.cover-photo-leave-active{transition:none}.cover-photo-enter-from,.cover-photo-leave-to{transform:none}}
</style>
<style scoped>
.journey-cover .cover-city{padding:12px 8px}.journey-cover .cover-city strong{white-space:nowrap}.journey-cover .cover-end{padding:12px 5px}.journey-cover .route-connection{padding:10px 0}
@media(max-width:600px){.journey-cover .cover-route{overflow-x:auto;scrollbar-width:thin;padding-bottom:6px}.journey-cover .cover-city{padding:12px 9px;min-width:90px;flex:1 0 90px}.journey-cover .cover-end{flex:0 0 35px;padding:10px 0}.journey-cover .route-connection{flex:0 0 12px}.journey-cover .return{display:none}.cover-bottom{flex-wrap:wrap;gap:4px}}
</style>

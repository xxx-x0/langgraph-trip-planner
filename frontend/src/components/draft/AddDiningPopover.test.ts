import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AddDiningPopover from './AddDiningPopover.vue'
const stubs = {
  'a-popover': { template:'<div><slot name="content"/><slot/></div>' },
  'a-tabs': { template:'<div><slot/></div>' },
  'a-tab-pane': { template:'<div><slot/></div>' },
  'a-button': { props:['disabled'], template:'<button :disabled="disabled"><slot/></button>' },
}
const item=(name:string,minutes:number,fit=true)=>({name,category:'main',avg_cost:40,recommendation:{source:'高德地图 POI',queried_at:'2026-10-15T12:00:00Z',cautions:['排队时长未知'],matches:[{slot:'lunch',before:'园林',after:'博物馆',distance_km:1,extra_walk_minutes:minutes,style:'on_route',hours_fit:fit}]}})
describe('dining decisions',()=>{
 it('shows at most three alternatives with source, unknowns, estimated route and real anchors',()=>{
  const w=mount(AddDiningPopover,{props:{pool:{main:[item('远',50),item('近',2),item('第二',5),item('第三',8)]}},global:{stubs}})
  expect(w.findAll('.candidate strong').map(x=>x.text())).toEqual(['近','第二','第三'])
  expect(w.text()).toContain('直线按步行折算，非导航')
  expect(w.text()).toContain('园林')
  expect(w.text()).toContain('高德地图 POI')
  expect(w.text()).toContain('排队时长未知')
 })
 it('preserves provider facts and explicit meal slot when replacing',async()=>{
  const w=mount(AddDiningPopover,{props:{pool:{main:[item('旧店',0),item('新店',2)]},replaceName:'旧店',insertAfter:'园林'},global:{stubs}})
  await w.findAll('button').find(b=>b.text()==='换成这家')!.trigger('click')
  expect(w.emitted('add')?.[0]?.[0]).toMatchObject({name:'新店',avg_cost:40,insert_after:'园林',preferred_slot:'lunch',schedule_mode:'manual'})
 })
 it('disables a known closed window and all actions while saving',()=>{
  const w=mount(AddDiningPopover,{props:{pool:{main:[item('休息',0,false)]}},global:{stubs}})
  expect(w.findAll('button').find(b=>b.text()==='加入用餐安排')?.attributes('disabled')).toBeDefined()
 })
})


it('ranks within-cap meals ahead of a closer over-cap meal and excludes saved restaurants',()=>{
 const expensive={...item('贵但近',1),avg_cost:150}
 const cheap=item('预算内',20)
 const w=mount(AddDiningPopover,{props:{pool:{main:[expensive,cheap,item('已安排',0)]},intent:{meal_budget_per_person:50},excludedNames:['已安排']},global:{stubs}})
 expect(w.findAll('.candidate strong').map(x=>x.text())).toEqual(['预算内','贵但近'])
 expect(w.text()).toContain('高于本次每人每餐 50 元')
 w.unmount()
})

it('preserves an explicit dinner replacement slot and original anchor',async()=>{
 const c={...item('晚餐新店',5),recommendation:{matches:[{slot:'dinner',before:'别处',hours_fit:true}]}}
 const w=mount(AddDiningPopover,{props:{pool:{main:[c]},replaceName:'旧店',preferredSlot:'dinner',insertAfter:'原景点'},global:{stubs}})
 await w.findAll('button').find(b=>b.text()==='换成这家')!.trigger('click')
 expect(w.emitted('add')?.[0]?.[0]).toMatchObject({name:'晚餐新店',type:'dinner',preferred_slot:'dinner',insert_after:'原景点',schedule_mode:'manual'})
 w.unmount()
})

it('blocks all picker actions during a pending daily save',()=>{
 const w=mount(AddDiningPopover,{props:{pool:{main:[item('备选',0)]},disabled:true},global:{stubs}})
 expect(w.findAll('button').every(b=>b.attributes('disabled')!==undefined)).toBe(true)
 w.unmount()
})

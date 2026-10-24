import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Result from './Result.vue'
const io=vi.hoisted(()=>({capture:vi.fn(),save:vi.fn()}))
vi.mock('html2canvas',()=>({default:io.capture}))
vi.mock('jspdf',()=>({default:class {addImage(){} addPage(){} save=io.save}}))
vi.mock('vue-router',()=>({useRoute:()=>({query:{},params:{}}),useRouter:()=>({push:vi.fn(),replace:vi.fn()})}))
vi.mock('@/services/api',()=>({saveTripToHistory:vi.fn(),getTripDetail:vi.fn(),finalizeDraftStream:vi.fn()}))
vi.mock('@/composables/useTripLoader',()=>({useTripLoader:()=>({})}))
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text().includes(text))!
const plan={city:'测试城',start_date:'2026-11-01',end_date:'2026-11-02',days:[{date:'2026-11-01',attractions:[],meals:[]}],weather_info:[{date:'2026-11-01'}],budget:{total:0},journey:{origin_city:'甲城',return_city:'甲城',destination_timezone:'Asia/Shanghai',outbound:{departure_time:'2026-11-01T07:00',arrival_time:'2026-11-01T09:00',passengers:2,ticket_total:50,currency:'CNY'}}}
async function open(){sessionStorage.setItem('tripPlan',JSON.stringify(plan));const w=mount(Result,{global:{stubs:{'a-result':true,'a-button':true,'a-skeleton':true,'a-empty':true,'a-back-top':true,TabOverview:true,TabBudget:true,TabWeather:true,TabItinerary:{props:['expanded'],template:'<div>day</div>'},TabMap:{name:'TabMap',props:['visible'],template:'<div>map</div>'}}}});await flushPromises();return w}
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear()})
afterEach(()=>vi.restoreAllMocks())
it('exports every panel, activates the map and blocks a second export until capture finishes',async()=>{
 let complete:any;io.capture.mockReturnValue(new Promise(r=>complete=r));const w=await open()
 await button(w,'导出 PDF').trigger('click');await flushPromises()
 expect(w.findAll('.result-panel').every(p=>(p.element as HTMLElement).style.display!=='none')).toBe(true)
 expect(w.findComponent({name:'TabMap'}).props('visible')).toBe(true)
 expect(button(w,'导出图片').attributes('disabled')).toBeDefined()
 await button(w,'导出 PDF').trigger('click');await flushPromises();expect(io.capture).toHaveBeenCalledTimes(1)
 complete({width:800,height:1000,toDataURL:()=> 'data:image/png;base64,AA=='});await flushPromises()
 expect(io.save).toHaveBeenCalledTimes(1);expect(w.classes()).not.toContain('is-exporting');w.unmount()
})
it('restores native disclosure state and selected panel after a failed export',async()=>{
 io.capture.mockRejectedValue(new Error('capture failed'));const w=await open()
 await button(w,'往返交通').trigger('click');await flushPromises()
 const details=w.get('.journey-leg details').element as HTMLDetailsElement;details.open=true
 await button(w,'导出 PDF').trigger('click');await flushPromises()
 expect(details.open).toBe(true)
 expect(w.get('#result-panel-transport').isVisible()).toBe(true)
 expect(w.classes()).not.toContain('is-exporting');expect(io.save).not.toHaveBeenCalled();w.unmount()
})

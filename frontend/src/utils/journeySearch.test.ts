import {beforeEach,expect,it,vi} from 'vitest'
import {collectJourneyTickets} from './journeySearch'
import {startTicketSearch,cancelTicketSearch,getTicketSearch} from '@/services/api'
vi.mock('@/services/api',()=>({startTicketSearch:vi.fn(),cancelTicketSearch:vi.fn(async()=>({})),getTicketSearch:vi.fn()}))
const request:any={city:'北京',start_date:'2026-11-10',end_date:'2026-11-12',companions:{count:2},journey:{origin_city:'上海',return_city:'上海'}}
beforeEach(()=>vi.clearAllMocks())
it('queries both directions, serializes flights and keeps rail when flights need verification',async()=>{
 const flightOrder:string[]=[]
 vi.mocked(startTicketSearch).mockImplementation(async(body:any)=>{
  if(body.mode==='flight')flightOrder.push(body.direction)
  return {search_id:body.mode+body.direction,status:body.mode==='train'?'completed':'needs_action',candidates:body.mode==='train'?[{id:'real-field-fixture'}]:[],message:'站点需验证'}
 })
 const result=await collectJourneyTickets(request,'auto',new AbortController().signal,()=>{})
 expect(result.batches).toHaveLength(2);expect(flightOrder).toEqual(['outbound','inbound'])
 expect(result.notices.join('')).toContain('网站当前需要额外验证')
 expect(cancelTicketSearch).toHaveBeenCalledTimes(4)
 expect(vi.mocked(startTicketSearch).mock.calls.map(([b]:any)=>b.passengers)).toEqual([2,2,2,2])
 expect(getTicketSearch).not.toHaveBeenCalled()
})
it('cleans up jobs whose IDs arrive after cancellation and rejects late data',async()=>{
 const ends:Array<(v:any)=>void>=[]
 vi.mocked(startTicketSearch).mockImplementation(()=>new Promise(resolve=>ends.push(resolve)))
 const controller=new AbortController()
 const promise=collectJourneyTickets(request,'train',controller.signal,()=>{})
 controller.abort()
 ends.forEach((finish,i)=>finish({search_id:`late${i}`,status:'completed',candidates:[{id:'late'}]}))
 await expect(promise).rejects.toMatchObject({name:'AbortError'})
 expect(cancelTicketSearch).toHaveBeenCalledWith('late0');expect(cancelTicketSearch).toHaveBeenCalledWith('late1')
})

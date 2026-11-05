import {cancelTicketSearch, getTicketSearch, startTicketSearch} from '@/services/api'
import type {TripFormData} from '@/types'

export type JourneySearchMode = 'auto'|'train'|'flight'

function detail(error:any):string {
  const value=error?.response?.data?.detail
  return typeof value==='string'?value:Array.isArray(value)?value.map(v=>v.msg).join('；'):'本次查询未完成，可重新查票'
}
function aborted(signal:AbortSignal){if(signal.aborted)throw new DOMException('已停止查询','AbortError')}
function pause(signal:AbortSignal){
  return new Promise<void>((resolve,reject)=>{
    const stop=()=>{clearTimeout(timer);reject(new DOMException('已停止查询','AbortError'))}
    const timer=setTimeout(()=>{signal.removeEventListener('abort',stop);resolve()},800)
    signal.addEventListener('abort',stop,{once:true})
    if(signal.aborted)stop()
  })
}

/** Rail directions may run together. The existing flight reader owns one job at
 * a time, so flight directions run sequentially. Never open a login window. */
export async function collectJourneyTickets(request:TripFormData, mode:JourneySearchMode, signal:AbortSignal, progress:(text:string)=>void) {
  const batches:any[]=[], notices:string[]=[]
  const journey=request.journey!
  async function search(direction:'outbound'|'inbound',kind:'train'|'flight') {
    aborted(signal)
    if(journey[direction]?.booking_status==='booked')return
    const label=(direction==='outbound'?'去程':'返程')+(kind==='train'?'铁路':'航班')
    const query={mode:kind,direction,from_place:direction==='outbound'?journey.origin_city:request.city,
      to_place:direction==='outbound'?request.city:journey.return_city,date:direction==='outbound'?request.start_date:request.end_date,
      passengers:request.companions?.count||1}
    let id=''
    try {
      progress(`正在查询${label}，随后计算抵离后还能安排多少活动…`)
      // Let a start response return its ID even after cancellation, so the owned
      // server job can be cleaned up instead of leaking a browser/search task.
      let result=await startTicketSearch(query)
      id=result.search_id
      aborted(signal)
      const expires=Date.now()+60000
      while(result.status==='searching'){
        if(Date.now()>expires)throw new Error('search deadline')
        await pause(signal);aborted(signal)
        result=await getTicketSearch(id,signal)
      }
      if(result.status==='completed'&&result.candidates?.length){
        batches.push({query:{...query,priority:'balanced'},candidates:result.candidates})
        notices.push(`${label}读取 ${result.candidates.length} 条${result.sampled?'抽样候选':''}。`)
      }else notices.push(`${label}暂未取得可用候选。${result.status==='needs_action'?'网站当前需要额外验证，本次继续比较已取得的结果。':result.message||''}`)
    }catch(error:any){
      if(signal.aborted)throw new DOMException('已停止查询','AbortError')
      notices.push(`${label} ${detail(error)}`)
    }finally{if(id)await cancelTicketSearch(id).catch(()=>{})}
  }
  const rail=mode==='flight'?Promise.resolve():Promise.all([search('outbound','train'),search('inbound','train')])
  const flights=async()=>{if(mode!=='train'){await search('outbound','flight');await search('inbound','flight')}}
  const outcomes=await Promise.allSettled([rail,flights()])
  aborted(signal)
  for(const result of outcomes)if(result.status==='rejected')throw result.reason
  return {batches,notices}
}

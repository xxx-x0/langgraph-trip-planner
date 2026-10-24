import railStations from '@/data/railStations.json'

// Public 12306 station-name asset, captured 2026-10-16. No live fare API.
export const stations: Record<string, string> = railStations
// City-level codes (not individual airports). Unknown locations never silently
// become a different city; users can still copy conditions and use the website.
export const flightCities: Record<string, string> = {
  北京:'bjs',上海:'sha',广州:'can',深圳:'szx',杭州:'hgh',成都:'ctu',重庆:'ckg',
  西安:'sia',昆明:'kmg',武汉:'wuh',南京:'nkg',厦门:'xmn',长沙:'csx',青岛:'tao',威海:'weh',
  天津:'tsn',郑州:'cgo',海口:'hak',三亚:'syx',哈尔滨:'hrb',沈阳:'she',大连:'dlc',
  济南:'tna',福州:'foc',贵阳:'kwe',南宁:'nng',南昌:'khn',合肥:'hfe',太原:'tyn',
  兰州:'lhw',乌鲁木齐:'urc',银川:'inc',西宁:'xnn',拉萨:'lxa',长春:'cgq',呼和浩特:'het',
}
export interface TicketQuery {mode:'train'|'flight';direction:'outbound'|'inbound';from:string;to:string;date:string;passengers:number;adultPassengers?:number}
export function validDate(date:string):boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(Date.parse(date+'T00:00:00Z')) && new Date(date+'T00:00:00Z').toISOString().slice(0,10)===date
}
export function queryError(q:TicketQuery):string {
  if(!q.from.trim()||!q.to.trim())return '请填写出发地和目的地。'
  if(q.from.trim()===q.to.trim())return '出发地和目的地不能相同。'
  if(!validDate(q.date))return '请填写有效的出发日期。'
  if(!Number.isInteger(q.passengers)||q.passengers<1||q.passengers>20)return '同行人数请填写1至20人。'
  return ''
}
export function searchLink(q:TicketQuery):{url:string;prefilled:boolean;note:string} {
  const home=q.mode==='train'?'https://www.12306.cn/index/':'https://flights.ctrip.com/online/channel/domestic'
  if(queryError(q))return {url:home,prefilled:false,note:queryError(q)}
  if(q.mode==='train') {
    const normalize=(value:string)=>Object.prototype.hasOwnProperty.call(stations,value.trim())?value.trim():value.trim().replace(/[市站]$/,'')
    const from=normalize(q.from),to=normalize(q.to)
    if(!Object.prototype.hasOwnProperty.call(stations,from)||!Object.prototype.hasOwnProperty.call(stations,to))return {url:home,prefilled:false,note:'站名未匹配，请从提示中选择具体车站；也可复制条件后到12306填写。'}
    // 12306 splits the raw query on literal commas before decoding station names.
    // URLSearchParams encodes these separators as %2C, leaving e.g. 上海%2CSHH
    // in the visible input without a usable station code. Encode values only.
    const params=`linktypeid=dc&fs=${encodeURIComponent(from)},${stations[from]}&ts=${encodeURIComponent(to)},${stations[to]}&date=${q.date}&flag=N,N,Y`
    return {url:'https://kyfw.12306.cn/otn/leftTicket/init?'+params,prefilled:true,note:'携带日期与站点打开12306；人数及票种请在网站确认。超出预售期可能查不到车票。'}
  }
  const from=q.from.trim().replace(/市$/,''),to=q.to.trim().replace(/市$/,'')
  if(!Object.prototype.hasOwnProperty.call(flightCities,from)||!Object.prototype.hasOwnProperty.call(flightCities,to))return {url:home,prefilled:false,note:'该地点尚无已收录的航班城市代码，请选择提示中的城市，或复制条件后到携程填写。不会自动改成附近机场。'}
  // Only prefill the full party as adults when its composition is explicitly known.
  const adults=q.adultPassengers===q.passengers?q.adultPassengers:1
  return {url:`https://flights.ctrip.com/online/list/oneway-${flightCities[from]}-${flightCities[to]}?`+new URLSearchParams({depdate:q.date,cabin:'y_s_c_f',adult:String(adults),child:'0',infant:'0'}),prefilled:true,note:q.adultPassengers===q.passengers?`按 ${adults} 位成人传递查询条件；网站仍需核对人数与余票，列表每人起价不等于同行含税总额。`:'同行票种未明确，先打开1成人参考列表；请在网站核对成人、儿童和婴儿，列表价不计作同行总额。'}
}
export function queryText(q:TicketQuery):string {
  return `${q.direction==='outbound'?'去程':'返程'}${q.mode==='train'?'火车票':'机票'}查询\n出发日期：${q.date}\n出发地：${q.from.trim()}\n目的地：${q.to.trim()}\n同行人数：${q.passengers}人（成人/儿童/婴儿票种请另行确认）\n请核对到达日期、具体车站/机场、全体含税费用、行李和退改条件。`
}

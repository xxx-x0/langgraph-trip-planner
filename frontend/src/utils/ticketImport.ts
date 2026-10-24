import type {JourneyLeg} from '@/types'
import {stations,validDate} from './ticketSearch'
export interface TicketPreview {
  mode:'train'|'flight';service:string;from:string;to:string;departure:string;arrival:string
  passengers:number;amount:number|null;basis:'unknown'|'total'|'person';currency:string;seat:string;warnings:string[]
}
const pad=(v:string|number)=>String(v).padStart(2,'0')
const unique=(v:string[])=>[...new Set(v)]
const stationNames=Object.keys(stations).sort((a,b)=>b.length-a.length)
function shift(date:string,days:number):string {return new Date(Date.parse(date+'T00:00:00Z')+days*86400000).toISOString().slice(0,10)}
export function parseTicket(raw:string,mode:'train'|'flight',baseDate:string,passengers:number):TicketPreview {
  const p:TicketPreview={mode,service:'',from:'',to:'',departure:'',arrival:'',passengers,amount:null,basis:'unknown',currency:'CNY',seat:'',warnings:[]}
  if(!raw.trim()||raw.length>8000){p.warnings.push('请粘贴一段不超过8000字的车票文字。');return p}
  // Ignore identity/order/contact lines, URLs and long identifiers. No raw text
  // is returned, persisted, logged or sent to a model/server.
  const text=raw.normalize('NFKC').replace(/\r/g,'').split('\n').filter(l=>!/(身份证|证件号|订单号|订票人|乘客姓名|联系电话|手机号|电子客票号)/.test(l)).join('\n').replace(/https?:\/\/\S+/g,' ').replace(/\b\d{11,}[Xx]?\b/g,' ').replace(/[：]/g,':')
  const services=unique([...text.toUpperCase().matchAll(mode==='train'?/(?<![A-Z0-9])[GDCZTKYSL]\d{1,5}(?![A-Z0-9])/g:/(?<![A-Z0-9])(?=[A-Z0-9]{2}\d{3,4}(?![A-Z0-9]))[A-Z0-9]*[A-Z][A-Z0-9]*(?![A-Z0-9])/g)].map(m=>m[0]))
  if(services.length===1)p.service=services[0]
  if(services.length>1){p.warnings.push('检测到多个班次，请一次只导入一段交通。');return p}
  if(mode==='train'&&!p.service)p.service=text.match(/(?:车次|列车)\s*:?\s*(\d{4})(?!\d)/)?.[1]||''
  const places=text.match(/([\p{L}][\p{L}\d·（）() ]{0,40}?)\s*(?:→|->|—|至|到)\s*([\p{L}][\p{L}\d·（）() ]{0,40})/u)
  if(places){p.from=places[1].trim().replace(/^(?:出发地|出发站)\s*/, '');p.to=places[2].trim().replace(/\s+(?:[A-Z]{1,2}\d|\d).*$/,'').trim()}
  const from=text.match(/(?:出发站|出发机场|出发地)\s*:\s*([^\n,，;；]+)/),to=text.match(/(?:到达站|到达机场|目的地)\s*:\s*([^\n,，;；]+)/)
  if(from)p.from=from[1].trim().slice(0,120)
  if(to)p.to=to[1].trim().slice(0,120)
  if(!p.from&&!p.to&&mode==='train'){
    const found:{name:string;index:number}[]=[]
    let remaining=text
    for(const name of stationNames){const i=remaining.indexOf(name);if(i>=0){found.push({name,index:i});remaining=remaining.split(name).join(' '.repeat(name.length))}}
    found.sort((a,b)=>a.index-b.index)
    if(found.length===2){p.from=found[0].name;p.to=found[1].name}
  }
  const dates=[...text.matchAll(/(?:(20\d{2})[-年/])?(\d{1,2})[-月/](\d{1,2})日?(?!\d)/g)].map(m=>{
    if(!m[1])p.warnings.push('文字未写年份，预览沿用查询年份，请核对。')
    return `${m[1]||baseDate.slice(0,4)}-${pad(m[2])}-${pad(m[3])}`
  })
  let date=dates[0]||baseDate
  if(!dates.length)p.warnings.push('文字未写日期，预览沿用查询日期，请核对。')
  const times=[...text.matchAll(/(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)/g)].map(m=>`${pad(m[1])}:${m[2]}`)
  // A third unlabelled time may be duration or another leg; require correction.
  if(times.length===2&&validDate(date)){
    p.departure=`${date}T${times[0]}`
    let arrivalDate=dates[1]||''
    const offset=text.match(/\+\s*([1-6])\s*(?:天|日)?/)
    if(!arrivalDate&&(offset||/次日|翌日|第二天/.test(text)))arrivalDate=shift(date,offset?Number(offset[1]):1)
    if(!arrivalDate&&/当日|当天|同日/.test(text))arrivalDate=date
    if(!arrivalDate&&times[1]>times[0]){arrivalDate=date;p.warnings.push('到达日期未单独标注，暂按当日，请确认是否跨日。')}
    if(validDate(arrivalDate))p.arrival=`${arrivalDate}T${times[1]}`
    else p.warnings.push('到达可能跨日，请补充准确到达日期时间。')
  }else p.warnings.push('时间不完整或包含多个时间，请补充本段出发与到达时间。')
  const money=[...text.matchAll(/(?:[¥￥]\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)|(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*元)/g)]
  if(money.length===1&&!/(?:USD|HKD|EUR|美元|港币|欧元|\$)/i.test(text)){
    p.amount=Number((money[0][1]||money[0][2]).replace(/,/g,''))
    if(/总价|合计|总额|全体/.test(text))p.basis='total'
    else if(/每人|单价|[\/／]人/.test(text))p.basis='person'
  }else if(money.length||/\$|USD|EUR|HKD/i.test(text))p.warnings.push('存在多个金额或外币，请核对后填写本段金额和币种。')
  if(/儿童|婴儿|成人/.test(text)&&p.basis==='person')p.basis='unknown'
  const counts=unique([...text.matchAll(/(?<!\d)(\d{1,2})\s*(?:人|位)(?!民)/g)].map(m=>m[1]))
  if(counts.length===1&&Number(counts[0])>=1&&Number(counts[0])<=20)p.passengers=Number(counts[0])
  else p.warnings.push('同行人数沿用查询条件，请确认票价适用人数。')
  const seats=unique([...text.matchAll(/商务座|一等座|二等座|硬卧|软卧|硬座|无座|经济舱|公务舱|头等舱/g)].map(m=>m[0]))
  if(seats.length===1)p.seat=seats[0]
  p.warnings.push('只识别单段交通；时区默认中国标准时间，税费、行李、接驳和退改仍需核对。')
  p.warnings=unique(p.warnings)
  return p
}
export function previewError(p:TicketPreview):string {
  if(!p.from.trim()||!p.to.trim()||p.from===p.to)return '请填写不同的出发站／机场和到达站／机场。'
  if(p.from.length>120||p.to.length>120||p.service.length>60)return '站点或班次文字过长，请只保留必要信息。'
  const valid=(v:string)=>/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/.test(v)&&validDate(v.slice(0,10))
  if(!valid(p.departure)||!valid(p.arrival))return '请补全有效的出发与到达日期时间。'
  const duration=Date.parse(p.arrival+'+08:00')-Date.parse(p.departure+'+08:00')
  if(duration<=0||duration>7*86400000)return '到达须晚于出发且不超过7天；请核对跨日日期。'
  if(!Number.isInteger(p.passengers)||p.passengers<1||p.passengers>20)return '同行人数请填写1至20人。'
  if(!/^[A-Z]{3}$/.test(p.currency))return '请填写三位大写币种代码，例如CNY。'
  if(p.amount!==null&&(!Number.isFinite(p.amount)||p.amount<0||p.amount>10000000))return '请填写有效金额，未知可留空。'
  if(p.amount!==null&&p.basis==='unknown')return '请确认金额是每人单价还是全体总价，或清空金额。'
  if(p.amount!==null&&p.amount*(p.basis==='person'?p.passengers:1)>10000000)return '全体总额超过支持范围。'
  return ''
}
export function ticketLeg(p:TicketPreview,source:string,now=new Date()):JourneyLeg {
  const error=previewError(p);if(error)throw new Error(error)
  const amount=p.amount===null?null:Math.round(p.amount*(p.basis==='person'?p.passengers:1)*100)/100
  const stamp=new Date(now.getTime()+8*3600000).toISOString().slice(0,16)
  return {mode:p.mode,service_number:p.service.trim(),departure_station:p.from.trim(),arrival_station:p.to.trim(),departure_time:p.departure,arrival_time:p.arrival,departure_timezone:'Asia/Shanghai',arrival_timezone:'Asia/Shanghai',passengers:p.passengers,booking_status:'planned',price_source:amount===null?'unknown':'user_quote',price_note:`用户文字导入（${source}）；记录时间为导入时间，请再次核价`,quoted_at:stamp,ticket_total:amount,extras_total:null,currency:p.currency,seat_class:p.seat,connections:null,transfer_before_minutes:60,station_buffer_minutes:60,baggage_minutes:30,transfer_after_minutes:60,lodging_buffer_minutes:30}
}

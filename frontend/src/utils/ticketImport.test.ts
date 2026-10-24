import {describe,it,expect} from 'vitest'
import {parseTicket,previewError,ticketLeg} from './ticketImport'
import {searchLink,queryText,queryError,type TicketQuery} from './ticketSearch'
const sample='2026-10-20 上海虹桥 → 北京南 G8 08:00—12:26 二等座 每人661元'
const parse=(s=sample,n=2)=>parseTicket(s,'train','2026-10-20',n)
describe('ticket text import',()=>{
 it('imports a single train and calculates party fare only once',()=>{const p=parse();expect(p.from).toBe('上海虹桥');expect(p.to).toBe('北京南');expect(p.service).toBe('G8');expect(p.basis).toBe('person');expect(previewError(p)).toBe('');const l=ticketLeg(p,'12306',new Date('2026-10-16T08:00:00Z'));expect(l.ticket_total).toBe(1322);expect(l.quoted_at).toBe('2026-10-16T16:00');expect(l.booking_status).toBe('planned');expect(l.extras_total).toBeNull()})
 it('does not multiply a group total',()=>{const p=parse(sample.replace('每人661元','2人合计1322元'));expect(p.passengers).toBe(2);expect(ticketLeg(p,'12306').ticket_total).toBe(1322)})
 it('requires a price basis even for one traveller',()=>{const p=parse(sample.replace('每人',''),1);expect(p.basis).toBe('unknown');expect(previewError(p)).toContain('金额是每人');p.amount=null;expect(ticketLeg(p,'12306').price_source).toBe('unknown')})
 it('requires an arrival date for an unexplained backwards clock',()=>{const p=parse(sample.replace('08:00—12:26','23:00—06:26'));expect(p.arrival).toBe('');expect(previewError(p)).toContain('日期时间')})
 it('handles explicit next day and a new year without local timezone dependency',()=>{const p=parse(sample.replace('2026-10-20','2026-12-31').replace('08:00—12:26','23:00—次日06:26'));expect(p.arrival).toBe('2027-01-01T06:26')})
 it('handles two explicit full dates',()=>{const p=parse('出发站：上海\n到达站：北京\n2026年10月20日 23:00\n2026年10月22日 06:00\nT110\n合计600元');expect(p.arrival).toBe('2026-10-22T06:00')})
 it('does not pick the cheapest amount from several fares or add taxes itself',()=>{const p=parse(sample+' 税费20元');expect(p.amount).toBeNull();expect(p.warnings.join()).toContain('多个金额')})
 it('does not infer CNY from foreign fares',()=>{expect(parse(sample.replace('每人661元','USD 100')).amount).toBeNull()})
 it('rejects mixing multiple trains',()=>{const p=parse(sample+'\nG10 09:00—13:00');expect(p.departure).toBe('');expect(p.warnings.join()).toContain('多个班次')})
 it('requires review of mixed adult/child pricing',()=>{expect(parse(sample+' 2成人1儿童').basis).toBe('unknown')})
 it('drops identity data and does not return the source text',()=>{const p=parse(sample+'\n订单号：G123456789\n身份证：123456199901011234\n乘客姓名：测试姓名');expect(p.service).toBe('G8');expect(JSON.stringify(ticketLeg(p,'12306'))).not.toMatch(/1234561999|测试姓名|G123456789/)})
 it('parses a labelled flight but never assumes paid/confirmed',()=>{const p=parseTicket('2026-10-20 MU5101 上海虹桥机场 → 北京首都机场 08:00—10:30 经济舱 合计1200元 已支付','flight','2026-10-20',2);expect(p.service).toBe('MU5101');expect(p.to).toBe('北京首都机场');expect(ticketLeg(p,'携程').price_source).toBe('user_quote')})
 it('rejects invalid calendar dates and impossible durations',()=>{const p=parse(sample.replace('2026-10-20','2026-02-30'));expect(previewError(p)).toContain('日期时间');const good=parse();good.arrival='2026-10-20T07:00';expect(previewError(good)).toContain('到达须晚于')})
 it('keeps missing fields visible instead of inventing them',()=>{const p=parse('G8');expect(p.from).toBe('');expect(p.amount).toBeNull();expect(p.departure).toBe('')})
})
const q:TicketQuery={mode:'train',direction:'outbound',from:'上海虹桥',to:'北京南',date:'2026-10-20',passengers:2}
describe('public ticket search links',()=>{
 it('keeps literal 12306 separators for its raw-query parser',()=>{const url=searchLink(q).url;expect(url).not.toContain('%2C');const raw=new URL(url).search;const parts=raw.match(/[?&]fs=([^&]+)/)![1].split(',');expect(parts).toHaveLength(2);expect(decodeURIComponent(parts[0])).toBe('上海虹桥');expect(parts[1]).toBe('AOH');expect(raw).toContain('&flag=N,N,Y')})
 it('accepts a city suffix and keeps explicit station choices',()=>{const url=new URL(searchLink({...q,from:'上海市',to:'北京市'}).url);expect(url.searchParams.get('fs')).toBe('上海,SHH');expect(url.searchParams.get('ts')).toBe('北京,BJP');expect(new URL(searchLink({...q,from:'上海虹桥站'}).url).searchParams.get('fs')).toBe('上海虹桥,AOH')})
 it('encodes only validated station names and updates return conditions',()=>{const u=new URL(searchLink(q).url);expect(u.searchParams.get('fs')).toBe('上海虹桥,AOH');expect(u.searchParams.get('ts')).toBe('北京南,VNP');expect(u.searchParams.get('date')).toBe(q.date);const ret={...q,direction:'inbound' as const,from:q.to,to:q.from,date:'2026-10-22'};expect(queryText(ret)).toContain('返程');expect(queryText(ret)).toContain('同行人数：2人');expect(new URL(searchLink(ret).url).searchParams.get('date')).toBe(ret.date)})
 it('falls back without leaking arbitrary address or URL text',()=>{for(const from of ['上海某街123号','javascript:alert(1)','__proto__']){const l=searchLink({...q,from});expect(l.prefilled).toBe(false);expect(l.url).toBe('https://www.12306.cn/index/')}})
 it('builds flight city/date links with explicit passenger caveat',()=>{const l=searchLink({...q,mode:'flight',from:'上海市',to:'北京'});expect(l.prefilled).toBe(true);expect(l.url).toContain('oneway-sha-bjs?depdate=2026-10-20');expect(l.note).toContain('1成人');expect(searchLink({...q,mode:'flight',to:'苏州'}).prefilled).toBe(false)})
 it('rejects invalid date and passenger count',()=>{expect(queryError({...q,date:'2026-02-30'})).toContain('日期');expect(queryError({...q,passengers:0})).toContain('人数')})
})

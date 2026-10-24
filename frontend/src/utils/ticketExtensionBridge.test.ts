import {readFileSync} from 'node:fs'
import {runInNewContext} from 'node:vm'
import {resolve} from 'node:path'
import {describe,it,expect,vi} from 'vitest'
function setup(){
 const saved:any={},pages:any={10:{url:'http://localhost:5173/draft/a'}},sent:any[]=[],probe={active:true};let listener:any,removed:any
 const chrome={runtime:{onMessage:{addListener:(fn:any)=>listener=fn}},storage:{session:{get:async(k:any)=>k===null?{...saved}:{[k]:saved[k]},set:async(v:any)=>Object.assign(saved,v),remove:async(keys:any)=>{for(const k of Array.isArray(keys)?keys:[keys])delete saved[k]}}},tabs:{create:vi.fn(async()=>({id:20})),update:vi.fn(async(id:any,v:any)=>{pages[id]={...pages[id],...v}}),get:vi.fn(async()=>({})),sendMessage:vi.fn(async(id:any,m:any)=>{if(m.type==='ltp-delivery-probe')return {active:probe.active,origin:new URL(pages[id].url).origin};sent.push({id,m});return {received:true}}),onRemoved:{addListener:(fn:any)=>removed=fn}}}
 runInNewContext(readFileSync(resolve(process.cwd(),'../browser-extension/background.js'),'utf8'),{chrome,URL,Date})
 const call=(m:any,id=10,url=pages[id]?.url,frameId=0)=>new Promise<any>(resolve=>listener(m,{frameId,url,tab:{id}},resolve))
 const start={type:'ltp-start',requestId:'query-1',url:'https://kyfw.12306.cn/otn/leftTicket/init?fs=上海,SHH&ts=北京,BJP&date=2026-10-27',query:{mode:'train',date:'2026-10-27',passengers:2}}
 return {call,start,chrome,saved,sent,pages,removed,probe}
}
describe('extension request binding',()=>{
 it('advertises the packaged manifest version on the allowed app origin',async()=>{const s=setup();const manifest=JSON.parse(readFileSync(resolve(process.cwd(),'../browser-extension/manifest.json'),'utf8'));expect(await s.call({type:'ltp-ping'})).toEqual({version:manifest.version})})
 it('binds ticket results to the initiating app tab across worker restarts',async()=>{const s=setup();expect(await s.call(s.start)).toEqual({started:true});expect(s.saved['ticket-tab:20'].appTab).toBe(10);expect((await s.call({type:'ltp-session'},20)).query).toEqual(s.start.query);expect(await s.call({type:'ltp-results',candidates:[{id:'public-ticket'}]},20)).toEqual({received:true});expect(s.sent[0]).toEqual({id:10,m:{type:'ltp-result',requestId:'query-1',candidates:[{id:'public-ticket'}]}});expect(s.chrome.tabs.update).toHaveBeenLastCalledWith(10,{active:true})})
 it('rejects arbitrary sites, remote pages and subframes',async()=>{const s=setup();expect((await s.call({...s.start,url:'https://evil.example/path'})).error).toBeTruthy();expect((await s.call(s.start,10,'https://evil.example/path')).error).toBeTruthy();expect((await s.call(s.start,10,undefined,1)).error).toBeTruthy();expect(s.chrome.tabs.create).not.toHaveBeenCalled()})
 it('cannot collect normal browsing, changed routes or old dates',async()=>{const s=setup();expect((await s.call({type:'ltp-session'},20,s.start.url)).error).toBeTruthy();await s.call(s.start);expect((await s.call({type:'ltp-session'},20,s.start.url.replace('2026-10-27','2026-10-28'))).error).toBeTruthy();expect((await s.call({type:'ltp-session'},20,'https://kyfw.12306.cn/otn/confirmPassenger/initDc')).error).toBeTruthy()})
 it('removes a cancelled query and does not target a different app origin',async()=>{const s=setup();await s.call(s.start);s.pages[10].url='http://127.0.0.1:5173/draft/a';expect((await s.call({type:'ltp-results',candidates:[]},20)).error).toBeTruthy();s.pages[10].url='http://localhost:5173/draft/a';await s.call({type:'ltp-cancel',requestId:'query-1'});expect((await s.call({type:'ltp-session'},20)).error).toBeTruthy();expect(s.sent).toHaveLength(0)})
 it('cleans sessions on tab closure and rejects mismatched source mode',async()=>{const s=setup();expect((await s.call({...s.start,query:{...s.start.query,mode:'flight'}})).error).toBeTruthy();await s.call(s.start);await s.removed(10);expect(s.saved).toEqual({})})
 it('delivers without access to sensitive tab URL metadata',async()=>{const s=setup();await s.call(s.start);expect(await s.call({type:'ltp-results',candidates:[]},20)).toEqual({received:true});expect(s.chrome.tabs.get).not.toHaveBeenCalled();expect(s.chrome.tabs.sendMessage).toHaveBeenCalledWith(10,{type:'ltp-delivery-probe',requestId:'query-1'},{frameId:0})})
 it('rejects a stale query even while the original app tab still exists',async()=>{const s=setup();await s.call(s.start);s.probe.active=false;expect((await s.call({type:'ltp-results',candidates:[]},20)).error).toBeTruthy();expect(s.sent).toHaveLength(0)})
})

function contentBridge(){
 let pageListener:any,extensionListener:any
 const location={port:'15173',origin:'http://127.0.0.1:15173'},window={addEventListener:(_type:any,fn:any)=>pageListener=fn,postMessage:vi.fn()}
 const chrome={runtime:{id:'helper',sendMessage:vi.fn(async()=>({started:true})),onMessage:{addListener:(fn:any)=>extensionListener=fn}}}
 runInNewContext(readFileSync(resolve(process.cwd(),'../browser-extension/app-bridge.js'),'utf8'),{location,window,chrome})
 const page=(type:string,id:string)=>pageListener({source:window,origin:location.origin,data:{channel:'ltp-ticket-app-v1',type,requestId:id}})
 const extension=(type:string,id:string,sender='helper')=>{const reply=vi.fn();extensionListener({type,requestId:id},{id:sender},reply);return reply}
 return {page,extension,window}
}
describe('original page delivery attestation',()=>{
 it('attests only the currently active request and invalidates a cancellation',async()=>{const s=contentBridge();await s.page('ltp-start','new');expect(s.extension('ltp-delivery-probe','new')).toHaveBeenCalledWith({active:true,origin:'http://127.0.0.1:15173'});expect(s.extension('ltp-delivery-probe','old')).toHaveBeenCalledWith({active:false,origin:'http://127.0.0.1:15173'});await s.page('ltp-cancel','new');expect(s.extension('ltp-delivery-probe','new')).toHaveBeenCalledWith({active:false,origin:'http://127.0.0.1:15173'})})
 it('does not forward another extension or an old query into the app',async()=>{const s=contentBridge();await s.page('ltp-start','new');s.window.postMessage.mockClear();s.extension('ltp-result','old');s.extension('ltp-result','new','another-extension');expect(s.window.postMessage).not.toHaveBeenCalled();expect(s.extension('ltp-result','new')).toHaveBeenCalledWith({received:true})})
})

it('rejects a same-day rail navigation that changes either endpoint before collection or delivery',async()=>{
 const s=setup();await s.call(s.start)
 for(const url of [s.start.url.replace('上海,SHH','杭州,HZH'),s.start.url.replace('北京,BJP','南京,NJH')]){
  expect((await s.call({type:'ltp-session'},20,url)).error).toBeTruthy()
  expect((await s.call({type:'ltp-results',candidates:[{id:'wrong-route'}]},20,url)).error).toBeTruthy()
 }
 expect(s.sent).toHaveLength(0)
})

// Sessions live only in browser session storage. No cookies, orders, account
// pages, arbitrary URLs, network fetches or payment actions are exposed.
const localApp = value => {
  try {const u=new URL(value);return u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)&&['5173','4173','15173'].includes(u.port)}catch{return false}
}
const allowedSite = value => {
  try {const u=new URL(value);return u.protocol==='https:'&&((u.hostname==='kyfw.12306.cn'&&u.pathname==='/otn/leftTicket/init')||(u.hostname==='flights.ctrip.com'&&/^\/online\/list\/oneway-[a-z]{3}-[a-z]{3}$/.test(u.pathname)))}catch{return false}
}
const key = id => 'ticket-tab:'+id
const ttl=15*60*1000
chrome.runtime.onMessage.addListener((m,sender,reply)=>{
  ;(async()=>{
    if(sender.frameId!==0||!sender.tab?.id)return {error:'仅支持顶层查询页'}
    if(m.type==='ltp-ping'&&localApp(sender.url))return {version:'0.2.2'}
    if(m.type==='ltp-start'&&localApp(sender.url)){
      if(!/^[a-zA-Z0-9-]{1,80}$/.test(m.requestId)||!allowedSite(m.url))return {error:'查询地址无效'}
      const u=new URL(m.url),q=m.query
      if(!q||!['train','flight'].includes(q.mode)||!/^\d{4}-\d{2}-\d{2}$/.test(q.date)||!Number.isInteger(q.passengers)||q.passengers<1||q.passengers>20)return {error:'查询条件无效'}
      if((q.mode==='train')!==(u.hostname==='kyfw.12306.cn'))return {error:'方式不匹配'}
      if(u.searchParams.get(q.mode==='train'?'date':'depdate')!==q.date)return {error:'查询日期不匹配'}
      // Open inactive first, bind before activating so document_idle cannot race.
      const tab=await chrome.tabs.create({url:'about:blank',active:false})
      const saved={appTab:sender.tab.id,appOrigin:new URL(sender.url).origin,requestId:m.requestId,url:u.href,query:q,created:Date.now()}
      const all=await chrome.storage.session.get(null)
      const expired=Object.entries(all).filter(([k,v])=>k.startsWith('ticket-tab:')&&(Date.now()-v.created>ttl||v.appTab===sender.tab.id)).map(([k])=>k)
      if(expired.length)await chrome.storage.session.remove(expired)
      await chrome.storage.session.set({[key(tab.id)]:saved})
      await chrome.tabs.update(tab.id,{url:u.href,active:true})
      return {started:true}
    }
    if(m.type==='ltp-cancel'&&localApp(sender.url)){
      const all=await chrome.storage.session.get(null)
      const keys=Object.entries(all).filter(([k,v])=>k.startsWith('ticket-tab:')&&v.appTab===sender.tab.id&&v.requestId===m.requestId).map(([k])=>k)
      if(keys.length)await chrome.storage.session.remove(keys)
      return {cancelled:true}
    }
    const saved=(await chrome.storage.session.get(key(sender.tab.id)))[key(sender.tab.id)]
    if(!saved||Date.now()-saved.created>ttl||!allowedSite(sender.url))return {error:'查询已过期，请从旅行规划重新发起'}
    // Navigation to a different route/date must never inherit the old request.
    const actual=new URL(sender.url),expected=new URL(saved.url)
    if(actual.origin+actual.pathname!==expected.origin+expected.pathname||actual.searchParams.get(saved.query.mode==='train'?'date':'depdate')!==saved.query.date)return {error:'网站查询条件已改变，请从应用重新查询'}
    if(saved.query.mode==='train'&&['fs','ts'].some(k=>actual.searchParams.get(k)!==expected.searchParams.get(k)))return {error:'网站查询条件已改变，请从应用重新查询'}
    if(m.type==='ltp-session')return {query:saved.query,url:saved.url}
    if(m.type==='ltp-results'){
      if(!Array.isArray(m.candidates)||m.candidates.length>80)return {error:'候选过多或格式无效'}
      // tabs.Tab.url is absent without tabs/host permissions. Ask the original
      // top-level content script to attest its origin and active query instead.
      let app
      try {app=await chrome.tabs.sendMessage(saved.appTab,{type:'ltp-delivery-probe',requestId:saved.requestId},{frameId:0})}
      catch{return {error:'原规划页已关闭或离开，请从规划页重新查询'}}
      if(!app?.active||app.origin!==saved.appOrigin)return {error:'原规划页或查询已改变，请从规划页重新查询'}
      const delivered=await chrome.tabs.sendMessage(saved.appTab,{type:'ltp-result',requestId:saved.requestId,candidates:m.candidates,...(m.status==='empty'&&m.candidates.length===0?{status:'empty'}:{})},{frameId:0})
      if(!delivered?.received)return {error:'原查询已失效，请从规划页重新查询'}
      await chrome.tabs.update(saved.appTab,{active:true})
      return {received:true}
    }
    return {error:'不支持的操作'}
  })().then(reply,()=>reply({error:'连接未完成，请回到规划页重新查询'}))
  return true
})
chrome.tabs.onRemoved.addListener(async id=>{
  const all=await chrome.storage.session.get(null)
  const keys=Object.entries(all).filter(([k,v])=>k===key(id)||v.appTab===id).map(([k])=>k)
  if(keys.length)await chrome.storage.session.remove(keys)
})

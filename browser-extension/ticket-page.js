;(async()=>{
  const session=await chrome.runtime.sendMessage({type:'ltp-session'})
  if(!session?.query)return // Normal browsing is never collected.
  const {query,url}=session
  const panel=document.createElement('div'),status=document.createElement('span'),button=document.createElement('button')
  panel.style.cssText='position:fixed;bottom:18px;right:18px;z-index:2147483647;padding:14px;background:#f2f6f3;color:#183d29;border:2px solid #365b43;border-radius:8px;max-width:360px;font:14px/1.6 sans-serif;box-shadow:0 3px 12px #0003'
  button.textContent='重新带回当前列表';button.style.cssText='margin-left:8px;cursor:pointer;padding:6px'
  status.textContent='旅行规划正在等待本次查询结果…';panel.append(status,button);document.body.append(panel)
  let sent='',queried=false,timer,stopped=false,collecting=false
  async function read(manual=false){
    if(stopped||collecting||(!manual&&sent==='candidates'))return
    let candidates=query.mode==='train'?LtpTicketReader.rail(document,query,url):LtpTicketReader.flights(document,query,url)
    if(query.mode==='flight'&&candidates.length){
      collecting=true;button.disabled=true;status.textContent='正在加载更多航班，覆盖不同出发时段；完成后自动带回…'
      try{candidates=await LtpTicketReader.collectFlights(document,query,url,window,ms=>new Promise(resolve=>setTimeout(resolve,ms)),()=>!stopped)}
      finally{collecting=false;button.disabled=stopped}
    }
    if(stopped)return
    if(!candidates.length){
      if(LtpTicketReader.empty(document,query,url)&&sent!=='empty'){
        sent='empty'
        await chrome.runtime.sendMessage({type:'ltp-results',status:'empty',candidates:[]})
        status.textContent='网站未返回航班候选；请核对条件、重试查询或完成网站登录后重新带回。'
      }else if(manual)status.textContent='未读取到匹配的直达候选，请核对本次日期/城市，等待列表加载或回应用重查。'
      return
    }
    sent='candidates'
    const result=await chrome.runtime.sendMessage({type:'ltp-results',candidates})
    status.textContent=result?.received?`已带回当前列表${candidates.length}条候选，请回规划页查看推荐。`:(result?.error||'带回失败，请回应用重查。')
  }
  button.addEventListener('click',()=>read(true))
  const observer=new MutationObserver(()=>{
    if(sent==='candidates'||stopped)return
    clearTimeout(timer)
    timer=setTimeout(()=>read(),1600)
    if(query.mode==='train'&&!queried&&document.querySelector('#train_date')?.value===query.date&&document.querySelector('#query_ticket')){
      queried=true;document.querySelector('#query_ticket').click()
    }
  })
  observer.observe(document.body,{childList:true,subtree:true})
  await read()
  if(query.mode==='train'&&!sent){queried=true;document.querySelector('#query_ticket')?.click()}
  setTimeout(()=>{if(!sent)status.textContent='尚未读到结果：请完成网站查询/验证后点击重新带回；网站结构变化时可回应用使用手动导入。'},45000)
  setTimeout(()=>{stopped=true;observer.disconnect();clearTimeout(timer);button.disabled=true;status.textContent='本次连接已过期，请从旅行规划重新查询。'},15*60*1000)
})().catch(()=>{/* A closed extension session must not interfere with the site. */})

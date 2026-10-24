if(['5173','4173','15173'].includes(location.port)){
  let activeRequestId=''
  window.addEventListener('message',async event=>{
    if(event.source!==window||event.origin!==location.origin||event.data?.channel!=='ltp-ticket-app-v1')return
    const m=event.data
    if(!['ltp-ping','ltp-start','ltp-cancel'].includes(m.type))return
    if(m.type==='ltp-start')activeRequestId=m.requestId
    if(m.type==='ltp-cancel'&&activeRequestId===m.requestId)activeRequestId=''
    try {
      const result=await chrome.runtime.sendMessage({type:m.type,requestId:m.requestId,url:m.url,query:m.query})
      window.postMessage({channel:'ltp-ticket-extension-v1',type:m.type+'-reply',requestId:m.requestId,...result},location.origin)
    }catch{window.postMessage({channel:'ltp-ticket-extension-v1',type:'ltp-error',requestId:m.requestId,error:'扩展已更新，请刷新规划页'},location.origin)}
  })
  chrome.runtime.onMessage.addListener((m,sender,reply)=>{
    if(sender.id!==chrome.runtime.id)return
    if(m.type==='ltp-delivery-probe'){reply({active:!!activeRequestId&&activeRequestId===m.requestId,origin:location.origin});return}
    if(m.type==='ltp-result'&&activeRequestId===m.requestId){window.postMessage({channel:'ltp-ticket-extension-v1',...m},location.origin);reply({received:true})}
  })
}

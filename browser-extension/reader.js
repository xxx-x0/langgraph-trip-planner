// Only list-specific DOM fields are read. Never export HTML, body text or
// attributes containing booking tokens. Shared verbatim by fixture tests.
globalThis.LtpTicketReader = (()=>{
  const text=(node,sel)=>node.querySelector(sel)?.textContent.trim()||''
  const arrival=(date,dep,arr,duration)=>{
    if(!/^\d{2}:\d{2}$/.test(dep)||!/^\d{2}:\d{2}$/.test(arr))return ''
    const instant=new Date(date+'T'+dep+':00Z').getTime()+duration*60000
    const iso=new Date(instant).toISOString()
    return iso.slice(11,16)===arr?iso.slice(0,16):''
  }
  const spread=items=>{const sorted=items.sort((a,b)=>a.departure.localeCompare(b.departure));return sorted.length<=80?sorted:Array.from({length:80},(_,i)=>sorted[Math.floor(i*(sorted.length-1)/79)])}
  function rail(doc,q,url){
    const u=new URL(url)
    if(doc.querySelector('#train_date')?.value!==q.date||doc.querySelector('#fromStationText')?.value!==u.searchParams.get('fs')?.split(',')[0]||doc.querySelector('#toStationText')?.value!==u.searchParams.get('ts')?.split(',')[0])return []
    const result=[]
    for(const row of doc.querySelectorAll('#queryLeftTable > tr[id^="ticket_"]')){
      const service=text(row,'a.number'),from=text(row,'.cdz strong:first-child'),to=text(row,'.cdz strong:last-child')
      const dep=text(row,'.cds strong:first-child'),arr=text(row,'.cds strong:last-child'),duration=text(row,'.ls strong')
      if(!/^[GDCZTKYSL]?\d{1,5}$/.test(service)||!from||!to||!/^\d{2}:\d{2}$/.test(duration))continue
      const [h,m]=duration.split(':').map(Number),end=arrival(q.date,dep,arr,h*60+m)
      if(!end)continue
      const stationSet=(id,prefix)=>new Set([...doc.querySelectorAll(id+' input[id]')].map(e=>e.id.slice(prefix.length).replace(/_check$/,'')))
      const fromStations=stationSet('#from_station_ul','cc_from_station_'),toStations=stationSet('#to_station_ul','cc_to_station_')
      if(fromStations.size&&!fromStations.has(from)||toStations.size&&!toStations.has(to))continue
      // Economy seated travel first; no-seat tickets are never a substitute.
      const seatCell=['ZE_','YZ_','YW_','YB_','ZY_','RW_'].map(prefix=>row.querySelector('td[id^="'+prefix+'"]')).find(e=>e&&(e.textContent.trim()==='有'||/^\d+$/.test(e.textContent.trim())&&Number(e.textContent.trim())>0))
      if(!seatCell)continue
      const label=seatCell.getAttribute('aria-label')||'',price=label.match(/票价(\d+(?:\.\d+)?)元/),seat=label.match(/，(.+?)票价/)?.[1]||''
      const count=seatCell.textContent.trim()
      result.push({id:'rail_'+result.length+'_'+service,mode:'train',service,from_station:from,to_station:to,departure:q.date+'T'+dep,arrival:end,seat,fare_per_person:price?Number(price[1]):null,availability:count==='有'||/^\d+$/.test(count)?'available':'unknown',source:'12306'})

    }
    return spread(result)
  }
  function matchesFlightQuery(doc,q,url){
    const u=new URL(url),inputs=[...doc.querySelectorAll('input[placeholder="可输入城市或机场"]')]
    const codes=u.pathname.match(/oneway-([a-z]{3})-([a-z]{3})$/)
    return doc.querySelector('input[placeholder="yyyy-mm-dd"]')?.value===q.date&&!!codes&&inputs.length===2&&inputs[0].value.toLowerCase().includes('('+codes[1]+')')&&inputs[1].value.toLowerCase().includes('('+codes[2]+')')
  }
  function flights(doc,q,url){
    if(!matchesFlightQuery(doc,q,url))return []
    const result=[]
    for(const card of doc.querySelectorAll('.flight-item.domestic .flight-box')){
      if(card.querySelectorAll('.depart-box').length!==1||card.querySelectorAll('.arrive-box').length!==1)continue
      const service=text(card,'.plane-No').match(/^([A-Z0-9]{2}\d{3,4})\b/)?.[1]
      if(!service||/中转|经停|转\d次/.test(text(card,'.arrow-box')))continue
      const dep=text(card,'.depart-box .time'),arr=text(card,'.arrive-box .time').match(/^\d{2}:\d{2}/)?.[0]
      const from=text(card,'.depart-box .airport .name'),to=text(card,'.arrive-box .airport .name')
      const day=text(card,'.arrive-box .day').match(/^\+([1-6])天?$/)
      if(text(card,'.arrive-box .day')&&!day)continue
      if(!dep||!arr||!from||!to)continue
      const endDate=new Date(Date.parse(q.date+'T00:00:00Z')+(day?Number(day[1]):0)*86400000).toISOString().slice(0,10)
      if(endDate+'T'+arr<=q.date+'T'+dep)continue
      const amount=text(card,'.flight-price .price').match(/[¥￥]\s*(\d+(?:\.\d+)?)/)
      result.push({id:'flight_'+result.length+'_'+service,mode:'flight',service,from_station:from,to_station:to,departure:q.date+'T'+dep,arrival:endDate+'T'+arr,seat:'经济舱列表起价，舱位待确认',fare_per_person:amount?Number(amount[1]):null,availability:'unknown',source:'ctrip'})

    }
    return spread(result)
  }
  function empty(doc,q,url){return q.mode==='flight'&&matchesFlightQuery(doc,q,url)&&text(doc,'.no-result-describe').includes('未找到符合条件的航班')}
  async function collectFlights(doc,q,url,view,pause,active=()=>true){
    const found=new Map(),x=view.scrollX,y=view.scrollY
    let stable=0,previous=''
    try{
      for(let round=0;round<16&&active();round++){
        if(!matchesFlightQuery(doc,q,url))return []
        for(const c of flights(doc,q,url))found.set([c.service,c.from_station,c.to_station,c.departure,c.arrival].join('|'),c)
        const cards=[...doc.querySelectorAll('.flight-item.domestic .flight-box')]
        const signature=cards.map(c=>text(c,'.depart-box .time')+'|'+text(c,'.plane-No')).join(';')
        stable=signature===previous?stable+1:0;previous=signature
        // The delivery cap is not a loading cap: even eighty visible morning
        // flights must not prevent checking later, virtualized result pages.
        if(stable>=3)break
        cards.at(-1)?.scrollIntoView?.({block:'end'})
        view.scrollBy(0,Math.max(500,view.innerHeight*.8))
        await pause(1100)
      }
      // A virtualized page can reuse row indices for another time/airport of
      // the same service. Assign batch IDs after merging and sampling.
      return active()&&matchesFlightQuery(doc,q,url)?spread([...found.values()]).map((c,i)=>({...c,id:'flight_'+i+'_'+c.service})):[]
    }finally{view.scrollTo(x,y)}
  }
  return {rail,flights,empty,collectFlights}
})()

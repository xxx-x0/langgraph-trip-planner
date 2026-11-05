type AttractionLike = {
  name: string
}

export function mergeDayAssignmentsWithSelected<T extends AttractionLike, U extends AttractionLike>(
  dayAssignments: U[][],
  selectedAttractions: T[],
): Array<Array<T & U>> {
  const selectedByName = new Map(selectedAttractions.map(attr => [attr.name, attr]))
  return dayAssignments.map(day =>
    day.map(attr => {
      const selected = selectedByName.get(attr.name)
      return selected ? ({ ...selected, ...attr } as T & U) : (attr as T & U)
    })
  )
}

// Empty city days can intentionally be rest days; an in-transit day never needs a POI.
export function hasUnsupportedEmptyDay(days: unknown[][], multiCity: boolean, unavailable: boolean[] = []): boolean {
  return days.some((day, index) => day.length === 0 && !multiCity && !unavailable[index])
}

export function reserveAssignmentWindows<T extends {name:string;visit_minutes?:number|null}>(days:T[][],windows:Array<{start_minutes?:number;end_minutes?:number;unavailable?:boolean}>):T[][]{
  const result:T[][]=windows.map(()=>[]),loads=windows.map(()=>0)
  const capacity=windows.map(w=>w.unavailable?0:Math.max(0,Math.min(1320,w.end_minutes??1440)-Math.max(480,w.start_minutes??0)))
  const overflow:T[][]=[]
  // Keep activities that still fit their original dates before relocating the
  // displaced group. A late arrival must not push every other day forward.
  days.forEach((items,source)=>{
    const moved:T[]=[]
    items.forEach(item=>{const minutes=(item.visit_minutes||90)+20
      if(source<capacity.length&&loads[source]+minutes<=capacity[source]){result[source].push(item);loads[source]+=minutes}
      else moved.push(item)
    });overflow.push(moved)
  })
  overflow.forEach(items=>{let target:number|undefined;items.forEach(item=>{
    const minutes=(item.visit_minutes||90)+20
    const choices=capacity.map((value,index)=>loads[index]+minutes<=value?index:-1).filter(index=>index>=0)
    if(!choices.length)return // The full selection remains available for the draft's pending catalog.
    if(target===undefined||!choices.includes(target))target=choices.sort((a,b)=>loads[a]/capacity[a]-loads[b]/capacity[b]||a-b)[0]
    result[target].push(item);loads[target]+=minutes
  })})
  return result
}

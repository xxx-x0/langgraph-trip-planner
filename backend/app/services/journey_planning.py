"""Reserve city capacity before placing attractions; no invented transport facts."""
import copy
import hashlib
from datetime import date, timedelta
from fastapi import HTTPException
from .journey_service import travel_window


def dates(request):
    return [(date.fromisoformat(request.start_date)+timedelta(days=i)).isoformat() for i in range(request.travel_days)]


def capacity(request, day):
    w=travel_window(request,day)
    return max(0,min(1320,w.get('end_minutes',1440))-max(480,w.get('start_minutes',0)))


def reserve_clusters(request, clusters, *, explicit=False):
    if not request.journey or not request.journey.planning:
        return clusters
    capacities=[capacity(request,d) for d in dates(request)]
    result=[[] for _ in capacities]
    loads=[0]*len(capacities)
    for source,group in enumerate(clusters):
        if explicit:
            if source>=len(capacities) or sum(a.get('visit_minutes') or a.get('visit_duration') or 120 for a in group)>capacities[source]:
                raise HTTPException(422, f'第{source+1}天的明确景点分配超出交通预留后的可用时间，请先修改日期分配或交通预留')
            result[source]=copy.deepcopy(group)
            continue
        target=None
        for item in group:
            visit=item.get('visit_minutes') or item.get('visit_duration') or 120
            # A skeleton allowance, not a verified route or meal schedule.
            candidates=[i for i,c in enumerate(capacities) if loads[i]+visit+20<=c]
            if not candidates: continue  # Retained in the draft's unassigned catalog.
            if target not in candidates:
                target=source if source in candidates and loads[source]==0 else min(candidates,key=lambda i:(loads[i]/capacities[i],i))
            result[target].append(copy.deepcopy(item));loads[target]+=visit+20
    return result


def pending_item(cluster, from_date=None, reason='交通预留后尚未分配，未核对路线及营业时间'):
    value=copy.deepcopy(cluster)
    ident=hashlib.sha256((str(value.get('poi_id',''))+'|'+value['name']).encode()).hexdigest()[:20]
    return dict(id=ident,name=value['name'],cluster=value,from_date=from_date,reason=reason)

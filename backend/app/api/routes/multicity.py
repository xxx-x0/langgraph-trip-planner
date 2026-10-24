"""Multi-city draft API: previews are pure, commits use one SQLite CAS transaction."""
import json
import uuid
from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from ...database import async_session
from ...models.multicity import MultiTrip
from ...models.db_models import TripDraft
from ...models.schemas import TripRequest
from ...services import multicity as svc

router=APIRouter(prefix='/multi-trips',tags=['multi-city'])

class Change(BaseModel):
    plan: MultiTrip
    revision: int = Field(ge=1)
    preview_token: str | None = None
    acknowledge_booked: bool = False
    ticket_basis: str | None = None
    adjust_days: bool = False
    adjustment_id: str | None = None
    acknowledge_adjustments: bool = False

class Revision(BaseModel):
    revision: int = Field(ge=1)

class ImportCity(Revision):
    draft_id: str
    basis: str


def stop_for(plan,stop_id):
    stop=next((s for s in plan.stops if s.id==stop_id),None)
    if not stop: raise HTTPException(404,'城市停留不存在')
    return stop

@router.get('')
async def listing():
    async with async_session() as s:
        rows=(await s.execute(select(TripDraft).where(func.json_extract(TripDraft.request_json,'$.kind')==svc.KIND).order_by(TripDraft.updated_at.desc()).limit(100))).scalars().all()
        return [dict(id=r.id,title=(d:=svc.document(r))['plan']['title'],status=d['status'],revision=d['revision'],start_date=d['plan']['start_date'],end_date=d['plan']['end_date'],cities=[x['city']['name'] for x in d['plan']['stops']]) for r in rows]

@router.post('')
async def create(plan:MultiTrip): return svc.response(await svc.create(plan))

@router.post('/compare')
async def compare(plan:MultiTrip): return {'options':svc.suggest(plan)}

@router.post('/rest-suggestions')
async def rest_suggestions(plan:MultiTrip): return svc.suggest_rest(plan)

@router.get('/{trip_id}')
async def get(trip_id:str): return svc.response(await svc.load(trip_id))

@router.post('/{trip_id}/preview')
async def preview(trip_id:str,body:Change):
    d=await svc.load(trip_id)
    if body.ticket_basis and body.ticket_basis != svc.token(d): raise HTTPException(409,'筛选后安排已改变，请重新查票')
    if d['revision']!=body.revision or d['status']=='saved': raise HTTPException(409,'版本已变化或已保存，请重新加载或创建新版本')
    old=MultiTrip.model_validate(d['plan']);changes,booked=svc.change_report(old,body.plan)
    if body.adjust_days:
        from ...services import transport_adjustment as adjustment
        plan,snapshots,adjustments,summary=await adjustment.propose(d,body.plan)
        if svc.token(await svc.load(trip_id)) != svc.token(d): raise HTTPException(409,'生成期间安排已改变，请重新预览')
        proposal_id=adjustment.remember(d,plan,snapshots,adjustments)
        _,booked=svc.change_report(old,plan)
        return dict(summary=summary,changes=changes,booked=booked,adjustments=adjustments,proposed_plan=plan.model_dump(mode='json'),adjustment_id=proposal_id,budget_delta=round(summary['budget']['total']-svc.projection(old,d['snapshots'])['budget']['total'],2),preview_token=svc.token([d,plan.model_dump(mode='json'),proposal_id]))
    summary=svc.projection(body.plan,d['snapshots']);before=svc.projection(old,d['snapshots'])
    return dict(summary=summary,changes=changes,booked=booked,budget_delta=round(summary['budget']['total']-before['budget']['total'],2),preview_token=svc.token([d,body.plan.model_dump(mode='json')]))

@router.put('/{trip_id}')
async def update(trip_id:str,body:Change):
    async def apply(d,session):
        expected=[d,body.plan.model_dump(mode='json')]
        if body.adjustment_id: expected.append(body.adjustment_id)
        if not body.preview_token or body.preview_token!=svc.token(expected): raise HTTPException(409,'预览已过期，请重新查看变更影响')
        _,booked=svc.change_report(MultiTrip.model_validate(d['plan']),body.plan)
        if booked and not body.acknowledge_booked: raise HTTPException(409,'涉及已订安排，请明确确认仅修改本地计划，不代表改签或退订')
        if body.adjustment_id:
            from ...services import transport_adjustment as adjustment
            if not body.acknowledge_adjustments: raise HTTPException(409,'请先核对并确认两城当天的调整与取消项')
            proposal=adjustment.resolve(body.adjustment_id,d,body.plan)
            d['snapshots']=proposal['snapshots']
        d['plan']=body.plan.model_dump(mode='json')
        svc.projection(body.plan,d['snapshots'])  # validate all cities before the only write
        return d
    return svc.response(await svc.write(trip_id,body.revision,apply))

@router.get('/{trip_id}/cities/{stop_id}/request')
async def city_input(trip_id:str,stop_id:str):
    d=await svc.load(trip_id);plan=MultiTrip.model_validate(d['plan']);stop=stop_for(plan,stop_id)
    request=svc.city_request(plan,stop)
    return dict(request=request.model_dump(mode='json'),days=[dict(date=day,window=svc.travel_window(request,day)) for day in svc.dates(date.fromisoformat(request.start_date),date.fromisoformat(request.end_date))],basis=svc.stop_basis(plan,stop),revision=d['revision'])

@router.post('/{trip_id}/cities/{stop_id}/import')
async def import_city(trip_id:str,stop_id:str,body:ImportCity):
    async def apply(d,session):
        plan=MultiTrip.model_validate(d['plan']);stop=stop_for(plan,stop_id)
        if body.basis!=svc.stop_basis(plan,stop): raise HTTPException(409,'这座城市的日期或交通已变化，请从整趟页面重新进入城市安排')
        row=await session.get(TripDraft,body.draft_id)
        if not row or row.id.startswith('mc_'): raise HTTPException(404,'城市草稿不存在')
        request=TripRequest.model_validate_json(row.request_json);expected=svc.city_request(plan,stop)
        fields=tuple(TripRequest.model_fields)
        if any(getattr(request,k)!=getattr(expected,k) for k in fields): raise HTTPException(409,'城市草稿的日期、人数或交通与整趟不一致；请先在整趟旅行确认变更')
        days=json.loads(row.days_detail_json)
        if len(days)!=request.travel_days: raise HTTPException(409,'城市每日数据不完整')
        expected_dates=svc.dates(date.fromisoformat(expected.start_date),date.fromisoformat(expected.end_date))
        for index,detail in enumerate(days):
            if detail is not None and (detail.get('day_index')!=index or detail.get('date')!=expected_dates[index]):
                raise HTTPException(409,'城市每日索引或日期与本次停留不一致，本次未同步')
        # The source is read in this same transaction, never supplied as arbitrary client JSON.
        editor_fields=('selected_attractions_json','macro_plan_json','clusters_data_json','hotels_by_day_json','dining_pool_json','weather_info_json')
        d['snapshots'][stop_id]=dict(draft_id=row.id,basis=body.basis,request=request.model_dump(mode='json'),days_detail=days,editor_data={k:getattr(row,k) for k in editor_fields})
        svc.projection(plan,d['snapshots'])
        return d
    return svc.response(await svc.write(trip_id,body.revision,apply))

@router.post('/{trip_id}/cities/{stop_id}/edit')
async def edit_city(trip_id:str,stop_id:str,body:Revision):
    # Clone the imported working copy. Parent and original city version remain intact.
    async with async_session() as session:
        await session.execute(text('BEGIN IMMEDIATE'))
        row=await session.get(TripDraft,trip_id)
        if not row: raise HTTPException(404,'旅行不存在')
        d=svc.document(row)
        if d['revision']!=body.revision or d['status']=='saved': raise HTTPException(409,'版本已变化或已保存，请重新加载')
        plan=MultiTrip.model_validate(d['plan']);stop=stop_for(plan,stop_id);snap=d['snapshots'].get(stop_id)
        if not snap: raise HTTPException(409,'尚无每日安排，请先选择景点')
        request=svc.city_request(plan,stop);old=TripRequest.model_validate(snap['request'])
        if any(getattr(old,k)!=getattr(request,k) for k in ('city','start_date','end_date','companions','hotel_occupancy')):
            raise HTTPException(409,'日期、城市或人数已变化。旧安排仍保留，请重新选择景点规划本次停留')
        data=dict(snap['editor_data'],user_id='default')
        # Use the imported snapshot (not later changes in another tab) for selected facts.
        projected=svc.projection(plan,d['snapshots']);city=next(c for c in projected['cities'] if c['id']==stop_id)
        data.update(status='assembling',request_json=request.model_dump_json(),days_detail_json=svc.dump(city['days']))
        new_id=uuid.uuid4().hex;session.add(TripDraft(id=new_id,**data));await session.commit()
        return dict(draft_id=new_id,basis=svc.stop_basis(plan,stop),revision=d['revision'])

@router.post('/{trip_id}/save')
async def save(trip_id:str,body:Revision):
    async def apply(d,session):
        summary=svc.projection(MultiTrip.model_validate(d['plan']),d['snapshots'])
        if summary['conflicts']: raise HTTPException(409,'仍有时间或夜晚冲突，请先处理：'+'；'.join(summary['conflicts']))
        d['status']='saved';d['saved_summary']=summary
        return d
    return svc.response(await svc.write(trip_id,body.revision,apply))

@router.post('/{trip_id}/copy')
async def copy(trip_id:str):
    d=await svc.load(trip_id)
    return svc.response(await svc.create(MultiTrip.model_validate(d['plan']),trip_id,d['snapshots']))

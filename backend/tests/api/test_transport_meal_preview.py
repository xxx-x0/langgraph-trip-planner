"""Preview/save/CAS verification with synthetic restaurant and map providers."""
import json
from unittest.mock import AsyncMock

import pytest

from .test_single_journey_adjustment import client, seed, request, late_journey
from app.database import async_session
from app.models.db_models import TripDraft
from app.services import single_journey_adjustment as adjustment, trip_draft_service as drafts, meal_recovery


@pytest.fixture
def restaurants(monkeypatch):
    candidates=[dict(name=name,poi_id=name,category='main',location={'longitude':116.4,'latitude':39.9},
        avg_cost=35,open_hours='08:00-23:00',source='nearby') for name in ['附近午餐','附近晚餐']]
    monkeypatch.setattr(meal_recovery,'search_dining_for_day',AsyncMock(return_value={'main':candidates}))
    monkeypatch.setattr(meal_recovery,'get_llm',lambda:object())
    monkeypatch.setattr(meal_recovery,'invoke_structured_or_json',AsyncMock(return_value=meal_recovery.MealRanking(option_ids=['0'])))


@pytest.mark.asyncio
async def test_missing_meals_need_explicit_refill_and_save_pool_with_day(client,restaurants):
    ident=await seed(request(days=2));url=f'/api/trip/draft/{ident}/journey-adjustment'
    before=adjustment.snapshot(await drafts.get_draft(ident))
    ordinary=(await client.post(url,json={'journey':None})).json()
    assert ordinary['meal_recovery']==[]
    assert all(not d['meals'] for d in ordinary['days_detail'])
    meal_recovery.search_dining_for_day.assert_not_awaited()
    body={'journey':None,'refill_meals':True}
    response=await client.post(url,json=body);assert response.status_code==200,response.text
    preview=response.json()
    assert len(preview['meal_recovery'])==4 and all(r['status']=='scheduled' for r in preview['meal_recovery'])
    assert adjustment.snapshot(await drafts.get_draft(ident))==before
    confirm=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'])
    assert (await client.post(url,json=confirm)).status_code==409
    assert (await client.post(url,json=confirm|{'acknowledge_adjustments':True})).status_code==200
    saved=(await client.get('/api/trip/draft/'+ident)).json()
    for old,new,ctx in zip(preview['days_detail'],saved['days_detail'],saved['days']):
        assert new['timeline_schedule']==old['timeline_schedule']
        assert new['meals']==old['meals']
        assert {m['type'] for m in new['meals']}=={'lunch','dinner'}
        assert {m['poi_id'] for m in new['meals']}<={m['poi_id'] for m in ctx['dining_pool']['main']}
        assert new['removed_attraction_names']==['早已删除']
        assert any('重新推荐晚餐' in note for note in new['meal_adjustments'])


@pytest.mark.asyncio
async def test_recovery_preview_rejects_new_candidate_pool_and_changed_opt_in(client,restaurants):
    ident=await seed(request(days=2));url=f'/api/trip/draft/{ident}/journey-adjustment'
    body={'journey':None,'refill_meals':True}
    preview=(await client.post(url,json=body)).json()
    confirm=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'],acknowledge_adjustments=True)
    assert (await client.post(url,json=confirm|{'refill_meals':False})).status_code==409
    async with async_session() as s:
        record=await s.get(TripDraft,ident);record.dining_pool_json='[{}]';await s.commit()
    before=adjustment.snapshot(await drafts.get_draft(ident))
    assert (await client.post(url,json=confirm)).status_code==409
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_displaced_meal_is_replaced_without_explicit_refill(client,restaurants):
    ident=await seed(request(days=2))
    async with async_session() as s:
        record=await s.get(TripDraft,ident);days=json.loads(record.days_detail_json)
        days[0]['meals']=[dict(name='下午才开门',type='lunch',preferred_slot='lunch',schedule_mode='auto',open_hours='16:30-22:00')]
        days[0]['timeline_order'].append(dict(kind='meal',ref_name='下午才开门'))
        record.days_detail_json=json.dumps(days,ensure_ascii=False);await s.commit()
    journey=late_journey();journey['outbound']['arrival_time']='2026-11-10T12:00'
    response=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json={'journey':journey})
    assert response.status_code==200,response.text
    p=response.json()
    assert len(p['meal_recovery'])==1 and p['meal_recovery'][0]['status']=='scheduled'
    assert p['meal_recovery'][0]['old_restaurant']=='下午才开门'
    assert [a['name'] for a in p['days_detail'][0]['attractions']]==['首日园林']
    assert p['days_detail'][0]['meals'][0]['type']=='lunch'
    assert not p['days_detail'][1]['meals']  # An unrelated missing/deleted meal stays absent.

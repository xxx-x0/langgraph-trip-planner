"""Mocked hotel selection to saved explanation projection; no live availability claim."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest
from httpx import ASGITransport,AsyncClient
from app.api.main import app
from app.database import init_db
from app.models.schemas import MacroPlan,DaySkeleton
from app.services import trip_draft_service
from app.agents.langgraph_agent.nodes.search import search_hotels_by_day_node
from tests.services.test_hotel_quotes import request,parsed

@pytest.mark.asyncio
async def test_distance_selected_hotel_explanation_survives_draft_finalize_and_history():
    await init_db();req=request()
    hotels=[{'name':'远处五星（分店）','hotel_id':1,'star_rating':5,'location':{'longitude':120.99,'latitude':31.3}},
            {'name':'近处三星（园林店）','hotel_id':2,'star_rating':3,'location':{'longitude':120.601,'latitude':31.3}}]
    async def enrich(h,*a):return {**h,'quote':parsed().quote.model_dump()}
    service=SimpleNamespace(get_tools=AsyncMock(return_value=[]),get_tool=AsyncMock(return_value=object()))
    with patch('app.services.aigohotel_mcp_service.get_aigohotel_service',return_value=service), patch('app.agents.langgraph_agent.nodes.search._aigohotel_search_for_day',new=AsyncMock(return_value=hotels)),patch('app.services.hotel_quotes.enrich_selected_hotel',side_effect=enrich):
        result=await search_hotels_by_day_node({'request':req,'clusters_data':[[{'name':'A','longitude':120.6,'latitude':31.3}]]*3})
    selected=result['hotels_by_day'][0][0]
    assert selected['name']=='近处三星（园林店）'
    assert selected['recommendation']['source']=='AIGoHotel'
    dates=['2026-10-19','2026-10-20','2026-10-21']
    draft=await trip_draft_service.create_draft(user_id='hotel-advice',request=req,selected_attractions=[],
        macro_plan=MacroPlan(city=req.city,total_days=3,days=[DaySkeleton(day_index=i,date=d,attraction_names=['A']) for i,d in enumerate(dates)]),
        clusters_data=[[{'name':'A','ticket_price':0,'visit_minutes':60}]]*3,
        hotels_by_day=result['hotels_by_day'],dining_pool=[{}]*3,weather_info=[])
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        with patch('app.api.routes.trip_draft.compute_day_route',new=AsyncMock(return_value=[])):
            edited=await client.post(f'/api/trip/draft/{draft}/day/0/recompute',json={'meals':[]})
        assert edited.status_code==200
        saved=edited.json()['day_detail']['hotel']
        assert saved['name']==selected['name'] and saved['recommendation']==selected['recommendation']
        with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])),patch('app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences',new=AsyncMock(return_value=None)):
            done=await client.post(f'/api/trip/draft/{draft}/finalize')
        event=next(json.loads(line[6:]) for line in done.text.splitlines() if line.startswith('data: ') and json.loads(line[6:])['type']=='complete')
        history=(await client.get(f"/api/trips/{event['trip_id']}")).json()['data']['plan']
        assert history==event['trip_plan']
        for day in history['days']:
            assert day['hotel']['name']==selected['name']
            assert day['hotel']['quote']==saved['quote']
            assert day['hotel']['recommendation']==selected['recommendation']

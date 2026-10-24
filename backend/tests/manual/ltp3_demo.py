"""Run the LTP-3 acceptance demo with simulated external services and isolated data."""
import os
import tempfile
import json
from contextlib import asynccontextmanager
from pathlib import Path

STATE_DIR = Path(tempfile.mkdtemp(prefix='ltp3-demo-'))
os.environ['DATABASE_URL'] = f"sqlite+aiosqlite:///{STATE_DIR / 'trips.db'}"

from fastapi import FastAPI, HTTPException
from app.api.routes import trip_draft, trip_history
from app.agents.langgraph_agent.finalize import pipeline
from app.database import init_db
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton, DiningPoolDay, RouteSegment, DayEditRequest
from app.services import trip_draft_service


async def simulated_route(detail, *args):
    flag = STATE_DIR / 'fail-next-route'
    if flag.exists():
        flag.unlink()
        raise HTTPException(503, detail='模拟路线失败，请重试')
    return [RouteSegment(from_name=a.name, to_name=b.name, distance='模拟 1 公里',
                         duration='模拟 15 分钟', mode='步行')
            for a, b in zip(detail.attractions, detail.attractions[1:])]


async def simulated_llm(*args):
    return type('Response', (), {'content': json.dumps({
        'attractions_order': ['平江路', '苏州博物馆', '狮子林', '拙政园'], 'meals': []
    }, ensure_ascii=False)})()


async def simulated_narrative(*args, **kwargs):
    return '本页用于 LTP-3 模拟验证，地图和 AI 均为模拟服务；草稿、编辑、定稿和历史读取使用真实代码与临时 SQLite。'


async def simulated_synthesizer(*args, **kwargs):
    return '模拟验证行程', '外部服务尚未实测', ''


async def simulated_preferences(*args):
    pass


trip_draft.compute_day_route = simulated_route
trip_draft.write_day_narrative_llm = simulated_narrative
trip_draft._invoke_llm_with_retry = simulated_llm
trip_draft.get_llm = lambda: None
pipeline.compute_day_route = simulated_route
pipeline._run_global_synthesizer = simulated_synthesizer
pipeline._run_extract_preferences = simulated_preferences


@asynccontextmanager
async def lifespan(app):
    await init_db()
    request = TripRequest(city='苏州', start_date='2026-10-20', end_date='2026-10-21',
                          travel_days=2, transportation='步行', accommodation='经济型酒店')
    names = [['拙政园', '狮子林', '苏州博物馆', '平江路'], ['寒山寺', '山塘街']]
    draft_id = await trip_draft_service.create_draft(
        user_id='default', request=request, selected_attractions=[],
        macro_plan=MacroPlan(city='苏州', total_days=2, days=[
            DaySkeleton(day_index=i, date=f'2026-10-{20+i}', attraction_names=day)
            for i, day in enumerate(names)
        ]),
        clusters_data=[[{'name':name,'ticket_price':20} for name in day] for day in names],
        hotels_by_day=[[],[]], dining_pool=[DiningPoolDay().model_dump(mode='json')]*2,
        weather_info=[],
    )
    await trip_draft.assemble_day(draft_id, 0, DayEditRequest(), force=False)
    (STATE_DIR / 'draft-id').write_text(draft_id)
    print(f'Demo data: {STATE_DIR}', flush=True)
    print(f'Open: http://127.0.0.1:5174/draft/{draft_id}', flush=True)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(trip_draft.router, prefix='/api')
app.include_router(trip_history.router, prefix='/api')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18000)

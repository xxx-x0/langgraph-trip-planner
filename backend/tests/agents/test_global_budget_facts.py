from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
import pytest
from app.models.schemas import TripPlan, DayPlan, Hotel, Budget, WeatherInfo
from app.agents.langgraph_agent.nodes.generate import global_synthesizer_node


@pytest.mark.asyncio
async def test_model_cannot_override_nights_unknown_cost_or_weather():
    plan = TripPlan(city='苏州', start_date='2026-10-14', end_date='2026-10-15', overall_suggestions='', days=[
        DayPlan(date='2026-10-14', day_index=0, description='', transportation='步行', accommodation='民宿',
                hotel=Hotel(name='H', estimated_cost=234), overnight_stay=True),
        DayPlan(date='2026-10-15', day_index=1, description='', transportation='步行', accommodation='民宿',
                hotel=Hotel(name='H', estimated_cost=234), overnight_stay=False,
                meal_warnings=['早餐未安排，请出发前自行安排'])],
        budget=Budget(total_hotels=234, total=234, is_complete=False,
                      unknown_cost_items=['拙政园门票']),
        weather_info=[WeatherInfo(date='2026-10-14', day_weather='阴', night_weather='阴',
                                  day_temp=25, night_temp=17, wind_direction='东北', wind_power='1-3')])
    output = SimpleNamespace(content='{"trip_tagline":"江南漫游","overall_suggestions":"两晚234元，门票200-400元","weather_summary":"晴"}')
    with patch('app.agents.langgraph_agent.nodes.generate.get_llm'), patch(
            'app.agents.langgraph_agent.nodes.generate._invoke_llm_with_retry', new=AsyncMock(return_value=output)):
        result = await global_synthesizer_node({'trip_plan':plan})
    saved = result['trip_plan']
    assert '需要1晚住宿' in saved.overall_suggestions
    assert saved.budget.total_hotels == 0
    assert '旧记录住宿报价条件未核对' in saved.overall_suggestions
    assert '拙政园门票' in saved.overall_suggestions
    assert '200-400' not in saved.overall_suggestions
    assert '两晚' not in saved.overall_suggestions
    assert '早餐未安排' in saved.overall_suggestions
    assert saved.weather_summary == '阴为主'


def test_no_hotel_does_not_erase_required_overnight_count():
    from app.agents.langgraph_agent.assemble.narrative import refresh_trip_descriptions
    plan=TripPlan(city='苏州',start_date='2026-10-19',end_date='2026-10-21',overall_suggestions='',
        days=[DayPlan(date=f'2026-10-{19+i}',day_index=i,description='',transportation='步行',accommodation='酒店',overnight_stay=i<2) for i in range(3)],
        budget=Budget(is_complete=False,unknown_cost_items=['住宿未安排']))
    refresh_trip_descriptions(plan)
    assert '需要2晚住宿' in plan.overall_suggestions
    assert plan.budget.total_hotels==0
    assert not plan.budget.is_complete

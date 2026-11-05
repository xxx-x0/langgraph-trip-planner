from unittest.mock import AsyncMock
import pytest
from app.agents.langgraph_agent.utils import strategy_extract as svc


@pytest.mark.asyncio
@pytest.mark.parametrize('model_fails', [False, True])
async def test_both_model_and_rating_fallback_fit_remaining_partial_day(monkeypatch, model_fails):
    pool = [dict(poi_id=str(i), name=f'公园{i}', visit_minutes=90, rating=5-i/10) for i in range(5)]
    monkeypatch.setattr(svc, 'estimate_durations_batch', AsyncMock(return_value={p['name']:90 for p in pool}))
    monkeypatch.setattr(svc, 'get_llm', lambda: object())
    monkeypatch.setattr(svc, 'is_structured_output_supported', lambda: False)
    async def pick(*args, **kwargs):
        assert '不超过 120 分钟' in args[1]
        if model_fails:
            raise RuntimeError('simulated failure')
        return '{"must":[{"poi_id":"0"},{"poi_id":"1"},{"poi_id":"2"}],"optional":[]}'
    monkeypatch.setattr(svc, '_invoke_llm_with_retry', pick)
    result = await svc.pick_attractions_from_pool('北京', 2, pool, daily_windows=[
        dict(date='2026-11-10', start_minutes=1140, end_minutes=1440),
        dict(date='2026-11-11', unavailable=True)])
    assert len(result['must_ids']) == 1
    assert '1' in result['optional_ids'] and '2' in result['optional_ids']

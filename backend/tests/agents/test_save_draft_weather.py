import json
from unittest.mock import AsyncMock, patch

import pytest
from app.agents.langgraph_agent.nodes.draft import save_draft_node
from app.models.schemas import TripRequest, MacroPlan


@pytest.mark.parametrize('representation', ['pretty_json','decoded','structured','nested_casts'])
def test_normalized_and_multiline_weather_keeps_dates_and_temperatures(representation):
    from app.agents.langgraph_agent.nodes.generate import _parse_weather_payload
    rows=[{'date':day,'dayweather':weather,'nightweather':weather,'daytemp':temp,'nighttemp':19}
          for day,weather,temp in [('2026-10-14','多云',24),('2026-10-15','阴',24),('2026-10-16','小雨',26)]]
    payload={'city':'苏州','forecasts':rows}
    if representation=='pretty_json':payload=json.dumps(payload,ensure_ascii=False,indent=2)
    elif representation=='structured':payload={'structuredContent':payload}
    elif representation=='nested_casts':payload={'forecasts':[{'casts':rows}]}
    parsed=_parse_weather_payload(payload,'2026-10-15','2026-10-16')
    assert [(w.date,w.day_weather,w.day_temp) for w in parsed]==[('2026-10-15','阴',24),('2026-10-16','小雨',26)]


@pytest.mark.asyncio
async def test_save_draft_keeps_discovery_mcp_weather_for_trip_dates():
    request = TripRequest(city="苏州", start_date="2026-10-14", end_date="2026-10-15",
                          travel_days=2, transportation="公共交通", accommodation="经济型酒店")
    weather = str([{"type": "text", "text": json.dumps({"city": "苏州", "forecasts": [
        {"date": day, "dayweather": "阴", "nightweather": "多云", "daytemp": "25", "nighttemp": "19"}
        for day in ["2026-10-13", "2026-10-14", "2026-10-15"]
    ]})}])
    save = AsyncMock(return_value="draft-id")
    with patch("app.agents.langgraph_agent.nodes.draft.trip_draft_service.create_draft", save), patch(
        "app.agents.langgraph_agent.nodes.generate.fetch_open_meteo_weather", new=AsyncMock(side_effect=AssertionError("weather is already present"))
    ):
        await save_draft_node({"request":request,"macro_plan":MacroPlan(city="苏州",total_days=2,days=[]),"weather_info":weather})
    saved = save.call_args.kwargs["weather_info"]
    assert [w["date"] for w in saved] == ["2026-10-14", "2026-10-15"]
    assert all(w["day_temp"] == 25 and w["day_weather"] == "阴" for w in saved)

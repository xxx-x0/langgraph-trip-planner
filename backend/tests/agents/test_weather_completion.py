import json

import pytest

from app.agents.langgraph_agent.nodes import generate
from app.models.schemas import TripRequest, WeatherInfo


def _request():
    return TripRequest(
        city="北京",
        start_date="2026-06-01",
        end_date="2026-06-04",
        travel_days=4,
        transportation="公共交通",
        accommodation="经济型酒店",
    )


@pytest.mark.asyncio
async def test_build_weather_list_fills_missing_days_with_open_meteo(monkeypatch):
    amap_weather = json.dumps({
        "forecasts": [{
            "casts": [
                {
                    "date": "2026-06-01",
                    "dayweather": "晴",
                    "nightweather": "多云",
                    "daytemp": "30",
                    "nighttemp": "21",
                    "daywind": "南风",
                    "daypower": "2-3级",
                },
                {
                    "date": "2026-06-02",
                    "dayweather": "多云",
                    "nightweather": "晴",
                    "daytemp": "31",
                    "nighttemp": "22",
                    "daywind": "南风",
                    "daypower": "2-3级",
                },
            ],
        }],
    })

    async def fake_open_meteo(city, start_date, end_date):
        assert city == "北京"
        assert start_date == "2026-06-03"
        assert end_date == "2026-06-04"
        return [
            WeatherInfo(
                date="2026-06-03",
                day_weather="小雨",
                night_weather="小雨",
                day_temp=28,
                night_temp=20,
                wind_direction="西南风",
                wind_power="3级",
            ),
            WeatherInfo(
                date="2026-06-04",
                day_weather="阴",
                night_weather="阴",
                day_temp=27,
                night_temp=19,
                wind_direction="西南风",
                wind_power="2级",
            ),
        ]

    monkeypatch.setattr(generate, "fetch_open_meteo_weather", fake_open_meteo)

    weather = await generate._build_weather_list(_request(), amap_weather)

    assert [w.date for w in weather] == [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
    ]
    assert weather[0].day_weather == "晴"
    assert weather[2].day_weather == "小雨"
    assert weather[3].day_temp == 27

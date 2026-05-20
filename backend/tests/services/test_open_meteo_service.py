from app.services.open_meteo_service import _parse_daily_forecast


def test_parse_daily_forecast_maps_open_meteo_daily_payload():
    data = {
        "daily": {
            "time": ["2026-06-01", "2026-06-02"],
            "weather_code": [0, 61],
            "temperature_2m_max": [30.4, 27.6],
            "temperature_2m_min": [21.2, 19.9],
            "wind_speed_10m_max": [8.2, 13.7],
            "wind_direction_10m_dominant": [10, 230],
        },
    }

    weather = _parse_daily_forecast(data)

    assert len(weather) == 2
    assert weather[0].date == "2026-06-01"
    assert weather[0].day_weather == "晴"
    assert weather[0].day_temp == 30
    assert weather[0].wind_direction == "北风"
    assert weather[0].wind_power == "8km/h"
    assert weather[1].day_weather == "小雨"
    assert weather[1].night_temp == 20
    assert weather[1].wind_direction == "西南风"

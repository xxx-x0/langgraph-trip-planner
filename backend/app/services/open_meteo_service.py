"""Open-Meteo weather integration.

Open-Meteo does not require an API key for the public forecast endpoints.  We
use it as a medium-range weather fallback when AMap cannot cover the requested
trip dates.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from ..models.schemas import WeatherInfo


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


WEATHER_CODE_TEXT = {
    0: "晴",
    1: "晴",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾",
    51: "小雨",
    53: "小雨",
    55: "中雨",
    56: "冻雨",
    57: "冻雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "阵雪",
    80: "阵雨",
    81: "阵雨",
    82: "暴雨",
    85: "阵雪",
    86: "大雪",
    95: "雷阵雨",
    96: "雷阵雨",
    99: "雷阵雨",
}


def _weather_text(code: Any) -> str:
    try:
        return WEATHER_CODE_TEXT.get(int(code), "多云")
    except (TypeError, ValueError):
        return "多云"


def _wind_direction(degrees: Any) -> str:
    try:
        deg = float(degrees) % 360
    except (TypeError, ValueError):
        return ""
    directions = [
        "北风",
        "东北风",
        "东风",
        "东南风",
        "南风",
        "西南风",
        "西风",
        "西北风",
    ]
    index = int((deg + 22.5) // 45) % 8
    return directions[index]


def _wind_power(speed: Any) -> str:
    try:
        return f"{round(float(speed))}km/h"
    except (TypeError, ValueError):
        return ""


class OpenMeteoWeatherService:
    async def _geocode_city(self, city: str, client: httpx.AsyncClient) -> Optional[tuple[float, float]]:
        names = [city]
        if city.endswith("市"):
            names.append(city[:-1])

        for name in names:
            resp = await client.get(
                GEOCODING_URL,
                params={
                    "name": name,
                    "count": 1,
                    "language": "zh",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if results:
                first = results[0]
                lat = first.get("latitude")
                lon = first.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
        return None

    async def fetch_daily_weather(
        self,
        city: str,
        start_date: str,
        end_date: str,
    ) -> list[WeatherInfo]:
        async with httpx.AsyncClient(timeout=12.0) as client:
            coords = await self._geocode_city(city, client)
            if not coords:
                print(f"⚠️ Open-Meteo 未找到城市坐标: {city}")
                return []

            latitude, longitude = coords
            resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": ",".join([
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "wind_speed_10m_max",
                        "wind_direction_10m_dominant",
                    ]),
                    "timezone": "Asia/Shanghai",
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            resp.raise_for_status()
            return _parse_daily_forecast(resp.json())


def _parse_daily_forecast(data: dict[str, Any]) -> list[WeatherInfo]:
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    max_temps = daily.get("temperature_2m_max") or []
    min_temps = daily.get("temperature_2m_min") or []
    wind_speeds = daily.get("wind_speed_10m_max") or []
    wind_degrees = daily.get("wind_direction_10m_dominant") or []

    weather: list[WeatherInfo] = []
    for idx, date in enumerate(dates):
        text = _weather_text(codes[idx] if idx < len(codes) else None)
        weather.append(WeatherInfo(
            date=str(date),
            day_weather=text,
            night_weather=text,
            day_temp=round(float(max_temps[idx])) if idx < len(max_temps) and max_temps[idx] is not None else 0,
            night_temp=round(float(min_temps[idx])) if idx < len(min_temps) and min_temps[idx] is not None else 0,
            wind_direction=_wind_direction(wind_degrees[idx] if idx < len(wind_degrees) else None),
            wind_power=_wind_power(wind_speeds[idx] if idx < len(wind_speeds) else None),
        ))
    return weather


async def fetch_open_meteo_weather(
    city: str,
    start_date: str,
    end_date: str,
) -> list[WeatherInfo]:
    service = OpenMeteoWeatherService()
    return await service.fetch_daily_weather(city, start_date, end_date)

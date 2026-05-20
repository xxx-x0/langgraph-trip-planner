import json
import re
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from ..exceptions import _invoke_llm_with_retry
from ..prompts import PLANNER_AGENT_PROMPT
from ..state import TripPlannerState, DayPlanLocalState
from ..utils.parsing import _parse_response, _validate_plan_coordinates, _create_fallback_plan
from ....models.schemas import (
    TripPlan, DayPlan, Attraction, Meal, Hotel, RouteSegment, Location,
    MacroPlan, DaySkeleton, Budget, WeatherInfo,
)
from ....services.llm_service import get_llm, is_structured_output_supported
from ....services.open_meteo_service import fetch_open_meteo_weather


def _truncate_info(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... (已截断，原始数据共{len(text)}字符)"


CITY_SEASON_WEATHER = {
    "广州": {
        1:  {"day_temp": 18, "night_temp": 10, "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        2:  {"day_temp": 19, "night_temp": 12, "day_weather": "阴", "night_weather": "多云", "wind": "东北风", "power": "2-3级"},
        3:  {"day_temp": 22, "night_temp": 15, "day_weather": "多云", "night_weather": "小雨", "wind": "南风", "power": "2-3级"},
        4:  {"day_temp": 26, "night_temp": 19, "day_weather": "多云", "night_weather": "晴", "wind": "南风", "power": "2-3级"},
        5:  {"day_temp": 30, "night_temp": 23, "day_weather": "多云", "night_weather": "雷阵雨", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 32, "night_temp": 25, "day_weather": "雷阵雨", "night_weather": "多云", "wind": "南风", "power": "3-4级"},
        7:  {"day_temp": 33, "night_temp": 26, "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 33, "night_temp": 26, "day_weather": "雷阵雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        9:  {"day_temp": 31, "night_temp": 24, "day_weather": "多云", "night_weather": "晴", "wind": "东北风", "power": "2-3级"},
        10: {"day_temp": 28, "night_temp": 20, "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
        11: {"day_temp": 24, "night_temp": 16, "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
        12: {"day_temp": 20, "night_temp": 12, "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
    },
    "北京": {
        1:  {"day_temp": -1, "night_temp": -10, "day_weather": "晴", "night_weather": "晴", "wind": "西北风", "power": "3-4级"},
        2:  {"day_temp": 3,  "night_temp": -7,  "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "3-4级"},
        3:  {"day_temp": 11, "night_temp": 0,   "day_weather": "多云", "night_weather": "晴", "wind": "南风", "power": "2-3级"},
        4:  {"day_temp": 20, "night_temp": 8,   "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "3-4级"},
        5:  {"day_temp": 27, "night_temp": 15,  "day_weather": "晴", "night_weather": "晴", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 31, "night_temp": 20,  "day_weather": "多云", "night_weather": "雷阵雨", "wind": "南风", "power": "2-3级"},
        7:  {"day_temp": 32, "night_temp": 23,  "day_weather": "雷阵雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 30, "night_temp": 22,  "day_weather": "多云", "night_weather": "雷阵雨", "wind": "北风", "power": "2-3级"},
        9:  {"day_temp": 26, "night_temp": 15,  "day_weather": "晴", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        10: {"day_temp": 17, "night_temp": 6,   "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "3-4级"},
        11: {"day_temp": 7,  "night_temp": -2,  "day_weather": "多云", "night_weather": "晴", "wind": "西北风", "power": "3-4级"},
        12: {"day_temp": 1,  "night_temp": -8,  "day_weather": "晴", "night_weather": "晴", "wind": "西北风", "power": "3-4级"},
    },
    "上海": {
        1:  {"day_temp": 6,  "night_temp": 0,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "3-4级"},
        2:  {"day_temp": 8,  "night_temp": 2,   "day_weather": "阴", "night_weather": "小雨", "wind": "东北风", "power": "3-4级"},
        3:  {"day_temp": 13, "night_temp": 6,   "day_weather": "多云", "night_weather": "小雨", "wind": "东风", "power": "2-3级"},
        4:  {"day_temp": 19, "night_temp": 12,  "day_weather": "多云", "night_weather": "晴", "wind": "东南风", "power": "2-3级"},
        5:  {"day_temp": 25, "night_temp": 17,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 28, "night_temp": 22,  "day_weather": "小雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        7:  {"day_temp": 33, "night_temp": 26,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "3-4级"},
        8:  {"day_temp": 33, "night_temp": 26,  "day_weather": "雷阵雨", "night_weather": "多云", "wind": "东南风", "power": "2-3级"},
        9:  {"day_temp": 28, "night_temp": 21,  "day_weather": "多云", "night_weather": "晴", "wind": "东风", "power": "2-3级"},
        10: {"day_temp": 22, "night_temp": 14,  "day_weather": "晴", "night_weather": "多云", "wind": "东北风", "power": "2-3级"},
        11: {"day_temp": 15, "night_temp": 8,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        12: {"day_temp": 8,  "night_temp": 2,   "day_weather": "晴", "night_weather": "多云", "wind": "西北风", "power": "3-4级"},
    },
    "成都": {
        1:  {"day_temp": 9,  "night_temp": 3,   "day_weather": "阴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
        2:  {"day_temp": 12, "night_temp": 5,   "day_weather": "多云", "night_weather": "小雨", "wind": "东北风", "power": "1-2级"},
        3:  {"day_temp": 17, "night_temp": 9,   "day_weather": "多云", "night_weather": "小雨", "wind": "南风", "power": "1-2级"},
        4:  {"day_temp": 22, "night_temp": 14,  "day_weather": "多云", "night_weather": "晴", "wind": "南风", "power": "1-2级"},
        5:  {"day_temp": 26, "night_temp": 18,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "1-2级"},
        6:  {"day_temp": 28, "night_temp": 21,  "day_weather": "阴", "night_weather": "小雨", "wind": "南风", "power": "1-2级"},
        7:  {"day_temp": 30, "night_temp": 23,  "day_weather": "多云", "night_weather": "雷阵雨", "wind": "南风", "power": "1-2级"},
        8:  {"day_temp": 30, "night_temp": 22,  "day_weather": "多云", "night_weather": "小雨", "wind": "北风", "power": "1-2级"},
        9:  {"day_temp": 25, "night_temp": 19,  "day_weather": "阴", "night_weather": "小雨", "wind": "北风", "power": "1-2级"},
        10: {"day_temp": 20, "night_temp": 14,  "day_weather": "阴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
        11: {"day_temp": 14, "night_temp": 8,   "day_weather": "多云", "night_weather": "阴", "wind": "北风", "power": "1-2级"},
        12: {"day_temp": 10, "night_temp": 4,   "day_weather": "阴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
    },
    "杭州": {
        1:  {"day_temp": 6,  "night_temp": 0,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        2:  {"day_temp": 9,  "night_temp": 3,   "day_weather": "小雨", "night_weather": "阴", "wind": "东北风", "power": "2-3级"},
        3:  {"day_temp": 14, "night_temp": 7,   "day_weather": "多云", "night_weather": "小雨", "wind": "东风", "power": "2-3级"},
        4:  {"day_temp": 21, "night_temp": 13,  "day_weather": "晴", "night_weather": "多云", "wind": "东南风", "power": "2-3级"},
        5:  {"day_temp": 26, "night_temp": 18,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 29, "night_temp": 22,  "day_weather": "小雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        7:  {"day_temp": 34, "night_temp": 26,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 33, "night_temp": 26,  "day_weather": "雷阵雨", "night_weather": "多云", "wind": "东南风", "power": "2-3级"},
        9:  {"day_temp": 28, "night_temp": 21,  "day_weather": "多云", "night_weather": "晴", "wind": "东风", "power": "2-3级"},
        10: {"day_temp": 22, "night_temp": 14,  "day_weather": "晴", "night_weather": "多云", "wind": "东北风", "power": "2-3级"},
        11: {"day_temp": 15, "night_temp": 8,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        12: {"day_temp": 8,  "night_temp": 2,   "day_weather": "晴", "night_weather": "多云", "wind": "西北风", "power": "2-3级"},
    },
    "深圳": {
        1:  {"day_temp": 20, "night_temp": 13, "day_weather": "多云", "night_weather": "晴", "wind": "东北风", "power": "2-3级"},
        2:  {"day_temp": 20, "night_temp": 14, "day_weather": "阴", "night_weather": "多云", "wind": "东北风", "power": "2-3级"},
        3:  {"day_temp": 23, "night_temp": 17, "day_weather": "多云", "night_weather": "小雨", "wind": "南风", "power": "2-3级"},
        4:  {"day_temp": 27, "night_temp": 21, "day_weather": "多云", "night_weather": "晴", "wind": "南风", "power": "2-3级"},
        5:  {"day_temp": 30, "night_temp": 24, "day_weather": "多云", "night_weather": "雷阵雨", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 32, "night_temp": 26, "day_weather": "雷阵雨", "night_weather": "多云", "wind": "南风", "power": "3-4级"},
        7:  {"day_temp": 33, "night_temp": 27, "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 33, "night_temp": 27, "day_weather": "雷阵雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        9:  {"day_temp": 31, "night_temp": 25, "day_weather": "多云", "night_weather": "晴", "wind": "东北风", "power": "2-3级"},
        10: {"day_temp": 28, "night_temp": 22, "day_weather": "晴", "night_weather": "多云", "wind": "东北风", "power": "2-3级"},
        11: {"day_temp": 24, "night_temp": 18, "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
        12: {"day_temp": 21, "night_temp": 14, "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
    },
    "重庆": {
        1:  {"day_temp": 10, "night_temp": 5,   "day_weather": "阴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
        2:  {"day_temp": 12, "night_temp": 7,   "day_weather": "阴", "night_weather": "小雨", "wind": "东北风", "power": "1-2级"},
        3:  {"day_temp": 17, "night_temp": 11,  "day_weather": "多云", "night_weather": "小雨", "wind": "南风", "power": "1-2级"},
        4:  {"day_temp": 23, "night_temp": 15,  "day_weather": "多云", "night_weather": "晴", "wind": "南风", "power": "1-2级"},
        5:  {"day_temp": 27, "night_temp": 20,  "day_weather": "多云", "night_weather": "阴", "wind": "南风", "power": "1-2级"},
        6:  {"day_temp": 30, "night_temp": 23,  "day_weather": "小雨", "night_weather": "多云", "wind": "南风", "power": "1-2级"},
        7:  {"day_temp": 34, "night_temp": 26,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "1-2级"},
        8:  {"day_temp": 35, "night_temp": 26,  "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
        9:  {"day_temp": 28, "night_temp": 21,  "day_weather": "阴", "night_weather": "小雨", "wind": "北风", "power": "1-2级"},
        10: {"day_temp": 20, "night_temp": 15,  "day_weather": "阴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
        11: {"day_temp": 15, "night_temp": 10,  "day_weather": "多云", "night_weather": "阴", "wind": "北风", "power": "1-2级"},
        12: {"day_temp": 11, "night_temp": 6,   "day_weather": "阴", "night_weather": "多云", "wind": "北风", "power": "1-2级"},
    },
    "西安": {
        1:  {"day_temp": 3,  "night_temp": -4,  "day_weather": "晴", "night_weather": "晴", "wind": "西北风", "power": "2-3级"},
        2:  {"day_temp": 7,  "night_temp": -2,  "day_weather": "多云", "night_weather": "晴", "wind": "东北风", "power": "2-3级"},
        3:  {"day_temp": 14, "night_temp": 4,   "day_weather": "多云", "night_weather": "晴", "wind": "南风", "power": "2-3级"},
        4:  {"day_temp": 21, "night_temp": 10,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        5:  {"day_temp": 27, "night_temp": 15,  "day_weather": "晴", "night_weather": "晴", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 32, "night_temp": 20,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        7:  {"day_temp": 34, "night_temp": 24,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 32, "night_temp": 22,  "day_weather": "多云", "night_weather": "雷阵雨", "wind": "北风", "power": "2-3级"},
        9:  {"day_temp": 26, "night_temp": 17,  "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        10: {"day_temp": 18, "night_temp": 9,   "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
        11: {"day_temp": 10, "night_temp": 2,   "day_weather": "多云", "night_weather": "晴", "wind": "西北风", "power": "2-3级"},
        12: {"day_temp": 4,  "night_temp": -3,  "day_weather": "晴", "night_weather": "晴", "wind": "西北风", "power": "2-3级"},
    },
    "南京": {
        1:  {"day_temp": 5,  "night_temp": -2,  "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "3-4级"},
        2:  {"day_temp": 8,  "night_temp": 0,   "day_weather": "小雨", "night_weather": "阴", "wind": "东北风", "power": "2-3级"},
        3:  {"day_temp": 14, "night_temp": 5,   "day_weather": "多云", "night_weather": "小雨", "wind": "东风", "power": "2-3级"},
        4:  {"day_temp": 21, "night_temp": 12,  "day_weather": "晴", "night_weather": "多云", "wind": "东南风", "power": "2-3级"},
        5:  {"day_temp": 27, "night_temp": 17,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 30, "night_temp": 22,  "day_weather": "小雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        7:  {"day_temp": 34, "night_temp": 26,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 33, "night_temp": 25,  "day_weather": "雷阵雨", "night_weather": "多云", "wind": "东南风", "power": "2-3级"},
        9:  {"day_temp": 28, "night_temp": 20,  "day_weather": "多云", "night_weather": "晴", "wind": "东风", "power": "2-3级"},
        10: {"day_temp": 21, "night_temp": 12,  "day_weather": "晴", "night_weather": "多云", "wind": "东北风", "power": "2-3级"},
        11: {"day_temp": 14, "night_temp": 6,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        12: {"day_temp": 7,  "night_temp": 0,   "day_weather": "晴", "night_weather": "多云", "wind": "西北风", "power": "3-4级"},
    },
    "武汉": {
        1:  {"day_temp": 6,  "night_temp": -1,  "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        2:  {"day_temp": 9,  "night_temp": 2,   "day_weather": "小雨", "night_weather": "阴", "wind": "东北风", "power": "2-3级"},
        3:  {"day_temp": 15, "night_temp": 7,   "day_weather": "多云", "night_weather": "小雨", "wind": "东风", "power": "2-3级"},
        4:  {"day_temp": 22, "night_temp": 13,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        5:  {"day_temp": 28, "night_temp": 18,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        6:  {"day_temp": 31, "night_temp": 23,  "day_weather": "小雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        7:  {"day_temp": 34, "night_temp": 26,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
        8:  {"day_temp": 33, "night_temp": 25,  "day_weather": "雷阵雨", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
        9:  {"day_temp": 28, "night_temp": 20,  "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        10: {"day_temp": 21, "night_temp": 12,  "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
        11: {"day_temp": 14, "night_temp": 6,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
        12: {"day_temp": 8,  "night_temp": 1,   "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
    },
}

DEFAULT_SEASON_WEATHER = {
    1:  {"day_temp": 5,  "night_temp": -2,  "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
    2:  {"day_temp": 8,  "night_temp": 0,   "day_weather": "多云", "night_weather": "晴", "wind": "东北风", "power": "2-3级"},
    3:  {"day_temp": 14, "night_temp": 5,   "day_weather": "多云", "night_weather": "小雨", "wind": "东风", "power": "2-3级"},
    4:  {"day_temp": 21, "night_temp": 11,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
    5:  {"day_temp": 27, "night_temp": 17,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
    6:  {"day_temp": 31, "night_temp": 22,  "day_weather": "多云", "night_weather": "雷阵雨", "wind": "南风", "power": "2-3级"},
    7:  {"day_temp": 33, "night_temp": 25,  "day_weather": "晴", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
    8:  {"day_temp": 32, "night_temp": 24,  "day_weather": "雷阵雨", "night_weather": "多云", "wind": "南风", "power": "2-3级"},
    9:  {"day_temp": 27, "night_temp": 19,  "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
    10: {"day_temp": 20, "night_temp": 12,  "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
    11: {"day_temp": 12, "night_temp": 5,   "day_weather": "多云", "night_weather": "晴", "wind": "北风", "power": "2-3级"},
    12: {"day_temp": 6,  "night_temp": -1,  "day_weather": "晴", "night_weather": "多云", "wind": "北风", "power": "2-3级"},
}


def _get_seasonal_weather(city: str, date_str: str) -> Dict[str, Any]:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    month = dt.month
    city_data = CITY_SEASON_WEATHER.get(city, DEFAULT_SEASON_WEATHER)
    month_data = city_data.get(month, DEFAULT_SEASON_WEATHER.get(month, DEFAULT_SEASON_WEATHER[5]))
    day_temp = month_data["day_temp"] + random.randint(-2, 2)
    night_temp = month_data["night_temp"] + random.randint(-2, 1)
    weathers = ["晴", "多云", "阴", month_data["day_weather"]]
    day_weather = random.choice(weathers)
    night_weathers = ["晴", "多云", month_data["night_weather"]]
    night_weather = random.choice(night_weathers)
    return {
        "day_temp": day_temp,
        "night_temp": night_temp,
        "day_weather": day_weather,
        "night_weather": night_weather,
        "wind_direction": month_data["wind"],
        "wind_power": month_data["power"],
    }


def _trip_dates(start_date: str, travel_days: int) -> list[str]:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    return [
        (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(travel_days)
    ]


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _weather_from_mapping(data: dict[str, Any], date_key: str = "date") -> Optional[WeatherInfo]:
    w_date = str(data.get(date_key, ""))
    if not w_date:
        return None
    return WeatherInfo(
        date=w_date,
        day_weather=str(data.get("dayweather", data.get("day_weather", ""))),
        night_weather=str(data.get("nightweather", data.get("night_weather", ""))),
        day_temp=_coerce_int(data.get("daytemp", data.get("day_temp", 0))),
        night_temp=_coerce_int(data.get("nighttemp", data.get("night_temp", 0))),
        wind_direction=str(data.get("daywind", data.get("wind_direction", ""))),
        wind_power=str(data.get("daypower", data.get("wind_power", ""))),
    )


def _parse_weather_payload(weather_data: Any, trip_start: str, trip_end: str) -> list[WeatherInfo]:
    weather_list: list[WeatherInfo] = []
    if not weather_data:
        return weather_list

    print(f"🌤️ 开始解析天气数据，原始长度: {len(str(weather_data))}")
    print(f"  行程日期范围: {trip_start} 至 {trip_end}")

    try:
        if isinstance(weather_data, str):
            import ast
            raw_chunks = [
                chunk.strip()
                for chunk in weather_data.split("\n")
                if chunk.strip() and not chunk.startswith("[工具调用失败")
            ]

            for chunk in raw_chunks:
                try:
                    parsed: Any = chunk
                    for _ in range(2):
                        try:
                            parsed = json.loads(parsed)
                            break
                        except (json.JSONDecodeError, TypeError):
                            try:
                                parsed = ast.literal_eval(parsed)
                                break
                            except (ValueError, SyntaxError):
                                pass

                    if isinstance(parsed, list) and parsed:
                        first = parsed[0]
                        if isinstance(first, dict) and "text" in first:
                            inner = first["text"]
                            if isinstance(inner, str):
                                try:
                                    parsed = json.loads(inner)
                                except (json.JSONDecodeError, TypeError):
                                    try:
                                        parsed = ast.literal_eval(inner)
                                    except (ValueError, SyntaxError):
                                        pass

                    forecasts: list[Any] = []
                    if isinstance(parsed, dict):
                        forecasts = parsed.get("forecasts", [])
                        if not forecasts:
                            for val in parsed.values():
                                if isinstance(val, list) and val and isinstance(val[0], dict):
                                    forecasts = val
                                    break
                    elif isinstance(parsed, list):
                        if parsed and isinstance(parsed[0], dict) and "forecasts" in parsed[0]:
                            forecasts = parsed[0]["forecasts"]
                        else:
                            forecasts = parsed

                    for forecast in forecasts:
                        if not isinstance(forecast, dict):
                            continue
                        casts = forecast.get("casts", [])
                        if casts:
                            for cast in casts:
                                try:
                                    weather = _weather_from_mapping(cast)
                                    if weather and trip_start <= weather.date <= trip_end:
                                        weather_list.append(weather)
                                except Exception as ce:
                                    print(f"  ⚠️ 天气cast解析失败: {str(ce)[:80]}")
                        else:
                            try:
                                weather = _weather_from_mapping(forecast)
                                if weather and trip_start <= weather.date <= trip_end:
                                    weather_list.append(weather)
                                elif weather:
                                    print(f"  ℹ️ 天气forecast日期{weather.date}不在行程范围内，跳过")
                            except Exception as fe:
                                print(f"  ⚠️ 天气forecast解析失败: {str(fe)[:80]}")
                except Exception as chunk_e:
                    print(f"  ⚠️ 天气数据块解析失败: {str(chunk_e)[:80]}")

        elif isinstance(weather_data, list):
            for item in weather_data:
                if isinstance(item, WeatherInfo):
                    if item.date and trip_start <= item.date <= trip_end:
                        weather_list.append(item)
                elif isinstance(item, dict):
                    try:
                        weather = _weather_from_mapping(item)
                        if weather and trip_start <= weather.date <= trip_end:
                            weather_list.append(weather)
                    except Exception:
                        pass
    except Exception as e:
        print(f"⚠️ 天气数据解析失败: {str(e)[:100]}")

    if weather_list:
        print(f"🌤️ 从天气数据解析到 {len(weather_list)} 天匹配行程日期的天气: {[w.date for w in weather_list]}")
    else:
        print(f"⚠️ 天气数据解析后无匹配行程日期的天气，行程: {trip_start} 至 {trip_end}")
        print(f"  原始数据前200字符: {str(weather_data)[:200]}")
    return weather_list


def _missing_date_ranges(dates: list[str]) -> list[tuple[str, str]]:
    if not dates:
        return []
    sorted_dates = sorted(dates)
    ranges: list[tuple[str, str]] = []
    start = prev = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    for date_str in sorted_dates[1:]:
        current = datetime.strptime(date_str, "%Y-%m-%d")
        if current == prev + timedelta(days=1):
            prev = current
            continue
        ranges.append((start.strftime("%Y-%m-%d"), prev.strftime("%Y-%m-%d")))
        start = prev = current
    ranges.append((start.strftime("%Y-%m-%d"), prev.strftime("%Y-%m-%d")))
    return ranges


async def _build_weather_list(request, weather_data: Any) -> list[WeatherInfo]:
    trip_start = request.start_date
    trip_end = request.end_date
    expected_dates = _trip_dates(trip_start, request.travel_days)
    weather_list = _parse_weather_payload(weather_data, trip_start, trip_end)

    by_date: dict[str, WeatherInfo] = {}
    for weather in weather_list:
        if weather.date in expected_dates and weather.date not in by_date:
            by_date[weather.date] = weather

    missing_dates = [date for date in expected_dates if date not in by_date]
    if missing_dates:
        print(f"🌤️ 高德天气缺少 {len(missing_dates)} 天，尝试使用 Open-Meteo 补全: {missing_dates}")
        for start_date, end_date in _missing_date_ranges(missing_dates):
            try:
                open_meteo_weather = await fetch_open_meteo_weather(
                    request.city,
                    start_date,
                    end_date,
                )
                for weather in open_meteo_weather:
                    if weather.date in missing_dates and weather.date not in by_date:
                        by_date[weather.date] = weather
            except Exception as e:
                print(f"⚠️ Open-Meteo 天气补全失败: {str(e)[:120]}")

    remaining_missing = [date for date in expected_dates if date not in by_date]
    if remaining_missing:
        print(f"🌤️ 仍缺少 {len(remaining_missing)} 天天气，根据{request.city}季节气候补全...")
        for date_str in remaining_missing:
            seasonal = _get_seasonal_weather(request.city, date_str)
            by_date[date_str] = WeatherInfo(
                date=date_str,
                day_weather=seasonal["day_weather"],
                night_weather=seasonal["night_weather"],
                day_temp=seasonal["day_temp"],
                night_temp=seasonal["night_temp"],
                wind_direction=seasonal["wind_direction"],
                wind_power=seasonal["wind_power"],
            )

    completed = [by_date[date] for date in expected_dates if date in by_date]
    print(f"✅ 天气数据准备完成: {[(w.date, f'{w.day_temp}°C', w.day_weather) for w in completed]}")
    return completed


MACRO_PLANNER_PROMPT = """你是旅行宏观编排专家。你的唯一任务是根据景点聚类分组和酒店信息，输出一个极浅的行程骨架。

**严格约束：**
1. 不要输出任何坐标、路线、餐饮细节
2. 每天的attraction_names必须来自聚类分组中的真实景点名称
3. 每天安排2-3个景点
4. hotel_name从酒店搜索结果中选择一个合适的酒店名称
5. **必须严格按照用户要求的旅行天数生成days数组**，不能减少天数。如果景点不够，某些天可以安排2个景点或适当放松
6. **total_days必须等于用户要求的旅行天数**

请严格按照以下JSON格式返回：
```json
{
  "city": "城市名称",
  "total_days": 3,
  "transportation": "交通方式",
  "accommodation": "住宿偏好",
  "days": [
    {
      "day_index": 0,
      "date": "YYYY-MM-DD",
      "attraction_names": ["景点A", "景点B"],
      "hotel_name": "酒店名称"
    }
  ]
}
```"""


DAY_PLAN_GENERATOR_PROMPT = """你是单日行程规划专家。你的任务是为指定的一天生成详细的行程计划。

请严格按照以下JSON格式返回单日行程：
```json
{
  "date": "YYYY-MM-DD",
  "day_index": 0,
  "description": "当日行程概述",
  "transportation": "交通方式",
  "accommodation": "住宿类型",
  "hotel": {
    "name": "酒店名称",
    "address": "酒店地址",
    "location": {"longitude": 116.397128, "latitude": 39.916527},
    "price_range": "300-500元",
    "rating": "4.5",
    "distance": "距离景点2公里",
    "type": "经济型酒店",
    "estimated_cost": 400,
    "star_rating": 3.0,
    "price": 350,
    "original_price": 500,
    "currency": "CNY",
    "hotel_amenities": ["免费WiFi", "停车场", "餐厅"],
    "room_amenities": ["空调", "独立卫浴"],
    "description": "酒店简介",
    "image_url": "酒店图片URL(从搜索数据提取)",
    "detail_url": "酒店详情页URL(从搜索数据提取)",
    "distance_in_meters": 2000
  },
  "attractions": [
    {
      "name": "景点名称",
      "address": "详细地址",
      "location": {"longitude": 116.397128, "latitude": 39.916527},
      "visit_duration": 120,
      "description": "景点描述",
      "category": "景点类别",
      "ticket_price": 60
    }
  ],
  "meals": [
    {
      "type": "breakfast",
      "name": "餐厅名称",
      "address": "餐厅地址",
      "location": {"longitude": 116.397128, "latitude": 39.916527},
      "description": "推荐理由",
      "cuisine": "菜系",
      "rating": 4.5,
      "avg_cost": 80,
      "distance": "距离景点500米",
      "source": "nearby",
      "estimated_cost": 30
    },
    {
      "type": "lunch",
      "name": "餐厅名称",
      "address": "餐厅地址",
      "location": {"longitude": 116.397128, "latitude": 39.916527},
      "description": "推荐理由",
      "cuisine": "菜系",
      "rating": 4.5,
      "avg_cost": 80,
      "distance": "距离景点200米",
      "source": "nearby",
      "estimated_cost": 50
    },
    {
      "type": "dinner",
      "name": "餐厅名称",
      "address": "餐厅地址",
      "location": {"longitude": 116.397128, "latitude": 39.916527},
      "description": "推荐理由",
      "cuisine": "菜系",
      "rating": 4.5,
      "avg_cost": 120,
      "distance": "距离酒店1公里",
      "source": "popular",
      "estimated_cost": 80
    }
  ],
}
```

**重要提示:**
1. **date字段必须严格等于输入中给定的日期，不要编造**
2. **day_index必须等于输入中给定的day_index**
3. **景点名称必须来自输入中指定的attraction_names列表，不要添加其他景点**
4. **route_segments由系统自动生成，你无需生成此字段**，即使你输出了也会被系统覆盖
5. **每天必须包含早中晚三餐(meals)**，source字段：breakfast/lunch用nearby，dinner用popular
6. **每个景点和餐厅的location必须包含经纬度坐标**，从搜索数据中提取
7. **hotel 必须严格来自输入的"当日酒店候选"列表**，优先选第 1 个（已按距离/星级排序）。把候选中的 name/address/location/star_rating/price/hotel_amenities/room_amenities/image_url/detail_url/distance_in_meters 字段照搬，不要编造 URL/设施列表。
8. **结合天气信息安排行程**：根据当天天气情况，在description中给出穿衣和出行建议（如雨天带伞、晴天防晒等）
9. **JSON必须严格合法且完整**：属性名用双引号，不要有尾随逗号，不要有注释
10. **meals 中每一餐必须严格来自输入的"当日餐厅候选"对应分组**（breakfast 取自 breakfast 列表, lunch 取自 lunch, dinner 取自 dinner）。直接照搬候选的 name/address/location/rating/avg_cost/open_hours/cuisine/source/tel 字段，**禁止跨组挪用或编造**。
11. **提供实用的旅行建议**，如最佳游览时间、注意事项等
12. **hotel的AIGoHotel字段必须从酒店搜索数据中提取**：star_rating, price, original_price, hotel_amenities, room_amenities, description, image_url, detail_url, distance_in_meters 这些字段如果搜索数据中有，必须原样填入，不要编造URL或设施列表"""


GLOBAL_SYNTHESIZER_PROMPT = """你是旅行综合建议专家。你的任务是根据行程摘要，输出全局旅行建议和消费分析。

**严格约束：**
1. 仅输出建议文本，不要输出任何行程细节
2. 建议应包含：出行注意事项、预算分析、天气提醒、交通建议
3. 输出纯文本即可，不需要JSON格式"""


async def generate_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📋 [DEPRECATED] 执行节点: generate_plan_node (旧版单体节点)")
    request = state["request"]
    attractions = _truncate_info(state.get("attractions_info", ""), 4000)
    weather = _truncate_info(state.get("weather_info", ""), 1500)
    hotels = _truncate_info(state.get("hotels_info", ""), 2000)
    food = _truncate_info(state.get("food_info", ""), 2000)
    cluster = _truncate_info(state.get("cluster_info", ""), 3000)
    routes = _truncate_info(state.get("route_info", ""), 2000)

    prompt = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 美食偏好: {request.food_preference}

**收集到的信息:**
[景点]: {attractions}
[天气]: {weather}
[酒店]: {hotels}
[美食]: {food}
[景点聚类分组]: {cluster}
[路线]: {routes if routes else "路线搜索数据不可用，请根据景点间距离和交通方式自行估算路线信息"}

**关键要求:**
1. **严格按照[景点聚类分组]的建议安排每日景点**，将同一组的景点安排在同一天，不要随意打散
2. 每组内的景点按照聚类给出的顺序安排游览（已按最近邻排序）
3. 如果聚类分组中某天景点过多或过少，可以适当调整，但必须保持地理位置相近的景点在同一天
4. 每天的餐饮推荐要结合当天的景点位置（早餐和午餐选景点周边，晚餐可选城市热门）
5. **每个景点的location字段必须包含经纬度坐标**，从[景点]搜索结果中提取，不要留空或编造
6. **每天必须包含route_segments路线段**，即使路线搜索数据不可用，也要根据景点位置和交通方式估算距离和时间
7. **返回的JSON必须严格合法**：属性名用双引号，不要有尾随逗号，不要有注释
8. **JSON必须完整输出**，不要因为长度限制而截断，overall_suggestions和budget字段必须包含
"""
    if request.free_text_input:
        prompt += f"\n**额外要求:** {request.free_text_input}"

    llm = get_llm()
    messages = [SystemMessage(content=PLANNER_AGENT_PROMPT), HumanMessage(content=prompt)]

    structured_llm = None
    if is_structured_output_supported():
        try:
            structured_llm = llm.with_structured_output(TripPlan, method="function_calling")
            print("🔧 使用 Structured Output (function_calling) 模式生成计划")
        except Exception as e:
            print(f"⚠️ Structured Output 不可用，使用手动JSON解析: {e}")
    else:
        print("ℹ️ 当前模型不支持 Structured Output，直接使用手动JSON解析")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if structured_llm is not None:
                try:
                    trip_plan = await structured_llm.ainvoke(messages)
                    if trip_plan is not None:
                        return {"trip_plan": _validate_plan_coordinates(trip_plan)}
                    print("⚠️ Structured Output 返回空结果，降级到手动解析")
                except Exception as e:
                    err_msg = str(e)
                    if "response_format" in err_msg or "unavailable" in err_msg or "400" in err_msg:
                        print(f"⚠️ Structured Output 不受API支持，降级到手动解析: {err_msg[:100]}")
                    else:
                        print(f"⚠️ Structured Output 调用失败，降级到手动解析: {err_msg[:100]}")
                structured_llm = None

            response = await _invoke_llm_with_retry(llm, messages)
            trip_plan = _parse_response(response.content, request)
            return {"trip_plan": trip_plan}
        except Exception as e:
            print(f"⚠️ 解析计划失败 (尝试 {attempt + 1}/{max_attempts}): {str(e)[:200]}")
            if attempt < max_attempts - 1:
                prompt = f"""上一次生成的JSON格式有误或被截断。请重新生成，确保：
1. 所有属性名用双引号包裹
2. 不要有尾随逗号（如 "a": 1, }} 或 [1, ]）
3. 不要有注释
4. **JSON必须完整**，尤其是最后的overall_suggestions和budget字段不能省略
5. 如果输出太长，可以简化description字段，但不要省略任何结构字段

错误信息: {str(e)[:100]}

请根据以下信息重新生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 美食偏好: {request.food_preference}

**收集到的信息:**
[景点]: {attractions}
[天气]: {weather}
[酒店]: {hotels}
[美食]: {food}
[景点聚类分组]: {cluster}
[路线]: {routes if routes else "路线搜索数据不可用，请根据景点间距离和交通方式自行估算路线信息"}

**关键要求:**
1. 严格按照[景点聚类分组]的建议安排每日景点
2. 每个景点的location字段必须包含经纬度坐标
3. 每天必须包含route_segments路线段
4. 返回的JSON必须严格合法且完整"""
                if request.free_text_input:
                    prompt += f"\n**额外要求:** {request.free_text_input}"
                messages = [SystemMessage(content=PLANNER_AGENT_PROMPT), HumanMessage(content=prompt)]
            else:
                print(f"❌ 解析计划最终失败，使用备用方案")
                return {"trip_plan": None, "errors": [f"generate_plan: 解析计划最终失败 - {str(e)[:200]}"]}


async def macro_planner_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🏗️ 执行节点: macro_planner_node (宏观编排器)")
    request = state["request"]
    cluster = _truncate_info(state.get("cluster_info", ""), 3000)
    hotels = _truncate_info(state.get("hotels_info", ""), 2500)

    prompt = f"""请根据以下信息，为{request.city}的{request.travel_days}天旅行生成行程骨架。

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 交通方式: {request.transportation}
- 住宿偏好: {request.accommodation}

**景点聚类分组:**
{cluster}

**可选酒店(行程级候选，已按到行程质心距离排序，每天显示同一份候选):**
{hotels}

**要求:**
1. 严格按照聚类分组安排每日景点，同一组的景点必须在同一天
2. 每天的attraction_names必须来自聚类分组中的真实景点名称
3. 每天安排2-3个景点
4. hotel_name **必须从"候选酒店"列表中挑选一个真实酒店名称**（优先选第 1 个，已按距离/星级排序）。**同一城市的多天行程默认每天选同一家酒店**（不需要每天换酒店），除非聚类明显远离同一商圈。
5. 不要输出任何坐标、路线、餐饮细节，仅输出骨架
6. **每天的date字段必须严格等于用户要求的日期**：第{request.start_date}天到第{request.end_date}天，不要编造日期
7. **必须生成{request.travel_days}天的行程骨架，不能减少天数**。如果聚类景点不够分配，可以某些天安排2个景点或适当放松，但days数组长度必须等于{request.travel_days}"""

    if request.free_text_input:
        from .search import analyze_free_text
        analysis = await analyze_free_text(request.free_text_input)
        must_visit = analysis.get("attractions", [])
        must_visit_hint = ""
        if must_visit:
            must_visit_hint = f"""

**⚠️ 最高优先级 - 用户明确指定必游景点:**
{', '.join(must_visit)}
这些景点必须出现在行程骨架中！每天的attraction_names必须包含这些景点。如果聚类分组中没有这些景点，请自行添加到合适的天数中。"""

        food_hint = ""
        food_prefs = analysis.get("food_preferences", [])
        if food_prefs:
            food_hint = f"""

**用户美食偏好:** {', '.join(food_prefs)}（这些是美食偏好，不是景点，不要放入attraction_names）"""

        accom_hint = ""
        accom_prefs = analysis.get("accommodation_preferences", [])
        if accom_prefs:
            accom_hint = f"""

**用户住宿偏好:** {', '.join(accom_prefs)}"""

        general_hint = ""
        general_suggs = analysis.get("general_suggestions", [])
        if general_suggs:
            general_hint = f"""

**用户其他要求:** {', '.join(general_suggs)}"""

        prompt += f"\n**额外要求:** {request.free_text_input}" + must_visit_hint + food_hint + accom_hint + general_hint

    llm = get_llm()
    messages = [SystemMessage(content=MACRO_PLANNER_PROMPT), HumanMessage(content=prompt)]

    structured_llm = None
    if is_structured_output_supported():
        try:
            structured_llm = llm.with_structured_output(MacroPlan, method="function_calling")
            print("🔧 Macro-Planner 使用 Structured Output 模式")
        except Exception as e:
            print(f"⚠️ Macro-Planner Structured Output 不可用: {e}")
    else:
        print("ℹ️ Macro-Planner 当前模型不支持 Structured Output，使用手动JSON解析")

    if structured_llm is not None:
        try:
            macro_plan = await structured_llm.ainvoke(messages)
            if macro_plan is not None:
                # 后处理：强制天数等于 travel_days
                from datetime import datetime, timedelta
                start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
                expected_days = request.travel_days
                actual_days = len(macro_plan.days)

                if actual_days < expected_days:
                    print(f"⚠️ LLM返回天数不足({actual_days} < {expected_days})，补充空白天数")
                    existing_dates = {d.date for d in macro_plan.days}
                    for i in range(expected_days):
                        current_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                        if current_date not in existing_dates:
                            macro_plan.days.append(DaySkeleton(
                                day_index=i,
                                date=current_date,
                                attraction_names=[f"{request.city}推荐景点"],
                                hotel_name=macro_plan.days[-1].hotel_name if macro_plan.days else "",
                            ))
                    macro_plan.days.sort(key=lambda d: d.date)
                    for idx, d in enumerate(macro_plan.days):
                        d.day_index = idx
                    macro_plan.total_days = expected_days
                elif actual_days > expected_days:
                    print(f"⚠️ LLM返回天数过多({actual_days} > {expected_days})，截断多余天数")
                    macro_plan.days = macro_plan.days[:expected_days]
                    macro_plan.total_days = expected_days

                # 始终按日期排序并重新编号 day_index
                macro_plan.days.sort(key=lambda d: d.date)
                for idx, d in enumerate(macro_plan.days):
                    d.day_index = idx

                print(f"✅ 宏观编排完成: {macro_plan.total_days}天, 共{sum(len(d.attraction_names) for d in macro_plan.days)}个景点")
                return {"macro_plan": macro_plan}
            print("⚠️ Structured Output 返回空结果，降级到手动解析")
        except Exception as e:
            print(f"⚠️ Structured Output 失败，降级到手动解析: {str(e)[:100]}")

    try:
        response = await _invoke_llm_with_retry(llm, messages)
        content = response.content

        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "{" in content:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            json_str = content[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON数据")

        data = json.loads(json_str)
        macro_plan = MacroPlan(**data)

        # 后处理：强制天数等于 travel_days
        from datetime import datetime, timedelta
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        expected_days = request.travel_days
        actual_days = len(macro_plan.days)

        if actual_days < expected_days:
            print(f"⚠️ LLM返回天数不足({actual_days} < {expected_days})，补充空白天数")
            existing_dates = {d.date for d in macro_plan.days}
            for i in range(expected_days):
                current_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                if current_date not in existing_dates:
                    macro_plan.days.append(DaySkeleton(
                        day_index=i,
                        date=current_date,
                        attraction_names=[f"{request.city}推荐景点"],
                        hotel_name=macro_plan.days[-1].hotel_name if macro_plan.days else "",
                    ))
            macro_plan.days.sort(key=lambda d: d.date)
            # 重新设置 day_index
            for idx, d in enumerate(macro_plan.days):
                d.day_index = idx
            macro_plan.total_days = expected_days
        elif actual_days > expected_days:
            print(f"⚠️ LLM返回天数过多({actual_days} > {expected_days})，截断多余天数")
            macro_plan.days = macro_plan.days[:expected_days]
            macro_plan.total_days = expected_days

        # 始终按日期排序并重新编号 day_index
        macro_plan.days.sort(key=lambda d: d.date)
        for idx, d in enumerate(macro_plan.days):
            d.day_index = idx

        print(f"✅ 宏观编排完成(手动解析): {macro_plan.total_days}天, 共{sum(len(d.attraction_names) for d in macro_plan.days)}个景点")
        return {"macro_plan": macro_plan}
    except Exception as e:
        print(f"❌ 宏观编排失败，使用默认骨架: {str(e)[:200]}")
        from datetime import datetime, timedelta
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        default_days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            default_days.append(DaySkeleton(
                day_index=i,
                date=current_date.strftime("%Y-%m-%d"),
                attraction_names=[f"{request.city}推荐景点"],
                hotel_name="",
            ))
        macro_plan = MacroPlan(
            city=request.city,
            total_days=request.travel_days,
            days=default_days,
            transportation=request.transportation,
            accommodation=request.accommodation,
        )
        return {"macro_plan": macro_plan}


def _find_coord(name: str, coords_list: List[Dict]) -> Optional[Dict]:
    """多层级模糊坐标匹配：精确 → 子串 → 去后缀 → Jaccard"""
    for c in coords_list:
        if c["name"] == name:
            return c
    for c in coords_list:
        if name in c["name"] or c["name"] in name:
            return c
    suffixes = ["景区", "风景区", "风景名胜区", "公园", "博物馆", "博物院", "纪念馆", "遗址"]
    stripped = name
    for s in suffixes:
        stripped = stripped.replace(s, "")
    if stripped and stripped != name:
        for c in coords_list:
            c_stripped = c["name"]
            for s in suffixes:
                c_stripped = c_stripped.replace(s, "")
            if stripped in c_stripped or c_stripped in stripped:
                return c
    if len(name) >= 2:
        name_chars = set(name)
        for c in coords_list:
            c_chars = set(c["name"])
            intersection = name_chars & c_chars
            union = name_chars | c_chars
            if union and len(intersection) / len(union) >= 0.5:
                return c
    return None


def _extract_wp(item: Dict, all_coords: List[Dict]) -> Optional[Dict]:
    """从 day_plan 中的景点/餐厅/酒店 dict 提取 waypoint，无坐标时模糊匹配"""
    name = item.get("name", "")
    if not name:
        return None
    loc = item.get("location")
    if isinstance(loc, dict):
        lon = loc.get("longitude")
        lat = loc.get("latitude")
        if lon and lat:
            try:
                lon, lat = float(lon), float(lat)
                if 73 < lon < 136 and 3 < lat < 54:
                    return {"name": name, "longitude": lon, "latitude": lat}
            except (ValueError, TypeError):
                pass
    coord = _find_coord(name, all_coords)
    if coord:
        return {"name": name, "longitude": coord["longitude"], "latitude": coord["latitude"]}
    return None


async def day_route_planner_node(state: DayPlanLocalState) -> Dict[str, Any]:
    """从 LLM 生成的 day_plan 中按时间线顺序提取 waypoints 并规划全部路线段"""
    from ..utils.geo import _extract_coordinates_regex
    from ..utils.route import compute_route_segments

    day_index = state["day_index"]
    city = state["city"]
    transportation = state["transportation"]

    day_plan_data = state.get("day_plan")
    if not day_plan_data:
        print(f"🗺️ 单日路线规划: 第{day_index + 1}天, day_plan 为空，跳过")
        return {"route_segments_data": []}

    if not isinstance(day_plan_data, dict):
        day_plan_data = day_plan_data.model_dump() if hasattr(day_plan_data, "model_dump") else dict(day_plan_data)

    print(f"🗺️ 单日路线规划: 第{day_index + 1}天 (完整时间线)")

    attractions_info = state.get("attractions_info", "")
    hotels_info = state.get("hotels_info", "")
    cluster_info = state.get("cluster_info", "")
    day_food_info = state.get("day_food_info", "")

    all_coords = _extract_coordinates_regex(attractions_info)
    hotel_coords = _extract_coordinates_regex(hotels_info)
    cluster_coords = _extract_coordinates_regex(cluster_info) if cluster_info else []
    food_coords = _extract_coordinates_regex(day_food_info) if day_food_info else []
    combined_coords = all_coords + hotel_coords + cluster_coords + food_coords

    hotel = day_plan_data.get("hotel") or {}
    attractions = day_plan_data.get("attractions") or []
    meals = day_plan_data.get("meals") or []

    breakfast = next((m for m in meals if m.get("type") == "breakfast"), None)
    lunch = next((m for m in meals if m.get("type") == "lunch"), None)
    dinner = next((m for m in meals if m.get("type") == "dinner"), None)

    timeline = []
    if hotel:
        timeline.append(hotel)
    if breakfast:
        timeline.append(breakfast)

    lunch_inserted = False
    mid = max(len(attractions) // 2, 1)
    for i, attr in enumerate(attractions):
        timeline.append(attr)
        if not lunch_inserted and lunch and i == mid - 1:
            timeline.append(lunch)
            lunch_inserted = True
    if not lunch_inserted and lunch:
        timeline.append(lunch)

    if dinner:
        timeline.append(dinner)
    if hotel:
        timeline.append(hotel)

    waypoints = []
    for item in timeline:
        wp = _extract_wp(item, combined_coords)
        if wp:
            if waypoints and wp["longitude"] == waypoints[-1]["longitude"] and wp["latitude"] == waypoints[-1]["latitude"]:
                continue
            waypoints.append(wp)
        else:
            print(f"  ⚠️ 未找到坐标: {item.get('name', '?')}")

    if len(waypoints) < 2:
        print(f"  ⚠️ 路径点不足({len(waypoints)}个)，跳过路线规划")
        return {"route_segments_data": []}

    segments = await compute_route_segments(waypoints, transportation, city)
    print(f"  ✅ 生成 {len(segments)} 段路线 (共{len(waypoints)}个路径点)")

    day_plan_data["route_segments"] = segments
    return {"day_plan": day_plan_data, "route_segments_data": segments}


async def day_plan_generator_node(state: DayPlanLocalState) -> Dict[str, Any]:
    day_index = state["day_index"]
    date = state["date"]
    attraction_names = state["attraction_names"]
    hotel_name = state["hotel_name"]
    city = state["city"]
    transportation = state["transportation"]
    accommodation = state["accommodation"]
    last_error = state.get("last_error", "")
    retry_count = state.get("retry_count", 0)

    print(f"📝 单日生成器: 第{day_index + 1}天 ({date}), 景点: {attraction_names}, 重试: {retry_count}")

    attractions_info = _truncate_info(state.get("attractions_info", ""), 3000)
    day_hotels_info = state.get("day_hotels_info", "")
    hotels_info = _truncate_info(day_hotels_info if day_hotels_info else state.get("hotels_info", ""), 3000)
    day_food_info = state.get("day_food_info", "")
    food_info = _truncate_info(day_food_info if day_food_info else state.get("food_info", ""), 2500)
    weather_info = _truncate_info(state.get("weather_info", ""), 800)
    cluster_info = _truncate_info(state.get("cluster_info", ""), 2000)

    error_hint = ""
    if last_error:
        error_hint = f"""
**⚠️ 上次生成失败，错误信息:**
{last_error}

请根据以上错误信息修正输出，特别注意：
- 如果是JSON格式错误，确保双引号、无尾随逗号、无注释
- 如果是字段缺失，确保所有必要字段都包含
- 如果是坐标无效，确保经纬度在中国范围内(经度73-136, 纬度3-54)
"""

    prompt = f"""请为{city}的第{day_index + 1}天({date})生成详细行程计划。

**当日安排:**
- 景点: {', '.join(attraction_names)}
- 入住酒店: {hotel_name or '待定'}
- 交通方式: {transportation}
- 住宿偏好: {accommodation}

**搜索数据:**
[景点详情]: {attractions_info}
[当日酒店候选(已按当日活动中心距离排好序，请从中挑选)]: {hotels_info}
[当日餐厅候选(JSON格式，按早午晚分组，已按评分+距离排序)]: {food_info}
[天气信息]: {weather_info}
[聚类分组]: {cluster_info}
{error_hint}
**关键要求:**
1. 景点名称必须来自: {', '.join(attraction_names)}
2. 每个景点的location必须包含经纬度坐标(从搜索数据提取)
3. 必须包含早中晚三餐(meals)
4. **meals 中的餐厅必须严格来自[当日餐厅候选]中的对应分组**（breakfast 从 breakfast 列表挑, lunch 从 lunch, dinner 从 dinner），不要编造餐厅，不要跨组挪用。直接复制 name/address/location/rating/avg_cost/open_hours/cuisine/source 字段。
5. **hotel 必须严格来自[当日酒店候选]列表**，优先选第 1 个（已按距离/星级排序）。把候选中的 name/address/location/star_rating/price/hotel_amenities/room_amenities/image_url/detail_url/distance_in_meters 字段照搬，不要编造。
6. route_segments由系统自动生成，你不需要生成
7. JSON必须严格合法且完整"""

    llm = get_llm()
    messages = [SystemMessage(content=DAY_PLAN_GENERATOR_PROMPT), HumanMessage(content=prompt)]

    try:
        response = await _invoke_llm_with_retry(llm, messages)
        content = response.content

        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "{" in content:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            json_str = content[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON数据")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            from ..utils.parsing import _repair_json
            data = json.loads(_repair_json(json_str))

        data.setdefault("date", date)
        data["day_index"] = day_index
        data.setdefault("transportation", transportation)
        data.setdefault("accommodation", accommodation)
        data.setdefault("route_segments", [])
        data.setdefault("meals", [])

        if "attractions" in data and isinstance(data["attractions"], list):
            for attr in data["attractions"]:
                if isinstance(attr, dict):
                    attr.setdefault("visit_duration", 120)
                    attr.setdefault("category", "景点")
                    attr.setdefault("ticket_price", 0)

        day_plan = DayPlan(**data)
        day_plan = _validate_plan_coordinates_single_day(day_plan)

        return {
            "day_plan": day_plan.model_dump(),
            "retry_count": retry_count + 1,
            "last_error": "",
        }
    except Exception as e:
        err_msg = str(e)[:300]
        print(f"⚠️ 第{day_index + 1}天生成失败 (重试{retry_count + 1}): {err_msg}")
        return {
            "day_plan": None,
            "retry_count": retry_count + 1,
            "last_error": err_msg,
        }


def _validate_plan_coordinates_single_day(day_plan: DayPlan) -> DayPlan:
    for attr in day_plan.attractions:
        if attr.location is not None:
            lon = attr.location.longitude
            lat = attr.location.latitude
            if not (73 < lon < 136 and 3 < lat < 54):
                attr.location = None
    for meal in day_plan.meals:
        if meal.location is not None:
            lon = meal.location.longitude
            lat = meal.location.latitude
            if not (73 < lon < 136 and 3 < lat < 54):
                meal.location = None
    return day_plan


def day_plan_validator_node(state: DayPlanLocalState) -> Dict[str, Any]:
    day_index = state["day_index"]
    day_plan_data = state.get("day_plan")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if day_plan_data is None:
        return {"last_error": f"第{day_index + 1}天: day_plan为空，生成失败"}

    try:
        if isinstance(day_plan_data, dict):
            day_plan = DayPlan(**day_plan_data)
        elif isinstance(day_plan_data, DayPlan):
            day_plan = day_plan_data
        else:
            return {"last_error": f"第{day_index + 1}天: day_plan类型异常: {type(day_plan_data)}"}
    except Exception as e:
        return {"last_error": f"第{day_index + 1}天: DayPlan解析失败 - {str(e)[:200]}"}

    errors = []
    if not day_plan.attractions:
        errors.append("景点列表为空")
    if len(day_plan.meals) < 3:
        meal_types = {m.type for m in day_plan.meals}
        for required in ["breakfast", "lunch", "dinner"]:
            if required not in meal_types:
                errors.append(f"缺少{required}餐")
    if not day_plan.route_segments:
        has_coords = sum(1 for a in day_plan.attractions if a.location) + (1 if day_plan.hotel and day_plan.hotel.location else 0)
        if has_coords >= 2:
            errors.append("路线段为空")

    for attr in day_plan.attractions:
        if attr.location is not None:
            lon = attr.location.longitude
            lat = attr.location.latitude
            if not (73 < lon < 136 and 3 < lat < 54):
                errors.append(f"景点{attr.name}坐标超出中国范围")

    if errors:
        err_msg = "; ".join(errors)
        print(f"⚠️ 第{day_index + 1}天校验失败: {err_msg}")
        return {"last_error": f"第{day_index + 1}天校验失败: {err_msg}"}

    print(f"✅ 第{day_index + 1}天校验通过: {len(day_plan.attractions)}个景点, {len(day_plan.meals)}餐, {len(day_plan.route_segments)}路线段")
    return {"last_error": "", "day_plan": day_plan.model_dump(), "day_plans": [day_plan.model_dump()]}


def _should_retry_or_fallback(state: DayPlanLocalState) -> str:
    last_error = state.get("last_error", "")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if not last_error:
        return "done"
    if retry_count < max_retries:
        print(f"🔄 第{state['day_index'] + 1}天将重试 (已尝试{retry_count}次)")
        return "retry"
    print(f"🛡️ 第{state['day_index'] + 1}天重试耗尽，进入降级兜底")
    return "fallback"


def _extract_meals_from_food_info(day_food_info: str, city: str) -> List:
    """从 day_food_search_node 的搜索结果中解析真实餐厅，分配到早中晚三餐。

    优先识别新版结构化 JSON（{breakfast:[...], lunch:[...], dinner:[...]}）；
    若不是 JSON 则回退到旧版高德文本解析。
    """
    if not day_food_info:
        return [
            Meal(type="breakfast", name="当地特色早餐", description="当地特色早餐", cuisine="本地菜", source="nearby", estimated_cost=30),
            Meal(type="lunch", name="午餐推荐", description="午餐推荐", cuisine="本地菜", source="nearby", estimated_cost=50),
            Meal(type="dinner", name="晚餐推荐", description="晚餐推荐", cuisine="本地菜", source="popular", estimated_cost=80),
        ]

    # 新版：JSON 结构（食物 search node 输出）
    try:
        parsed = json.loads(day_food_info)
        if isinstance(parsed, dict) and any(k in parsed for k in ("breakfast", "lunch", "dinner")):
            meals: List[Meal] = []
            default_cost = {"breakfast": 30, "lunch": 50, "dinner": 80}
            for meal_type in ("breakfast", "lunch", "dinner"):
                candidates = parsed.get(meal_type) or []
                if candidates and isinstance(candidates[0], dict):
                    cand = candidates[0]
                    loc = None
                    cand_loc = cand.get("location")
                    if isinstance(cand_loc, dict) and cand_loc.get("longitude") and cand_loc.get("latitude"):
                        loc = Location(longitude=cand_loc["longitude"], latitude=cand_loc["latitude"])
                    meals.append(Meal(
                        type=meal_type,
                        name=cand.get("name") or f"{city}{'早餐' if meal_type == 'breakfast' else '午餐' if meal_type == 'lunch' else '晚餐'}",
                        address=cand.get("address"),
                        location=loc,
                        cuisine=cand.get("cuisine") or "本地菜",
                        rating=cand.get("rating"),
                        avg_cost=cand.get("avg_cost"),
                        distance=cand.get("distance"),
                        source=cand.get("source") or ("popular" if meal_type == "dinner" else "nearby"),
                        estimated_cost=cand.get("avg_cost") or default_cost[meal_type],
                        open_hours=cand.get("open_hours"),
                        tel=cand.get("tel"),
                    ))
                else:
                    meals.append(Meal(
                        type=meal_type,
                        name=f"{city}{'早餐' if meal_type == 'breakfast' else '午餐' if meal_type == 'lunch' else '晚餐'}推荐",
                        description="推荐餐厅",
                        cuisine="本地菜",
                        source="popular" if meal_type == "dinner" else "nearby",
                        estimated_cost=default_cost[meal_type],
                    ))
            return meals
    except (json.JSONDecodeError, TypeError):
        pass

    # 旧版：高德文本格式
    nearby_restaurants = []
    popular_restaurants = []
    for line in day_food_info.split("\n"):
        if not line.strip():
            continue
        is_text_search = "maps_text_search" in line
        colon_idx = line.find("]: ")
        raw = line[colon_idx + 3:] if colon_idx >= 0 else line

        pois = _parse_amap_pois(raw)
        for poi in pois:
            if is_text_search:
                popular_restaurants.append(poi)
            else:
                nearby_restaurants.append(poi)

    meals = []
    used_names = set()

    def _pick(pool: list, meal_type: str, source: str, default_cost: int) -> "Meal":
        for r in pool:
            if r["name"] not in used_names:
                used_names.add(r["name"])
                loc = None
                if r.get("longitude") and r.get("latitude"):
                    loc = Location(longitude=r["longitude"], latitude=r["latitude"])
                return Meal(
                    type=meal_type, name=r["name"], address=r.get("address", ""),
                    location=loc, description=r.get("type", ""), cuisine=r.get("type", "本地菜"),
                    rating=r.get("rating"), source=source, estimated_cost=default_cost,
                )
        return Meal(type=meal_type, name=f"{city}{'早餐' if meal_type == 'breakfast' else '午餐' if meal_type == 'lunch' else '晚餐'}推荐",
                    description="推荐餐厅", cuisine="本地菜", source=source, estimated_cost=default_cost)

    meals.append(_pick(nearby_restaurants, "breakfast", "nearby", 30))
    meals.append(_pick(nearby_restaurants, "lunch", "nearby", 50))
    meals.append(_pick(popular_restaurants or nearby_restaurants, "dinner", "popular", 80))
    return meals


def _parse_amap_pois(raw: str) -> List[Dict]:
    """从高德 API 返回的文本中提取 POI 列表"""
    import re
    pois = []
    try:
        data = json.loads(raw)
        poi_list = []
        if isinstance(data, dict):
            poi_list = data.get("pois", [])
            if not poi_list and "result" in data:
                inner = data["result"]
                if isinstance(inner, str):
                    inner = json.loads(inner)
                if isinstance(inner, dict):
                    poi_list = inner.get("pois", [])
        elif isinstance(data, list):
            poi_list = data

        for p in poi_list:
            if not isinstance(p, dict):
                continue
            name = p.get("name", "")
            if not name:
                continue
            poi = {"name": name, "address": p.get("address", ""), "type": p.get("type", "")}
            loc_str = p.get("location", "")
            if isinstance(loc_str, str) and "," in loc_str:
                parts = loc_str.split(",")
                try:
                    poi["longitude"] = float(parts[0])
                    poi["latitude"] = float(parts[1])
                except (ValueError, IndexError):
                    pass
            rating = p.get("biz_ext", {}).get("rating") if isinstance(p.get("biz_ext"), dict) else None
            if rating:
                try:
                    poi["rating"] = float(rating)
                except (ValueError, TypeError):
                    pass
            pois.append(poi)
    except (json.JSONDecodeError, TypeError):
        name_pattern = re.compile(r'"name"\s*:\s*"([^"]+)"')
        for m in name_pattern.finditer(raw):
            pois.append({"name": m.group(1)})
    return pois


def day_plan_fallback_node(state: DayPlanLocalState) -> Dict[str, Any]:
    day_index = state["day_index"]
    date = state["date"]
    attraction_names = state["attraction_names"]
    hotel_name = state["hotel_name"]
    city = state["city"]
    transportation = state["transportation"]
    accommodation = state["accommodation"]

    print(f"🛡️ 降级兜底: 第{day_index + 1}天 ({date})")

    attractions = []
    for name in attraction_names:
        attractions.append(Attraction(
            name=name,
            address=f"{city}市",
            location=None,
            visit_duration=120,
            description="推荐景点（数据来源受限，建议自行确认详情）",
            category="景点",
            ticket_price=0,
        ))
    if not attractions:
        attractions = [Attraction(
            name=f"{city}推荐景点",
            address=f"{city}市",
            location=None,
            visit_duration=120,
            description="请自行查询景点详情",
            category="景点",
            ticket_price=0,
        )]

    hotel = None
    if hotel_name:
        hotel = Hotel(name=hotel_name, address=f"{city}市", type=accommodation)

    meals = _extract_meals_from_food_info(state.get("day_food_info", ""), city)

    day_plan = DayPlan(
        date=date,
        day_index=day_index,
        description=f"第{day_index + 1}天行程（降级方案）",
        transportation=transportation,
        accommodation=accommodation,
        hotel=hotel,
        attractions=attractions,
        meals=meals,
        route_segments=[],
    )

    print(f"🛡️ 第{day_index + 1}天降级方案已生成: {len(attractions)}个景点, {len([m for m in meals if m.name != '当地特色早餐'])}个真实餐厅")
    return {"day_plan": day_plan.model_dump(), "day_plans": [day_plan.model_dump()]}


def _create_day_plan_subgraph():
    from .food import day_food_search_node

    sub_workflow = StateGraph(DayPlanLocalState)
    sub_workflow.add_node("day_food_search", day_food_search_node)
    sub_workflow.add_node("day_plan_generator", day_plan_generator_node)
    sub_workflow.add_node("day_route_planner", day_route_planner_node)
    sub_workflow.add_node("day_plan_validator", day_plan_validator_node)
    sub_workflow.add_node("day_plan_fallback", day_plan_fallback_node)

    sub_workflow.add_edge(START, "day_food_search")
    sub_workflow.add_edge("day_food_search", "day_plan_generator")
    sub_workflow.add_edge("day_plan_generator", "day_route_planner")
    sub_workflow.add_edge("day_route_planner", "day_plan_validator")
    sub_workflow.add_conditional_edges(
        "day_plan_validator",
        _should_retry_or_fallback,
        {
            "retry": "day_plan_generator",
            "fallback": "day_plan_fallback",
            "done": END,
        }
    )
    sub_workflow.add_edge("day_plan_fallback", END)
    return sub_workflow.compile()


async def day_plan_subgraph_node(state: DayPlanLocalState) -> Dict[str, Any]:
    subgraph = _create_day_plan_subgraph()
    result = await subgraph.ainvoke(state)
    day_plans = result.get("day_plans", [])
    return {"day_plans": day_plans}


async def reduce_assemble_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🔧 执行节点: reduce_assemble_node (归约合并)")
    request = state["request"]
    day_plans_data = state.get("day_plans", [])

    if not day_plans_data:
        print("⚠️ day_plans为空，使用降级方案")
        return {"trip_plan": _create_fallback_plan(request, state)}

    day_plans = []
    for dp_data in day_plans_data:
        try:
            if isinstance(dp_data, dict):
                day_plans.append(DayPlan(**dp_data))
            elif isinstance(dp_data, DayPlan):
                day_plans.append(dp_data)
        except Exception as e:
            print(f"⚠️ DayPlan解析失败: {str(e)[:100]}")

    day_plans.sort(key=lambda d: d.day_index)

    # 跨天餐厅去重：保留首次出现，后续重复替换为通用名称
    seen_meal_names: set = set()
    for dp in day_plans:
        for meal in dp.meals:
            meal_key = meal.name.strip()
            generic_keywords = ["当地特色", "推荐", "自选", "酒店"]
            if meal_key in seen_meal_names and not any(kw in meal_key for kw in generic_keywords):
                fallback_names = {
                    "breakfast": "当地特色早餐",
                    "lunch": "当地特色午餐",
                    "dinner": "当地特色晚餐",
                }
                print(f"  ⚠️ 去重: 第{dp.day_index+1}天 {meal.type} '{meal.name}' 重复，替换")
                meal.name = fallback_names.get(meal.type, "当地特色美食")
                meal.description = "品尝当地特色美食"
            seen_meal_names.add(meal.name.strip())

    total_attractions = sum(
        a.ticket_price for d in day_plans for a in d.attractions
    )
    total_meals = sum(
        m.estimated_cost for d in day_plans for m in d.meals
    )
    total_hotels = sum(
        d.hotel.estimated_cost for d in day_plans if d.hotel and d.hotel.estimated_cost
    )
    total_transportation = max(len(day_plans) * 50, 0)
    total = total_attractions + total_meals + total_hotels + total_transportation

    budget = Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotels,
        total_meals=total_meals,
        total_transportation=total_transportation,
        total=total,
    )

    weather_list = await _build_weather_list(request, state.get("weather_info", ""))

    trip_plan = TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=day_plans,
        weather_info=weather_list,
        overall_suggestions="",
        budget=budget,
    )

    print(f"✅ 归约合并完成: {len(day_plans)}天, 预算{total}元")
    return {"trip_plan": trip_plan}


async def global_synthesizer_node(state: TripPlannerState) -> Dict[str, Any]:
    print("💡 执行节点: global_synthesizer_node (全局综合)")
    trip_plan = state.get("trip_plan")
    if not trip_plan:
        print("⚠️ trip_plan为空，跳过全局综合")
        return {}

    summary_lines = [f"城市：{trip_plan.city}，{len(trip_plan.days)}天行程"]
    for day in trip_plan.days:
        attr_names = "、".join(a.name for a in day.attractions)
        hotel_name = day.hotel.name if day.hotel else "未定"
        summary_lines.append(f"第{day.day_index + 1}天：{attr_names} → 酒店：{hotel_name}")

    if trip_plan.budget:
        summary_lines.append(
            f"总门票：{trip_plan.budget.total_attractions}元，"
            f"总餐饮：{trip_plan.budget.total_meals}元，"
            f"总住宿：{trip_plan.budget.total_hotels}元，"
            f"总交通：{trip_plan.budget.total_transportation}元，"
            f"合计：{trip_plan.budget.total}元"
        )

    weather_info = state.get("weather_info", "")
    if weather_info:
        summary_lines.append(f"天气概况：{_truncate_info(str(weather_info), 300)}")

    request = state.get("request")
    if request and request.free_text_input:
        summary_lines.append(f"用户额外要求：{request.free_text_input}")

    summary_text = "\n".join(summary_lines)

    prompt = f"""根据以下行程摘要，请以JSON格式返回三个字段。

**行程摘要:**
{summary_text}

**要求返回严格JSON格式:**
{{
  "trip_tagline": "8-15字的行程主题标语，体现目的地特色和旅行主题，如'广府文化与寻味之旅'、'江南水乡诗意漫游'",
  "weather_summary": "一句话天气概况，如'晴间多云为主'、'多云转阴，偶有小雨'",
  "overall_suggestions": "使用Markdown格式的完整旅行建议，包含：## 出行建议、## 消费分析、## 天气提醒等章节，使用列表和加粗等格式"
}}

注意：
- trip_tagline 要朗朗上口，体现城市文化特色
- weather_summary 要简洁，不超过10个字
- overall_suggestions 必须使用Markdown格式（标题、列表、加粗等）
- 只返回JSON，不要其他内容"""

    llm = get_llm()
    messages = [SystemMessage(content=GLOBAL_SYNTHESIZER_PROMPT), HumanMessage(content=prompt)]

    try:
        response = await _invoke_llm_with_retry(llm, messages)
        raw = response.content.strip()
        import json as _json
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(raw)
        suggestions = parsed.get("overall_suggestions", "")
        tagline = parsed.get("trip_tagline", "")
        weather_summary = parsed.get("weather_summary", "")
        print(f"💡 全局建议生成完成: tagline={tagline}, weather={weather_summary}")
    except Exception as e:
        print(f"⚠️ 全局建议JSON解析失败，回退纯文本: {str(e)[:80]}")
        try:
            response = await _invoke_llm_with_retry(llm, messages)
            suggestions = response.content.strip()
        except Exception:
            suggestions = "请根据行程安排提前确认景点开放时间和交通信息。建议携带雨具和防晒用品。"
        tagline = ""
        weather_summary = _generate_weather_summary_fallback(trip_plan)

    if not weather_summary:
        weather_summary = _generate_weather_summary_fallback(trip_plan)

    if trip_plan:
        trip_plan.overall_suggestions = suggestions
        trip_plan.trip_tagline = tagline
        trip_plan.weather_summary = weather_summary

    return {"trip_plan": trip_plan, "global_narrative": suggestions}


def _generate_weather_summary_fallback(trip_plan) -> str:
    from collections import Counter
    if not trip_plan.weather_info:
        return ""
    weathers = [w.day_weather for w in trip_plan.weather_info if w.day_weather]
    if not weathers:
        return ""
    counter = Counter(weathers)
    most_common = counter.most_common(1)[0][0]
    if len(counter) == 1:
        return f"{most_common}为主"
    second = counter.most_common(2)[1][0] if len(counter) > 1 else ""
    return f"{most_common}间{second}为主" if second else f"{most_common}为主"

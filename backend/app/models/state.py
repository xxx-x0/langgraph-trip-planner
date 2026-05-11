"""LangGraph State 数据模型

用于 LangGraph 工作流中的状态传递，使用 TypedDict 实现轻量级数据结构。
与 schemas.py 中的 Pydantic 模型不同，这些模型用于中间处理而非 API 序列化。

重构说明:
- 所有列表字段添加 operator.add Reducer，消除并发写入竞态
- 新增 poi_details 字段，避免 fetch_poi_details 覆写整个列表
- 新增 quality_report 字段，支持条件路由
- 移除 6 个冗余字符串字段，统一使用结构化数据 + 序列化辅助函数
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
import operator

from .schemas import Location, TripRequest, TripPlan


def _merge_poi_details(left: Dict[str, Dict[str, Any]], right: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    merged = dict(left)
    merged.update(right)
    return merged


class POIInfo(TypedDict):
    id: str
    name: str
    address: str
    location: Optional[Location]
    typecode: Optional[str]
    photo: Optional[str]


class WeatherData(TypedDict):
    date: str
    day_weather: str
    night_weather: str
    day_temp: int
    night_temp: int
    wind_direction: str
    wind_power: str


class HotelData(TypedDict):
    id: str
    name: str
    address: str
    location: Optional[Location]
    price_range: Optional[str]
    rating: Optional[str]
    type: Optional[str]
    photos: List[str]


class FoodData(TypedDict):
    id: str
    name: str
    address: str
    location: Optional[Location]
    cuisine: Optional[str]
    rating: Optional[float]
    avg_cost: Optional[int]
    photos: List[str]


class ClusterGroup(TypedDict):
    day_index: int
    attractions: List[Dict[str, Any]]
    center: Optional[Location]


class RouteSegmentData(TypedDict):
    from_name: str
    to_name: str
    mode: str
    distance: str
    duration: str
    detail: str


class TripPlannerState(TypedDict):
    request: TripRequest

    attractions: Annotated[List[POIInfo], operator.add]
    weather: Annotated[List[WeatherData], operator.add]
    hotels: Annotated[List[HotelData], operator.add]
    foods: Annotated[List[FoodData], operator.add]
    clusters: Annotated[List[ClusterGroup], operator.add]
    routes: Annotated[List[RouteSegmentData], operator.add]

    poi_details: Annotated[Dict[str, Dict[str, Any]], _merge_poi_details]
    quality_report: Dict[str, Any]

    trip_plan: Optional[TripPlan]
    errors: Annotated[List[str], operator.add]
    messages: Annotated[List[BaseMessage], operator.add]

"""LangGraph State 数据模型

用于 LangGraph 工作流中的状态传递，使用 TypedDict 实现轻量级数据结构。
与 schemas.py 中的 Pydantic 模型不同，这些模型用于中间处理而非 API 序列化。
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
import operator

from .schemas import Location, TripRequest, TripPlan


class POIInfo(TypedDict):
    """POI信息 - 原始搜索数据"""
    id: str
    name: str
    address: str
    location: Optional[Location]
    typecode: Optional[str]
    photo: Optional[str]


class WeatherData(TypedDict):
    """天气数据 - 原始天气查询结果"""
    date: str
    day_weather: str
    night_weather: str
    day_temp: int
    night_temp: int
    wind_direction: str
    wind_power: str


class HotelData(TypedDict):
    """酒店数据 - 原始搜索数据"""
    id: str
    name: str
    address: str
    location: Optional[Location]
    price_range: Optional[str]
    rating: Optional[str]
    type: Optional[str]
    photos: List[str]


class FoodData(TypedDict):
    """美食数据 - 原始搜索数据"""
    id: str
    name: str
    address: str
    location: Optional[Location]
    cuisine: Optional[str]
    rating: Optional[float]
    avg_cost: Optional[int]
    photos: List[str]


class ClusterGroup(TypedDict):
    """聚类分组 - 景点聚类结果"""
    day_index: int
    attractions: List[Dict[str, Any]]
    center: Optional[Location]


class RouteSegmentData(TypedDict):
    """路线段数据 - 路线规划结果"""
    from_name: str
    to_name: str
    mode: str
    distance: str
    duration: str
    detail: str


class TripPlannerState(TypedDict):
    """LangGraph 状态类：管理整个旅行规划流程中的数据流转"""
    # 请求信息
    request: TripRequest

    # 结构化搜索数据（替代原来的字符串）
    attractions: List[POIInfo]
    weather: List[WeatherData]
    hotels: List[HotelData]
    foods: List[FoodData]
    clusters: List[ClusterGroup]
    routes: List[RouteSegmentData]

    # 保留原始字符串用于兼容和调试
    attractions_info: str
    weather_info: str
    hotels_info: str
    food_info: str
    cluster_info: str
    route_info: str

    # 最终结果
    trip_plan: Optional[TripPlan]
    errors: List[str]
    messages: Annotated[List[BaseMessage], operator.add]

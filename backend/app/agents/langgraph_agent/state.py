from typing import TypedDict, Annotated, List, Optional, Any, Dict
import operator

from langchain_core.messages import BaseMessage

from ...models.schemas import TripRequest, TripPlan, UserPreference, MacroPlan


class DiscoveryState(TypedDict):
    """景点发现阶段的状态"""
    request: TripRequest
    discovered_attractions: Annotated[List[dict], operator.add]
    weather_info: str
    errors: List[str]
    messages: Annotated[List[BaseMessage], operator.add]
    user_id: str


class TripPlannerState(TypedDict):
    """LangGraph 状态类：管理整个旅行规划流程中的数据流转"""
    request: TripRequest
    attractions_info: str
    selected_pois: List[dict]
    weather_info: str
    hotels_info: str
    aigohotel_raw_results: str
    selected_hotels: List[dict]
    food_info: str
    cluster_info: str
    route_info: str
    trip_plan: Optional[TripPlan]
    errors: List[str]
    messages: Annotated[List[BaseMessage], operator.add]
    user_preferences: Optional[UserPreference]
    extracted_preferences: Optional[dict]
    user_id: str
    macro_plan: Optional[MacroPlan]
    day_plans: Annotated[List[dict], operator.add]
    global_narrative: Optional[str]
    user_selected_attractions: List[dict]
    user_day_assignments: Optional[List[List[dict]]]
    clusters_data: List[List[dict]]
    hotels_by_day: List[List[dict]]
    dining_pool: List[Dict[str, Any]]   # 每日 DiningPoolDay-shape dict 列表（骨架阶段产物）
    draft_id: Optional[str]              # save_draft_node 写入的草稿 ID


class DayPlanLocalState(TypedDict):
    day_index: int
    date: str
    attraction_names: List[str]
    hotel_name: str
    city: str
    transportation: str
    accommodation: str
    attractions_info: str
    hotels_info: str
    food_info: str
    route_info: str
    weather_info: str
    cluster_info: str
    route_segments_data: List[dict]
    day_plan: Optional[dict]
    retry_count: int
    max_retries: int
    last_error: str
    day_plans: List[dict]
    day_food_info: str
    food_preference: str
    day_hotels_info: str
    day_hotel_location: Optional[dict]
    day_cluster: List[dict]

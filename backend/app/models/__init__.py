"""数据模型模块"""

from .schemas import (
    TripRequest,
    TripPlan,
    TripPlanResponse,
    DayPlan,
    Attraction,
    Meal,
    Hotel,
    WeatherInfo,
    Location,
    RouteSegment,
    Budget,
    CompanionInfo,
    POISearchRequest,
    POISearchResponse,
    POIInfo as POIDetail,
    GeoRequest,
    GeoResponse,
    RouteRequest,
    RouteResponse,
    WeatherResponse,
    ErrorResponse,
)

from .state import TripPlannerState, DiscoveryState, DayPlanLocalState

__all__ = [
    # Schemas - Pydantic models for API
    "TripRequest",
    "TripPlan",
    "TripPlanResponse",
    "DayPlan",
    "Attraction",
    "Meal",
    "Hotel",
    "WeatherInfo",
    "Location",
    "RouteSegment",
    "Budget",
    "CompanionInfo",
    "POISearchRequest",
    "POISearchResponse",
    "POIDetail",
    "GeoRequest",
    "GeoResponse",
    "RouteRequest",
    "RouteResponse",
    "WeatherResponse",
    "ErrorResponse",
    # Canonical graph states (API payloads remain Pydantic schemas).
    "TripPlannerState",
    "DiscoveryState",
    "DayPlanLocalState",
]

from typing import Dict, Any
from datetime import datetime

from langchain_core.messages import SystemMessage

from ..state import TripPlannerState
from ....services.preferences_service import (
    load_preferences,
    save_preferences,
    merge_preferences,
    format_preference_hint,
)
from ....models.schemas import UserPreference


async def load_user_preferences_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📋 执行节点: load_user_preferences_node")
    user_id = state.get("user_id", "default")

    preferences = await load_preferences(user_id)

    if preferences:
        print(f"  ✅ 已加载用户偏好: 酒店={preferences.preferred_hotel_types}, "
              f"美食={preferences.preferred_cuisines}, "
              f"历史出行{preferences.total_trips}次")
        preference_hint = format_preference_hint(preferences)
        return {
            "messages": [SystemMessage(content=preference_hint)],
            "user_preferences": preferences,
        }

    print("  [INFO]️ 无历史偏好数据，将使用默认策略")
    return {"user_preferences": None}


async def extract_preferences_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📊 执行节点: extract_preferences_node")
    trip_plan = state.get("trip_plan")
    if not trip_plan:
        return {"extracted_preferences": None}

    preferences: Dict[str, Any] = {}

    hotel_types = set()
    for day in trip_plan.days:
        if day.hotel and day.hotel.type:
            hotel_types.add(day.hotel.type)
    if hotel_types:
        preferences["preferred_hotel_types"] = list(hotel_types)

    cuisines = set()
    for day in trip_plan.days:
        for meal in day.meals:
            if meal.cuisine:
                cuisines.add(meal.cuisine)
    if cuisines:
        preferences["preferred_cuisines"] = list(cuisines)

    categories = set()
    for day in trip_plan.days:
        for attr in day.attractions:
            if attr.category:
                categories.add(attr.category)
    if categories:
        preferences["preferred_attraction_categories"] = list(categories)

    meal_costs = []
    for day in trip_plan.days:
        for meal in day.meals:
            if meal.estimated_cost:
                meal_costs.append(meal.estimated_cost)
    if meal_costs:
        preferences["preferred_meal_price_range"] = [min(meal_costs), max(meal_costs)]

    hotel_costs = []
    for day in trip_plan.days:
        if day.hotel and day.hotel.estimated_cost:
            hotel_costs.append(day.hotel.estimated_cost)
    if hotel_costs:
        preferences["preferred_hotel_price_range"] = [min(hotel_costs), max(hotel_costs)]

    attractions_per_day = [len(day.attractions) for day in trip_plan.days]
    if attractions_per_day:
        preferences["preferred_attractions_per_day"] = round(
            sum(attractions_per_day) / len(attractions_per_day)
        )

    if preferences:
        print(f"  ✅ 提取到偏好: {list(preferences.keys())}")
    else:
        print("  [INFO]️ 未提取到有效偏好")

    return {"extracted_preferences": preferences if preferences else None}


async def save_preferences_node(state: TripPlannerState) -> Dict[str, Any]:
    print("💾 执行节点: save_preferences_node")
    extracted = state.get("extracted_preferences")
    if not extracted:
        print("  [INFO]️ 无偏好数据需要保存")
        return {}

    user_id = state.get("user_id", "default")
    existing = await load_preferences(user_id)

    if existing:
        merged = merge_preferences(existing, extracted)
    else:
        merged = UserPreference(user_id=user_id, **extracted)

    request = state.get("request")
    merged.total_trips += 1
    if request and request.city not in merged.cities_visited:
        merged.cities_visited.append(request.city)
    merged.last_updated = datetime.utcnow().isoformat()

    await save_preferences(user_id, merged, source="inferred", confidence=0.6)
    print(f"  ✅ 已保存用户偏好 (累计{merged.total_trips}次出行)")

    return {}

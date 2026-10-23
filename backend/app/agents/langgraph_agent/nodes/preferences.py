"""Legacy graph observation nodes; historical data is never injected into planning."""
from typing import Dict, Any

from ..state import TripPlannerState
from ....database import async_session
from ....services.preferences_service import apply_extracted_preferences


async def extract_preferences_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📊 执行节点: extract_preferences_node（历史行程观察，不参与下次规划）")
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

    request = state.get("request")
    async with async_session() as session:
        await apply_extracted_preferences(
            session, state.get("user_id", "default"), extracted,
            request.city if request else "",
        )
        await session.commit()
    return {}

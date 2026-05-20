"""景点发现阶段的专用节点 — 用于 Discovery Graph"""

from typing import Any, Dict

from ..state import DiscoveryState
from .search import _preferences_to_categories
from ....services.attractions_cache_service import CachedAttraction, get_attractions_cache_service


def _cached_attraction_to_discovery_item(attraction: CachedAttraction) -> dict[str, Any]:
    location = None
    if attraction.longitude is not None and attraction.latitude is not None:
        location = {
            "longitude": attraction.longitude,
            "latitude": attraction.latitude,
        }

    return {
        "name": attraction.name,
        "description": attraction.description or attraction.category or attraction.address or "高德推荐景点",
        "category": attraction.category or "其他",
        "address": attraction.address or "",
        "rating": attraction.rating,
        "ticket_price": attraction.ticket_price,
        "image_url": attraction.image_url,
        "location": location,
        "poi_id": attraction.poi_id,
    }


async def search_attractions_discovery_node(state: DiscoveryState) -> Dict[str, Any]:
    """从共享景点缓存获取大量景点，供用户在发现页选择。"""
    print("🔍 执行节点: search_attractions_discovery_node (发现模式)")
    request = state["request"]
    service = get_attractions_cache_service()
    categories = _preferences_to_categories(request.preferences or [])

    try:
        attractions = await service.get_attractions(
            city=request.city,
            min_count=40,
            categories=categories,
        )
        max_count = min(40, max(20, request.travel_days * 6))
        discovered = [_cached_attraction_to_discovery_item(poi) for poi in attractions[:max_count]]
        with_location = sum(1 for item in discovered if item.get("location"))
        print(f"🔍 发现景点: {len(discovered)} 个 ({with_location} 个有坐标)")
        return {"discovered_attractions": discovered}
    except Exception as e:
        print(f"❌ search_attractions_discovery_node 异常: {e}")
        return {
            "discovered_attractions": [],
            "errors": [f"search_attractions_discovery: 查询失败 - {str(e)[:200]}"],
        }


async def gather_discovery_node(state: DiscoveryState) -> Dict[str, Any]:
    """发现阶段的汇总节点"""
    print("🔗 执行节点: gather_discovery_node (发现阶段汇总)")
    discovered = state.get("discovered_attractions", [])
    weather = state.get("weather_info", "")
    errors = state.get("errors", [])

    with_location = sum(1 for a in discovered if a.get("location"))
    print(f"📊 发现阶段汇总: {len(discovered)} 个景点 ({with_location} 个有坐标), "
          f"天气: {'有' if weather else '无'}")

    if errors:
        print(f"🚨 发现阶段共 {len(errors)} 个错误")
        for err in errors[-5:]:
            print(f"   - {err[:200]}")

    return {}

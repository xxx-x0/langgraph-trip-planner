"""按 day_detail.timeline_order 计算路线段"""
from typing import List

from ....models.schemas import DayDetail, RouteSegment
from ..utils.route import compute_route_segments


async def compute_day_route(
    day_detail: DayDetail, city: str, transportation: str
) -> List[RouteSegment]:
    """从 timeline_order 提取 waypoints，调高德 directions 算路线段"""
    if not day_detail.timeline_order or len(day_detail.timeline_order) < 2:
        return []

    by_attr_name = {a.name: a for a in day_detail.attractions}
    by_meal_name = {m.name: m for m in day_detail.meals}
    hotel = day_detail.hotel

    waypoints = []
    for item in day_detail.timeline_order:
        kind = item.get("kind")
        ref = item.get("ref_name", "")
        loc = None
        name = ""
        if kind == "hotel" and hotel and hotel.location:
            loc = hotel.location
            name = hotel.name
        elif kind == "attraction":
            a = by_attr_name.get(ref)
            if a and a.location:
                loc = a.location
                name = a.name
        elif kind == "meal":
            m = by_meal_name.get(ref)
            if m and m.location:
                loc = m.location
                name = m.name
        else:
            continue
        if loc is None:
            continue
        wp = {"name": name, "longitude": loc.longitude, "latitude": loc.latitude}
        if waypoints and wp["longitude"] == waypoints[-1]["longitude"] and \
           wp["latitude"] == waypoints[-1]["latitude"]:
            continue
        waypoints.append(wp)

    if len(waypoints) < 2:
        return []

    try:
        segments = await compute_route_segments(waypoints, transportation, city)
    except Exception as e:
        print(f"⚠️ compute_day_route 失败: {e}")
        return []
    return segments

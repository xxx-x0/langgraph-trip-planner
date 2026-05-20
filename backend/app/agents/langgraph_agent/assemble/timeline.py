"""规则装配每日时间轴

设计原则：
- 景点：默认沿用聚类已排序；用户给了 attractions_order 就按用户的来（忽略不存在的名字）
- 餐饮：用户给了完全用用户的；否则默认嵌一个 main top1 在景点中点之后
- timeline_order：[{kind, ref_name}]，hotel 在头尾，meal 按 insert_after 嵌入
"""
from typing import Dict, Any, List, Optional

from ....models.schemas import (
    Attraction, Meal, Location, DayDetail, DraftDayContext,
    DiningCategory, DiningCandidate,
)


def _candidate_to_meal(c: DiningCandidate) -> Meal:
    """DiningCandidate → Meal（兼容老 type 字段）"""
    type_map = {
        DiningCategory.MAIN: "lunch",          # 默认正餐当作午餐
        DiningCategory.SNACK: "snack",
        DiningCategory.DESSERT: "dessert",
        DiningCategory.CAFE: "cafe",
        DiningCategory.LATE_NIGHT: "late_night",
    }
    return Meal(
        type=type_map.get(c.category, c.category.value),
        category=c.category,
        name=c.name,
        address=c.address,
        location=c.location,
        cuisine=c.cuisine,
        rating=c.rating,
        avg_cost=c.avg_cost,
        distance=c.distance,
        open_hours=c.open_hours,
        tel=c.tel,
        poi_id=c.poi_id,
        source=c.source,
        estimated_cost=c.avg_cost or _default_cost(c.category),
    )


def _default_cost(category: DiningCategory) -> int:
    return {
        DiningCategory.MAIN: 80,
        DiningCategory.SNACK: 30,
        DiningCategory.DESSERT: 40,
        DiningCategory.CAFE: 35,
        DiningCategory.LATE_NIGHT: 60,
    }.get(category, 50)


def _meal_from_override_dict(d: Dict[str, Any]) -> tuple[Meal, str]:
    """把前端传的 meal dict 解析成 (Meal, insert_after)；insert_after 默认 ''"""
    cat_value = d.get("category") or d.get("type") or "main"
    try:
        category = DiningCategory(cat_value)
    except ValueError:
        category = DiningCategory.MAIN

    loc_dict = d.get("location")
    location = None
    if isinstance(loc_dict, dict) and loc_dict.get("longitude"):
        location = Location(
            longitude=float(loc_dict["longitude"]),
            latitude=float(loc_dict["latitude"]),
        )

    avg_cost = d.get("avg_cost")
    meal = Meal(
        type=d.get("type") or category.value,
        category=category,
        name=d.get("name", ""),
        address=d.get("address"),
        location=location,
        cuisine=d.get("cuisine"),
        rating=d.get("rating"),
        avg_cost=avg_cost,
        distance=d.get("distance"),
        open_hours=d.get("open_hours"),
        tel=d.get("tel"),
        poi_id=d.get("poi_id"),
        source=d.get("source") or "user_custom",
        estimated_cost=avg_cost or _default_cost(category),
    )
    insert_after = d.get("insert_after") or ""
    return meal, insert_after


def _apply_attraction_order(
    attractions: List[Attraction], order_names: Optional[List[str]]
) -> List[Attraction]:
    if not order_names:
        return list(attractions)
    by_name = {a.name: a for a in attractions}
    ordered: List[Attraction] = []
    used: set[str] = set()
    for name in order_names:
        if name in by_name and name not in used:
            ordered.append(by_name[name])
            used.add(name)
    # 用户没列到的景点保留在末尾（避免悄悄丢失）
    for a in attractions:
        if a.name not in used:
            ordered.append(a)
    return ordered


def _default_main_meal(ctx: DraftDayContext, attractions: List[Attraction]) -> tuple[Optional[Meal], str]:
    if not attractions or not ctx.dining_pool.main:
        return None, ""
    top1 = ctx.dining_pool.main[0]
    meal = _candidate_to_meal(top1)
    mid_idx = max(len(attractions) // 2 - 1, 0)
    return meal, attractions[mid_idx].name


def _build_timeline_order(
    attractions: List[Attraction],
    meals_with_insert: List[tuple[Meal, str]],
    hotel,
) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    if hotel is not None:
        timeline.append({"kind": "hotel", "ref_name": hotel.name, "phase": "start"})

    pending = list(meals_with_insert)
    # hotel_start 上挂的餐：在 hotel 之后立即插入
    remaining = []
    for meal, ia in pending:
        if ia == "hotel_start":
            timeline.append({"kind": "meal", "ref_name": meal.name})
        else:
            remaining.append((meal, ia))
    pending = remaining

    for attr in attractions:
        timeline.append({"kind": "attraction", "ref_name": attr.name})
        remaining = []
        for meal, ia in pending:
            if ia == attr.name:
                timeline.append({"kind": "meal", "ref_name": meal.name})
            else:
                remaining.append((meal, ia))
        pending = remaining

    # 剩余（insert_after 是 hotel_end 或匹配不上的）放尾部 hotel 之前
    for meal, _ia in pending:
        timeline.append({"kind": "meal", "ref_name": meal.name})

    if hotel is not None:
        timeline.append({"kind": "hotel", "ref_name": hotel.name, "phase": "end"})

    return timeline


def rule_assemble_day_timeline(
    ctx: DraftDayContext,
    overrides: Optional[Dict[str, Any]] = None,
) -> DayDetail:
    overrides = overrides or {}

    attractions = _apply_attraction_order(
        ctx.attractions, overrides.get("attractions_order")
    )

    if "meals" in overrides:
        meals_with_insert = [
            _meal_from_override_dict(d) for d in (overrides["meals"] or [])
        ]
        meals = [m for m, _ in meals_with_insert]
    else:
        default_meal, default_after = _default_main_meal(ctx, attractions)
        if default_meal is not None:
            meals_with_insert = [(default_meal, default_after)]
            meals = [default_meal]
        else:
            meals_with_insert = []
            meals = []

    timeline = _build_timeline_order(attractions, meals_with_insert, ctx.hotel)

    return DayDetail(
        day_index=ctx.day_index,
        date=ctx.date,
        attractions=attractions,
        meals=meals,
        hotel=ctx.hotel,
        timeline_order=timeline,
        is_assembled=True,
    )

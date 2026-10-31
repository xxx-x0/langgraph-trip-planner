"""规则装配每日时间轴

设计原则：
- 景点：默认沿用聚类已排序；用户给了 attractions_order 就按用户的来（忽略不存在的名字）
- 餐饮：用户给了完全用用户的；否则默认嵌一个 main top1 在景点中点之后
- timeline_order：[{kind, ref_name}]，hotel 在头尾，meal 按 insert_after 嵌入
"""
from typing import Dict, Any, List, Optional
from .schedule import estimated_lunch_anchor, opening_windows, clock, clock_minutes

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
        recommendation=c.recommendation,
        estimated_cost=c.avg_cost if c.avg_cost is not None else _default_cost(c.category),
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
        description=d.get("description"),
        location=location,
        cuisine=d.get("cuisine"),
        rating=d.get("rating"),
        avg_cost=avg_cost,
        distance=d.get("distance"),
        open_hours=d.get("open_hours"),
        tel=d.get("tel"),
        schedule_mode=d.get("schedule_mode") or "manual",
        preferred_slot=d.get("preferred_slot"),
        poi_id=d.get("poi_id"),
        source=d.get("source", "user_custom"),
        recommendation=d.get("recommendation") or {},
        estimated_cost=(avg_cost if avg_cost is not None else d.get("estimated_cost", _default_cost(category))),
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


def _unique_names(names: Optional[List[str]]) -> List[str]:
    if not names:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for name in names:
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _apply_removed_attractions(
    attractions: List[Attraction], removed_names: Optional[List[str]]
) -> List[Attraction]:
    removed = set(_unique_names(removed_names))
    if not removed:
        return list(attractions)
    return [a for a in attractions if a.name not in removed]



def _default_meals(ctx: DraftDayContext, attractions: List[Attraction]):
    if not attractions or not ctx.dining_pool.main:
        return []
    from ....services.recommendations import explain_dining, dining_for_slot
    explain_dining(ctx.dining_pool.main, attractions, ctx.trip_intent, ctx.day_start_time, hotel=ctx.hotel)
    result = []
    used = set()
    for slot, start, end in [("lunch", 690, 870), ("dinner", 1050, 1230)]:
        if ctx.travel_window.get('unavailable') or max(start,ctx.travel_window.get('start_minutes',0)) + 60 > min(end+60,ctx.travel_window.get('end_minutes',1440)):
            continue
        candidates = [c for c in ctx.dining_pool.main if c.name not in used and not any(w in (c.name+' '+(c.open_hours or '')) for w in ('暂停营业','永久关闭','已歇业')) and
                      (not opening_windows(c.open_hours) or any(
                          max(a, start) + 60 <= min(b, end + 60)
                          for a, b in opening_windows(c.open_hours)))]
        if not candidates:
            continue
        meal = _candidate_to_meal(dining_for_slot(candidates, slot, ctx.trip_intent)[0])
        meal.type = slot
        meal.schedule_mode = "auto"
        meal.preferred_slot = slot
        anchor = estimated_lunch_anchor(attractions, ctx.day_start_time) if slot == "lunch" else attractions[-1].name
        result.append((meal, anchor))
        used.add(meal.name)
    return result


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
    removed_attraction_names = _unique_names(overrides.get("removed_attraction_names"))
    locked_attraction_names = _unique_names(overrides.get("locked_attraction_names"))

    available_attractions = _apply_removed_attractions(
        ctx.attractions, removed_attraction_names
    )
    attractions = _apply_attraction_order(
        available_attractions, overrides.get("attractions_order")
    )
    present_names = {a.name for a in attractions}
    locked_attraction_names = [
        name for name in locked_attraction_names if name in present_names
    ]

    if "meals" in overrides:
        meals_with_insert = [
            _meal_from_override_dict(d) for d in (overrides["meals"] or [])
        ]
        start = overrides.get("day_start_time") or ctx.day_start_time
        meals_with_insert = [
            (meal, ("hotel_start" if (meal.preferred_slot or meal.type) == "breakfast" else
              estimated_lunch_anchor(attractions, start) if (meal.preferred_slot or meal.type) == "lunch"
              else attractions[-1].name if attractions else "hotel_start")
             if meal.schedule_mode == "auto" else anchor)
            for meal, anchor in meals_with_insert
        ]
        meals = [m for m, _ in meals_with_insert]
    else:
        meals_with_insert = _default_meals(ctx, attractions)
        meals = [m for m, _ in meals_with_insert]

    hotel = None if ctx.travel_window.get("unavailable") else ctx.hotel
    timeline = _build_timeline_order(attractions, meals_with_insert, hotel)

    return DayDetail(
        trip_intent=ctx.trip_intent,
        travel_window=ctx.travel_window, rest_periods=ctx.rest_periods,
        time_constraints=overrides.get("time_constraints"),
        day_index=ctx.day_index,
        date=ctx.date,
        attractions=attractions,
        meals=meals,
        hotel=hotel,
        day_start_time=overrides.get("day_start_time") or clock(clock_minutes(ctx.day_start_time) if ctx.travel_window.get('unavailable') else max(clock_minutes(ctx.day_start_time),ctx.travel_window.get("start_minutes",0))),
        timeline_order=timeline,
        locked_attraction_names=locked_attraction_names,
        removed_attraction_names=removed_attraction_names,
        is_assembled=True,
        overnight_stay=ctx.overnight_stay,
        companion_count=ctx.companion_count,
        meal_adjustments=overrides.get("meal_adjustments") or [],
    )

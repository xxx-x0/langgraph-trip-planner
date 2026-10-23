"""Known estimated costs; missing prices never mean a free visit."""
import re
import math
from ....models.schemas import Budget, DayDetail
from ....services.hotel_quotes import hotel_cost_for_date

_DAILY_TRANSPORT_DEFAULT = 50


def parse_ticket_price(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if math.isfinite(value) and value >= 0 else None
    text = str(value).strip()
    if text in {"免费", "免票", "0元", "0"}:
        return 0
    if text.startswith("-"):
        return None
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def compute_day_budget(day_detail: DayDetail) -> Budget:
    count = day_detail.companion_count
    unknown = [f"{day_detail.date} {a.name}门票" for a in day_detail.attractions if a.ticket_price is None]
    unknown.extend(f"{day_detail.date} {warning}" for warning in day_detail.meal_warnings if warning.startswith(("早餐未安排", "午餐未安排", "晚餐未安排")))
    total_attractions = sum(a.ticket_price or 0 for a in day_detail.attractions) * count
    total_meals = sum(m.estimated_cost for m in day_detail.meals) * count
    total_hotels = 0
    if day_detail.hotel and day_detail.overnight_stay:
        total_hotels, hotel_missing = hotel_cost_for_date(day_detail.hotel, day_detail.date)
        unknown.extend(f"{day_detail.date} {item}" for item in hotel_missing)
    elif day_detail.overnight_stay:
        unknown.append(f"{day_detail.date} 住宿未安排")
    has_content = bool(day_detail.attractions or day_detail.meals or day_detail.hotel)
    transport = _DAILY_TRANSPORT_DEFAULT * count if has_content else 0
    if has_content:
        unknown.append('市内交通仅按每人每天50元估算' if 'intercity_cost' in day_detail.travel_window else '往返大交通未纳入；市内交通仅按每人每天50元估算')
    intercity = day_detail.travel_window.get('intercity_cost',0)
    unknown.extend(day_detail.travel_window.get('unknown_cost_items',[]))
    return Budget(
        total_attractions=total_attractions, total_hotels=total_hotels,
        total_meals=total_meals, total_transportation=transport+intercity, total_intercity=intercity,
        total=round(total_attractions + total_hotels + total_meals + transport + intercity, 2),
        unknown_cost_items=unknown, is_complete=not unknown,
    )


def combine_budgets(budgets: list[Budget], limit: int | None = None) -> Budget:
    unknown = list(dict.fromkeys(item for budget in budgets for item in budget.unknown_cost_items))
    total = round(sum(b.total for b in budgets), 2)
    complete = all(b.is_complete for b in budgets)
    return Budget(
        **{field: round(sum(getattr(b, field) for b in budgets), 2) for field in
           ["total_attractions", "total_hotels", "total_meals", "total_transportation", "total_intercity"]},
        total=total, budget_limit=limit, unknown_cost_items=unknown, is_complete=complete,
        is_within_budget=(False if limit is not None and total > limit else
                          total <= limit if complete and limit is not None else None),
    )

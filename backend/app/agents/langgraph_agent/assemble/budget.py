"""单日预算计算"""
from ....models.schemas import Budget, DayDetail


_DAILY_TRANSPORT_DEFAULT = 50  # 元/天，与旧 reduce_assemble_node 保持一致


def compute_day_budget(day_detail: DayDetail) -> Budget:
    total_attractions = sum(a.ticket_price for a in day_detail.attractions)
    total_meals = sum(m.estimated_cost for m in day_detail.meals)
    total_hotels = day_detail.hotel.estimated_cost if (
        day_detail.hotel and day_detail.hotel.estimated_cost
    ) else 0
    # 空日（无任何景点/餐饮/酒店）不计交通费；否则按日固定默认值
    has_content = bool(day_detail.attractions) or bool(day_detail.meals) or bool(day_detail.hotel)
    total_transportation = _DAILY_TRANSPORT_DEFAULT if has_content else 0
    return Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotels,
        total_meals=total_meals,
        total_transportation=total_transportation,
        total=total_attractions + total_meals + total_hotels + total_transportation,
    )

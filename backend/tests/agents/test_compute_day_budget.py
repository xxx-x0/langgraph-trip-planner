from app.agents.langgraph_agent.assemble.budget import compute_day_budget
from app.models.schemas import (
    Attraction, Hotel, Meal, DayDetail, DiningCategory, Location,
)


def test_empty_day_has_zero_budget():
    detail = DayDetail(day_index=0, date="2026-06-01")
    b = compute_day_budget(detail)
    assert b.total == 0
    assert b.total_attractions == 0
    assert b.total_meals == 0


def test_attractions_meals_hotel_summed():
    detail = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[
            Attraction(name="A", address="...", visit_duration=120,
                       description="", ticket_price=60),
            Attraction(name="B", address="...", visit_duration=120,
                       description="", ticket_price=40),
        ],
        hotel=Hotel(name="H", estimated_cost=300),
        meals=[
            Meal(type="main", category=DiningCategory.MAIN, name="M",
                 estimated_cost=80),
            Meal(type="snack", category=DiningCategory.SNACK, name="S",
                 estimated_cost=20),
        ],
    )
    b = compute_day_budget(detail)
    assert b.total_attractions == 100
    assert b.total_meals == 100
    assert b.total_hotels == 300
    assert b.total_transportation == 50  # 默认 50
    assert b.total == 550

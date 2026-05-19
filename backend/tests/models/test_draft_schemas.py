from app.models.schemas import (
    DiningCategory, DiningCandidate, DiningPoolDay,
    DayDetail, TripDraftPayload, DayEditRequest, Meal,
    Location, MacroPlan, DaySkeleton, TripRequest, Attraction,
)


def test_dining_category_enum_values():
    assert DiningCategory.MAIN == "main"
    assert DiningCategory.LATE_NIGHT == "late_night"
    assert {c.value for c in DiningCategory} == {
        "main", "snack", "dessert", "cafe", "late_night"
    }


def test_dining_pool_day_default_empty():
    pool = DiningPoolDay()
    assert pool.main == []
    assert pool.late_night == []


def test_dining_candidate_requires_category():
    cand = DiningCandidate(name="某餐厅", category=DiningCategory.MAIN)
    assert cand.category == DiningCategory.MAIN
    assert cand.source == "nearby"


def test_day_detail_defaults():
    dd = DayDetail(day_index=0, date="2026-06-01")
    assert dd.is_assembled is False
    assert dd.meals == []
    assert dd.day_budget is None


def test_meal_category_backward_compat():
    m1 = Meal(type="breakfast", name="某餐厅")
    assert m1.category is None
    m2 = Meal(type="main", name="某餐厅", category=DiningCategory.MAIN)
    assert m2.category == DiningCategory.MAIN


def test_day_edit_request_field_omission_semantics():
    """不传 meals 与传空数组是两种意图"""
    r1 = DayEditRequest()
    assert r1.meals is None
    r2 = DayEditRequest(meals=[])
    assert r2.meals == []

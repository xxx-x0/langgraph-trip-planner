from unittest.mock import AsyncMock

import pytest

from app.services.aigohotel_mcp_service import AIGoHotelService


@pytest.mark.asyncio
async def test_search_hotels_uses_current_nested_search_arguments():
    service = AIGoHotelService()
    service._call_tool = AsyncMock(return_value={"hotelInformationList": []})

    await service.search_hotels(
        place="重庆",
        origin_query="住解放碑附近",
        check_in="2026-06-01",
        stay_nights=2,
        adult_count=2,
        star_ratings=[4.0, 5.0],
        distance_in_meter=3000,
        size=8,
    )

    tool_name, arguments = service._call_tool.await_args.args[:2]
    assert tool_name == "SearchHotels"
    assert arguments["checkInParam"] == {
        "checkInDate": "2026-06-01",
        "stayNights": 2,
        "adultCount": 2,
    }
    assert arguments["filterOptions"] == {
        "starRatings": [4.0, 5.0],
        "distanceInMeter": 3000,
    }
    assert arguments["size"] == 8
    assert "checkIn" not in arguments


@pytest.mark.asyncio
async def test_get_hotel_detail_accepts_dates_and_occupancy():
    service = AIGoHotelService()
    service._call_tool = AsyncMock(return_value={"hotelId": 572174})

    await service.get_hotel_detail(
        572174,
        check_in="2026-06-01",
        stay_nights=2,
        adult_count=2,
    )

    tool_name, arguments = service._call_tool.await_args.args[:2]
    assert tool_name == "GetHotelDetail"
    assert arguments == {
        "hotelId": 572174,
        "dateParam": {
            "checkInDate": "2026-06-01",
            "stayNights": 2,
        },
        "occupancyParam": {"adultCount": 2},
    }

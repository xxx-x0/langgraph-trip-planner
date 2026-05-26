from app.agents.langgraph_agent.nodes.search import _parse_aigohotel_hotels


def test_parse_aigohotel_hotels_strips_description_markup():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "海景酒店",
            "description": "<p><b>酒店简介</b><br/>步行可到海边</p>",
        }],
    })

    assert hotels[0]["description"] == "酒店简介 步行可到海边"


def test_parse_aigohotel_hotels_keeps_numeric_price():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "海景酒店",
            "totalPrice": "688.5",
        }],
    })

    assert hotels[0]["price"] == 688.5


def test_parse_aigohotel_hotels_reads_current_rate_and_booking_fields():
    hotels = _parse_aigohotel_hotels({
        "hotelInformationList": [{
            "hotelId": 572174,
            "name": "麗枫酒店",
            "bookingUrl": "https://rollinggo.example/hotel",
            "price": {
                "hasPrice": True,
                "lowestPrice": 350,
                "currency": "CNY",
            },
        }],
    })

    assert hotels[0]["hotel_id"] == 572174
    assert hotels[0]["price"] == 350
    assert hotels[0]["currency"] == "CNY"
    assert hotels[0]["detail_url"] == "https://rollinggo.example/hotel"


def test_parse_aigohotel_hotels_fills_estimated_cost_from_price():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "测试酒店",
            "totalPrice": "688.5",
        }],
    })
    assert hotels[0]["estimated_cost"] == 688


def test_parse_aigohotel_hotels_fills_estimated_cost_from_price_obj():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "测试酒店2",
            "price": {"hasPrice": True, "lowestPrice": 350, "currency": "CNY"},
        }],
    })
    assert hotels[0]["estimated_cost"] == 350


def test_parse_aigohotel_hotels_estimated_cost_falls_back_to_star_rating():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "无价酒店",
            "starRating": 4,
        }],
    })
    # 4 星 × 200 = 800
    assert hotels[0]["estimated_cost"] == 800


def test_parse_aigohotel_hotels_estimated_cost_default_when_no_signals():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "纯净酒店",
        }],
    })
    # 无 price 也无 star → 默认 500
    assert hotels[0]["estimated_cost"] == 500

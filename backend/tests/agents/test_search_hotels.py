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

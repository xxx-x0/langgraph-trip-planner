from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.db_models import AttractionCache
from app.services.attractions_cache_service import (
    AttractionsCacheService,
    _extract_location,
    _is_valid_coordinate,
    _normalize_category,
    _normalize_poi,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def service_with_rows(session_factory):
    async with session_factory() as session:
        session.add_all([
            AttractionCache(
                city="北京",
                name="故宫博物院",
                address="北京市东城区景山前街4号",
                longitude=116.397128,
                latitude=39.916527,
                category="历史文化",
                amap_type="风景名胜;风景名胜",
                poi_id="B000A8UIN8",
            ),
            AttractionCache(
                city="北京",
                name="天坛公园",
                address="北京市东城区天坛路甲1号",
                longitude=116.410829,
                latitude=39.881913,
                category="历史文化",
                amap_type="风景名胜;公园广场",
                poi_id="B000A83M61",
            ),
        ])
        await session.commit()
    return AttractionsCacheService(session_factory=session_factory)


@pytest.mark.parametrize(
    ("amap_type", "expected"),
    [
        ("风景名胜;风景名胜;公园广场", "自然风光"),
        ("科教文化服务;博物馆", "历史文化"),
        ("购物服务;购物相关场所", "购物"),
        ("餐饮服务;中餐厅", "美食街区"),
        ("地名地址信息", "其他"),
    ],
)
def test_normalize_category(amap_type, expected):
    assert _normalize_category(amap_type) == expected


def test_extract_location_from_string():
    assert _extract_location("116.397128,39.916527") == (116.397128, 39.916527)


def test_extract_location_from_dict():
    assert _extract_location({"longitude": 116.397128, "latitude": 39.916527}) == (116.397128, 39.916527)


def test_invalid_coordinate_outside_china_bounds():
    assert _is_valid_coordinate(151.2, -33.8) is False


def test_normalize_poi_keeps_core_fields():
    poi = {
        "id": "B000A8UIN8",
        "name": "故宫博物院",
        "address": "北京市东城区景山前街4号",
        "location": "116.397128,39.916527",
        "type": "风景名胜;风景名胜;风景名胜",
        "biz_ext": {"rating": "4.8", "cost": "60"},
        "photos": [{"url": "https://example.com/gugong.jpg"}],
    }

    normalized = _normalize_poi("北京", poi)

    assert normalized["city"] == "北京"
    assert normalized["name"] == "故宫博物院"
    assert normalized["poi_id"] == "B000A8UIN8"
    assert normalized["longitude"] == 116.397128
    assert normalized["latitude"] == 39.916527
    assert normalized["category"] == "自然风光"
    assert normalized["rating"] == 4.8
    assert normalized["ticket_price"] == "60"
    assert normalized["image_url"] == "https://example.com/gugong.jpg"


@pytest.mark.asyncio
async def test_get_attractions_returns_cache_hit(service_with_rows):
    result = await service_with_rows.get_attractions("北京", min_count=2)
    assert [p.name for p in result] == ["故宫博物院", "天坛公园"]


@pytest.mark.asyncio
async def test_category_filter_falls_back_to_all_when_too_few(service_with_rows):
    result = await service_with_rows.get_attractions("北京", min_count=2, categories=["购物"])
    assert [p.name for p in result] == ["故宫博物院", "天坛公园"]


@pytest.mark.asyncio
async def test_get_attractions_fetches_when_cache_empty(session_factory):
    service = AttractionsCacheService(session_factory=session_factory)
    mock_tool = AsyncMock()
    mock_tool.ainvoke.return_value = {
        "pois": [
            {
                "id": "B000A8UIN8",
                "name": "故宫博物院",
                "address": "北京市东城区景山前街4号",
                "location": "116.397128,39.916527",
                "type": "风景名胜",
            }
        ]
    }
    mock_amap = MagicMock()
    mock_amap.get_tool = AsyncMock(return_value=mock_tool)

    with patch("app.services.attractions_cache_service.get_langchain_amap_service", return_value=mock_amap):
        result = await service.get_attractions("北京", min_count=1)

    assert [p.name for p in result] == ["故宫博物院"]


@pytest.mark.asyncio
async def test_refresh_city_replaces_rows(session_factory):
    service = AttractionsCacheService(session_factory=session_factory)
    async with session_factory() as session:
        session.add(AttractionCache(city="北京", name="旧景点", category="其他"))
        await session.commit()

    mock_tool = AsyncMock()
    mock_tool.ainvoke.return_value = {
        "pois": [
            {
                "id": "B000A83M61",
                "name": "天坛公园",
                "location": "116.410829,39.881913",
                "type": "风景名胜;公园广场",
            }
        ]
    }
    mock_amap = MagicMock()
    mock_amap.get_tool = AsyncMock(return_value=mock_tool)

    with patch("app.services.attractions_cache_service.get_langchain_amap_service", return_value=mock_amap):
        refreshed = await service.refresh_city("北京")

    assert refreshed == 1
    result = await service.get_attractions("北京", min_count=1)
    assert [p.name for p in result] == ["天坛公园"]

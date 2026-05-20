from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _mock_service():
    service = MagicMock()
    service.refresh_city = AsyncMock(return_value=12)
    service.clear_city = AsyncMock(return_value=8)
    service.get_stats = AsyncMock(return_value={"cities": 1, "attractions": 12})
    return service


def test_refresh_city_rejects_empty_city():
    response = client.post("/api/admin/attractions/refresh", params={"city": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "city is required"


def test_refresh_city_success():
    service = _mock_service()
    with patch("app.api.routes.admin.get_attractions_cache_service", return_value=service):
        response = client.post("/api/admin/attractions/refresh", params={"city": "北京"})

    assert response.status_code == 200
    assert response.json() == {"city": "北京", "refreshed": 12}
    service.refresh_city.assert_awaited_once_with("北京")


def test_clear_city_success():
    service = _mock_service()
    with patch("app.api.routes.admin.get_attractions_cache_service", return_value=service):
        response = client.post("/api/admin/attractions/clear", params={"city": "北京"})

    assert response.status_code == 200
    assert response.json() == {"city": "北京", "cleared": 8}
    service.clear_city.assert_awaited_once_with("北京")


def test_stats_success():
    service = _mock_service()
    with patch("app.api.routes.admin.get_attractions_cache_service", return_value=service):
        response = client.get("/api/admin/attractions/stats")

    assert response.status_code == 200
    assert response.json() == {"cities": 1, "attractions": 12}
    service.get_stats.assert_awaited_once()

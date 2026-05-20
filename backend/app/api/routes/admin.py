"""Admin endpoints for local cache maintenance."""

from fastapi import APIRouter, HTTPException

from ...services.attractions_cache_service import get_attractions_cache_service

router = APIRouter(prefix="/admin/attractions", tags=["admin"])


@router.post("/refresh")
async def refresh_city(city: str):
    if not city.strip():
        raise HTTPException(status_code=400, detail="city is required")
    count = await get_attractions_cache_service().refresh_city(city.strip())
    return {"city": city.strip(), "refreshed": count}


@router.post("/clear")
async def clear_city(city: str):
    if not city.strip():
        raise HTTPException(status_code=400, detail="city is required")
    count = await get_attractions_cache_service().clear_city(city.strip())
    return {"city": city.strip(), "cleared": count}


@router.get("/stats")
async def stats():
    return await get_attractions_cache_service().get_stats()

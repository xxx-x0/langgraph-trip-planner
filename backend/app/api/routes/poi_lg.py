"""POI相关API路由 (LangGraph版本)

重构说明:
- 原始路由(poi.py)使用 amap_service (旧MCP封装) 和 unsplash_service
- 本路由使用 langchain-mcp-adapters 官方适配器
- Unsplash图片服务保持不变(与MCP无关)
- 响应模型统一使用 schemas.py 中定义的类型
- 所有服务调用均为异步
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ...models.schemas import (
    POISearchResponse,
    POIDetailResponse
)
from ...services.langchain_amap_tools import get_langchain_amap_service
from ...services.unsplash_service import get_unsplash_service

router = APIRouter(prefix="/poi", tags=["POI"])


@router.get(
    "/detail/{poi_id}",
    response_model=POIDetailResponse,
    summary="获取POI详情",
    description="根据POI ID获取详细信息，使用LangChain MCP适配器"
)
async def get_poi_detail(poi_id: str):
    try:
        service = get_langchain_amap_service()
        result = await service.get_poi_detail(poi_id=poi_id)

        return POIDetailResponse(
            success=True,
            message="获取POI详情成功",
            data=result
        )

    except Exception as e:
        print(f"❌ 获取POI详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取POI详情失败: {str(e)}")


@router.get(
    "/search",
    response_model=POISearchResponse,
    summary="搜索POI",
    description="根据关键词搜索POI，使用LangChain MCP适配器"
)
async def search_poi(
    keywords: str = Query(..., description="搜索关键词", example="故宫"),
    city: str = Query(default="北京", description="城市名称", example="北京")
):
    try:
        service = get_langchain_amap_service()
        result = await service.search_poi(keywords=keywords, city=city)

        return POISearchResponse(
            success=True,
            message="搜索成功",
            data=result if isinstance(result, list) else []
        )

    except Exception as e:
        print(f"❌ 搜索POI失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索POI失败: {str(e)}")


@router.get(
    "/photo",
    summary="获取景点图片",
    description="根据景点名称从Unsplash获取图片"
)
async def get_attraction_photo(name: str = Query(..., description="景点名称")):
    try:
        unsplash_service = get_unsplash_service()

        photo_url = unsplash_service.get_photo_url(f"{name} China landmark")

        if not photo_url:
            photo_url = unsplash_service.get_photo_url(name)

        return {
            "success": True,
            "message": "获取图片成功",
            "data": {
                "name": name,
                "photo_url": photo_url
            }
        }

    except Exception as e:
        print(f"❌ 获取景点图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取景点图片失败: {str(e)}")

"""LangGraph兼容的地图服务API路由

重构说明:
- 原始路由(map.py)使用 amap_service (旧MCP封装)
- 本路由使用 langchain-mcp-adapters 官方适配器
- 响应模型统一使用 schemas.py 中定义的类型
- 所有服务调用均为异步
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ...models.schemas import (
    POISearchRequest,
    POISearchResponse,
    POIDetailResponse,
    RouteRequest,
    RouteResponse,
    WeatherResponse,
    GeoRequest,
    GeoResponse
)
from ...services.langchain_amap_tools import get_langchain_amap_service

router = APIRouter(prefix="/map", tags=["地图服务"])


@router.get(
    "/poi",
    response_model=POISearchResponse,
    summary="搜索POI",
    description="根据关键词搜索POI(兴趣点)，使用LangChain MCP适配器"
)
async def search_poi(
    keywords: str = Query(..., description="搜索关键词", example="故宫"),
    city: str = Query(..., description="城市", example="北京"),
    citylimit: bool = Query(True, description="是否限制在城市范围内")
):
    try:
        service = get_langchain_amap_service()
        result = await service.search_poi(keywords=keywords, city=city)

        return POISearchResponse(
            success=True,
            message="POI搜索成功",
            data=result if isinstance(result, list) else []
        )

    except Exception as e:
        print(f"❌ POI搜索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"POI搜索失败: {str(e)}")


@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="查询天气",
    description="查询指定城市的天气信息，使用LangChain MCP适配器"
)
async def get_weather(
    city: str = Query(..., description="城市名称", example="北京")
):
    try:
        service = get_langchain_amap_service()
        result = await service.get_weather(city=city)

        return WeatherResponse(
            success=True,
            message="天气查询成功",
            data=result if isinstance(result, list) else []
        )

    except Exception as e:
        print(f"❌ 天气查询失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"天气查询失败: {str(e)}")


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="路线规划",
    description="规划两点之间的路线，支持步行、驾车、公交三种方式，使用LangChain MCP适配器"
)
async def plan_route(request: RouteRequest):
    try:
        service = get_langchain_amap_service()

        if request.route_type == "transit":
            if not request.origin_city or not request.destination_city:
                raise HTTPException(
                    status_code=400,
                    detail="公交路线规划必须提供起点城市和终点城市"
                )

        result = await service.plan_route(
            origin_address=request.origin_address,
            destination_address=request.destination_address,
            origin_city=request.origin_city,
            destination_city=request.destination_city,
            route_type=request.route_type
        )

        if isinstance(result, dict) and "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return RouteResponse(
            success=True,
            message="路线规划成功",
            data=result
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 路线规划失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"路线规划失败: {str(e)}")


@router.get(
    "/poi/detail/{poi_id}",
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


@router.post(
    "/geo",
    response_model=GeoResponse,
    summary="地理编码",
    description="将地址转换为经纬度坐标，使用LangChain MCP适配器"
)
async def geocode(request: GeoRequest):
    try:
        service = get_langchain_amap_service()
        result = await service.geocode(address=request.address, city=request.city)

        return GeoResponse(
            success=True,
            message="地理编码成功",
            data=result
        )

    except Exception as e:
        print(f"❌ 地理编码失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"地理编码失败: {str(e)}")


@router.get(
    "/health",
    summary="健康检查",
    description="检查地图服务是否正常"
)
async def health_check():
    try:
        return {
            "status": "healthy",
            "service": "map-service-langgraph",
            "mcp_adapter": "langchain-mcp-adapters"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"地图服务不可用: {str(e)}")

"""LangChain 兼容的高德地图服务封装

本模块是 LangGraph 重构后的新 MCP 调用层，独立于旧的 amap_service.py。
使用 langchain-mcp-adapters 官方适配器替代 hello_agents.MCPTool，
通过 SSE 传输连接高德官方 MCP 云服务（无需本地安装 uvx/Node.js），
提供 LangChainAmapService 异步服务类，统一封装所有高德地图 MCP 工具调用。
"""

import asyncio
import json
import threading
from typing import Optional, Dict, Any, List

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import get_settings


_mcp_client: Optional[MultiServerMCPClient] = None
_mcp_tools: Optional[List[BaseTool]] = None
_mcp_async_lock: Optional[asyncio.Lock] = None


def _get_async_lock() -> asyncio.Lock:
    global _mcp_async_lock
    if _mcp_async_lock is None:
        _mcp_async_lock = asyncio.Lock()
    return _mcp_async_lock


def _build_mcp_config() -> Dict[str, Any]:
    settings = get_settings()
    if not settings.amap_api_key:
        raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
    return {
        "amap": {
            "transport": "sse",
            "url": f"https://mcp.amap.com/sse?key={settings.amap_api_key}",
            "timeout": 60,
            "sse_read_timeout": 300
        }
    }


async def _init_mcp_client() -> None:
    global _mcp_client, _mcp_tools

    if _mcp_client is not None and _mcp_tools is not None:
        return

    async_lock = _get_async_lock()
    async with async_lock:
        if _mcp_client is not None and _mcp_tools is not None:
            return

        config = _build_mcp_config()
        _mcp_client = MultiServerMCPClient(config)
        _mcp_tools = await _mcp_client.get_tools()

        print(f"✅ LangChain MCP 适配器初始化成功 (langchain-mcp-adapters)")
        print(f"   工具数量: {len(_mcp_tools)}")
        if _mcp_tools:
            print("   可用工具:")
            for t in _mcp_tools:
                print(f"     - {t.name}")
            if len(_mcp_tools) > 5:
                print(f"     ... 还有 {len(_mcp_tools) - 5} 个工具")


async def get_mcp_tools() -> List[BaseTool]:
    await _init_mcp_client()
    return _mcp_tools


async def get_mcp_tool_by_name(name: str) -> Optional[BaseTool]:
    tools = await get_mcp_tools()
    for t in tools:
        if t.name == name:
            return t
    return None


def _parse_result(result: Any) -> Any:
    if isinstance(result, (dict, list)):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return {"raw_result": result}
    return {"raw_result": str(result)}


class LangChainAmapService:
    """LangChain 兼容的高德地图服务封装类

    使用 langchain-mcp-adapters 官方适配器，提供统一的异步服务接口。
    MCP 工具自动从服务器加载，无需手动定义 @tool 函数。
    """

    async def _ensure_initialized(self) -> None:
        await _init_mcp_client()

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        await self._ensure_initialized()
        tool = await get_mcp_tool_by_name(tool_name)
        if tool is None:
            raise ValueError(f"MCP 工具不存在: {tool_name}")
        result = await tool.ainvoke(arguments)
        return result

    async def search_poi(self, keywords: str, city: str) -> Any:
        result = await self._call_tool("maps_text_search", {
            "keywords": keywords,
            "city": city,
            "citylimit": "true"
        })
        return _parse_result(result)

    async def get_weather(self, city: str) -> Any:
        result = await self._call_tool("maps_weather", {"city": city})
        return _parse_result(result)

    async def _geocode_address(self, address: str, city: Optional[str] = None) -> Optional[str]:
        arguments = {"address": address}
        if city:
            arguments["city"] = city
        result = await self._call_tool("maps_geo", arguments)
        parsed = _parse_result(result)
        if isinstance(parsed, dict):
            geocodes = parsed.get("geocodes", [])
            if geocodes:
                location = geocodes[0].get("location", "")
                if location:
                    return location
        return None

    async def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking"
    ) -> Any:
        tool_name_map = {
            "walking": "maps_direction_walking",
            "driving": "maps_direction_driving",
            "transit": "maps_direction_transit_integrated"
        }
        tool_name = tool_name_map.get(route_type)
        if not tool_name:
            return {"error": f"不支持的路线类型: {route_type}"}

        origin_coord = await self._geocode_address(origin_address, origin_city)
        dest_coord = await self._geocode_address(destination_address, destination_city)

        if not origin_coord:
            return {"error": f"无法解析起点地址: {origin_address}"}
        if not dest_coord:
            return {"error": f"无法解析终点地址: {destination_address}"}

        arguments = {
            "origin": origin_coord,
            "destination": dest_coord
        }
        if route_type == "transit":
            arguments["city"] = origin_city or destination_city or ""
            arguments["cityd"] = destination_city or origin_city or ""

        result = await self._call_tool(tool_name, arguments)
        return _parse_result(result)

    async def geocode(self, address: str, city: Optional[str] = None) -> Any:
        arguments = {"address": address}
        if city:
            arguments["city"] = city
        result = await self._call_tool("maps_geo", arguments)
        return _parse_result(result)

    async def get_poi_detail(self, poi_id: str) -> Any:
        result = await self._call_tool("maps_search_detail", {"id": poi_id})
        return _parse_result(result)

    async def get_tools(self) -> List[BaseTool]:
        await self._ensure_initialized()
        return _mcp_tools

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        return await get_mcp_tool_by_name(name)


_langchain_amap_service: Optional[LangChainAmapService] = None
_service_lock = threading.Lock()


def get_langchain_amap_service() -> LangChainAmapService:
    global _langchain_amap_service
    if _langchain_amap_service is None:
        with _service_lock:
            if _langchain_amap_service is None:
                _langchain_amap_service = LangChainAmapService()
    return _langchain_amap_service

"""AIGoHotel MCP 服务封装

通过魔搭社区接入 AIGoHotel MCP，提供酒店搜索和详情查询能力。
使用 langchain-mcp-adapters 官方适配器，streamable_http 传输方式。

工具列表:
- GetHotelSearchTags: 获取酒店搜索标签元数据
- SearchHotels (find-hotels): 多条件酒店信息搜索
- GetHotelDetail: 单个酒店房型价格及详细信息
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

_CONNECTION_ERROR_KEYWORDS = [
    "connection", "connect", "timeout", "timed out",
    "sse", "eof", "broken pipe", "reset", "refused",
    "network", "unreachable", "host", "dns",
]


class AIGoHotelConfigError(Exception):
    """AIGoHotel 配置错误"""
    pass


def _get_async_lock() -> asyncio.Lock:
    global _mcp_async_lock
    if _mcp_async_lock is None:
        _mcp_async_lock = asyncio.Lock()
    return _mcp_async_lock


def _is_connection_error(e: Exception) -> bool:
    if isinstance(e, (ConnectionError, ConnectionResetError, ConnectionAbortedError, OSError)):
        return True
    if isinstance(e, asyncio.TimeoutError):
        return True
    msg = str(e).lower()
    return any(kw in msg for kw in _CONNECTION_ERROR_KEYWORDS)


def _build_mcp_config() -> Dict[str, Any]:
    settings = get_settings()
    if not settings.aigohotel_mcp_url:
        raise AIGoHotelConfigError("AIGOHOTEL_MCP_URL 未配置")
    return {
        "aigohotel": {
            "transport": "streamable_http",
            "url": settings.aigohotel_mcp_url,
            "timeout": 60,
        }
    }


async def _reset_mcp_client() -> None:
    global _mcp_client, _mcp_tools
    async_lock = _get_async_lock()
    async with async_lock:
        if _mcp_client is not None:
            try:
                if hasattr(_mcp_client, 'close'):
                    await _mcp_client.close()
            except Exception:
                pass
        _mcp_client = None
        _mcp_tools = None
        print("🔄 AIGoHotel MCP 客户端已重置，将在下次调用时重新连接")


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

        print(f"✅ AIGoHotel MCP 适配器初始化成功")
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
        if t.name == name or t.name.lower() == name.lower():
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


class AIGoHotelService:
    """AIGoHotel MCP 服务封装类

    提供酒店搜索和详情查询的统一异步接口。
    韧性增强:
    - _call_tool 内置超时控制和断线重连
    - health_check 方法用于探测连接状态
    """

    async def _ensure_initialized(self) -> None:
        await _init_mcp_client()

    async def _call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Any:
        await self._ensure_initialized()
        tool = await get_mcp_tool_by_name(tool_name)
        if tool is None:
            raise ValueError(f"AIGoHotel MCP 工具不存在: {tool_name}")

        try:
            result = await asyncio.wait_for(
                tool.ainvoke(arguments), timeout=timeout
            )
            return result
        except Exception as e:
            if _is_connection_error(e):
                print(f"🔄 AIGoHotel MCP 连接异常 [{tool_name}]: {str(e)[:150]}")
                print("   尝试重置客户端并重新连接...")
                await _reset_mcp_client()
                try:
                    await self._ensure_initialized()
                    tool = await get_mcp_tool_by_name(tool_name)
                    if tool is None:
                        raise ValueError(
                            f"重连后 AIGoHotel MCP 工具仍不存在: {tool_name}"
                        )
                    result = await asyncio.wait_for(
                        tool.ainvoke(arguments), timeout=timeout
                    )
                    print(f"✅ AIGoHotel MCP 重连后工具调用成功 [{tool_name}]")
                    return result
                except Exception as reconnect_err:
                    print(f"❌ AIGoHotel MCP 重连后调用仍失败 [{tool_name}]: {str(reconnect_err)[:150]}")
                    raise
            raise

    async def health_check(self) -> bool:
        try:
            await self._ensure_initialized()
            return _mcp_tools is not None and len(_mcp_tools) > 0
        except Exception:
            return False

    async def search_hotels(
        self,
        place: str,
        origin_query: str = "",
        place_type: str = "城市",
        check_in: Optional[str] = None,
        stay_nights: Optional[int] = None,
        star_ratings: Optional[List[float]] = None,
        adult_count: Optional[int] = None,
        distance_in_meter: Optional[int] = None,
        size: Optional[int] = None,
        with_hotel_amenities: bool = True,
        with_room_amenities: bool = True,
    ) -> Any:
        """搜索酒店

        Args:
            place: 搜索地点（城市、景点、机场等）
            origin_query: 用户原始需求描述（如"帮我找杭州西湖附近的酒店"）
            place_type: 地点类型（城市/景点/机场/火车站/地铁站/酒店/具体地址），默认"城市"
            check_in: 入住日期 yyyy-MM-dd
            stay_nights: 住宿天数
            star_ratings: 星级范围如 [4.0, 5.0]
            adult_count: 每间房成人数量
            distance_in_meter: 以POI为中心的半径（米）
            size: 返回数量，默认10，最大20
            with_hotel_amenities: 是否包含酒店设施
            with_room_amenities: 是否包含房间设施
        """
        arguments: Dict[str, Any] = {"place": place, "placeType": place_type}
        if origin_query:
            arguments["originQuery"] = origin_query
        if check_in:
            arguments["checkIn"] = check_in
        if stay_nights is not None:
            arguments["stayNights"] = stay_nights
        if star_ratings:
            arguments["starRatings"] = star_ratings
        if adult_count is not None:
            arguments["adultCount"] = adult_count
        if distance_in_meter is not None:
            arguments["distanceInMeter"] = distance_in_meter
        if size is not None:
            arguments["size"] = size
        if with_hotel_amenities:
            arguments["withHotelAmenities"] = True
        if with_room_amenities:
            arguments["withRoomAmenities"] = True

        result = await self._call_tool("SearchHotels", arguments, timeout=45.0)
        return _parse_result(result)

    async def get_hotel_detail(self, hotel_id: str) -> Any:
        """获取酒店详情"""
        result = await self._call_tool("GetHotelDetail", {"hotelId": hotel_id}, timeout=30.0)
        return _parse_result(result)

    async def get_tools(self) -> List[BaseTool]:
        await self._ensure_initialized()
        return _mcp_tools

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        return await get_mcp_tool_by_name(name)


_aigohotel_service: Optional[AIGoHotelService] = None
_service_lock = threading.Lock()


def get_aigohotel_service() -> Optional[AIGoHotelService]:
    """获取 AIGoHotel 服务实例

    如果 AIGOHOTEL_MCP_URL 未配置，返回 None，调用方应降级到高德搜索。
    """
    global _aigohotel_service
    if _aigohotel_service is None:
        with _service_lock:
            if _aigohotel_service is None:
                try:
                    _build_mcp_config()  # 验证配置是否可用
                    _aigohotel_service = AIGoHotelService()
                except AIGoHotelConfigError as e:
                    print(f"⚠️ AIGoHotel MCP 未配置: {e}")
                    return None
    return _aigohotel_service

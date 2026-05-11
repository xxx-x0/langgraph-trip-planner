"""必应搜索 MCP 服务封装

通过魔搭社区接入必应搜索 MCP，提供中文搜索能力。
使用 langchain-mcp-adapters 官方适配器，SSE 传输方式。
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


class BingMCPConfigError(Exception):
    """必应 MCP 配置错误"""
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
    if not settings.bing_mcp_url:
        raise BingMCPConfigError("BING_MCP_URL 未配置")
    return {
        "bing": {
            "transport": "sse",
            "url": settings.bing_mcp_url,
            "timeout": 60,
            "sse_read_timeout": 300,
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
        print("🔄 必应 MCP 客户端已重置，将在下次调用时重新连接")


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

        print(f"✅ 必应 MCP 适配器初始化成功")
        print(f"   工具数量: {len(_mcp_tools)}")
        if _mcp_tools:
            print("   可用工具:")
            for t in _mcp_tools:
                print(f"     - {t.name}")


async def get_mcp_tools() -> List[BaseTool]:
    await _init_mcp_client()
    return _mcp_tools


async def get_mcp_tool_by_name(name: str) -> Optional[BaseTool]:
    tools = await get_mcp_tools()
    for t in tools:
        if t.name == name or t.name.lower() == name.lower():
            return t
    return None


class BingMCPService:
    """必应 MCP 服务封装类"""

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
            raise ValueError(f"必应 MCP 工具不存在: {tool_name}")

        try:
            result = await asyncio.wait_for(
                tool.ainvoke(arguments), timeout=timeout
            )
            return result
        except Exception as e:
            if _is_connection_error(e):
                print(f"🔄 必应 MCP 连接异常 [{tool_name}]: {str(e)[:150]}")
                print("   尝试重置客户端并重新连接...")
                await _reset_mcp_client()
                try:
                    await self._ensure_initialized()
                    tool = await get_mcp_tool_by_name(tool_name)
                    if tool is None:
                        raise ValueError(
                            f"重连后必应 MCP 工具仍不存在: {tool_name}"
                        )
                    result = await asyncio.wait_for(
                        tool.ainvoke(arguments), timeout=timeout
                    )
                    print(f"✅ 必应 MCP 重连后工具调用成功 [{tool_name}]")
                    return result
                except Exception as reconnect_err:
                    print(f"❌ 必应 MCP 重连后调用仍失败 [{tool_name}]: {str(reconnect_err)[:150]}")
                    raise
            raise

    async def search(self, query: str, count: int = 5, offset: int = 0) -> Any:
        """必应搜索"""
        result = await self._call_tool(
            "bing_search",
            {"query": query, "count": count, "offset": offset},
            timeout=30.0,
        )
        return result

    async def crawl_webpage(self, url: str) -> Any:
        """抓取网页内容"""
        result = await self._call_tool(
            "crawl_webpage",
            {"url": url},
            timeout=30.0,
        )
        return result

    async def get_tools(self) -> List[BaseTool]:
        await self._ensure_initialized()
        return _mcp_tools

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        return await get_mcp_tool_by_name(name)


_bing_service: Optional[BingMCPService] = None
_service_lock = threading.Lock()


def get_bing_service() -> Optional[BingMCPService]:
    """获取必应 MCP 服务实例

    如果 BING_MCP_URL 未配置，返回 None，调用方应降级到 DuckDuckGo。
    """
    global _bing_service
    if _bing_service is None:
        with _service_lock:
            if _bing_service is None:
                try:
                    _build_mcp_config()  # 验证配置是否可用
                    _bing_service = BingMCPService()
                except BingMCPConfigError as e:
                    print(f"⚠️ 必应 MCP 未配置: {e}")
                    return None
    return _bing_service

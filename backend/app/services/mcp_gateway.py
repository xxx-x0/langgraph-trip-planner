"""Expose managed LangChain tools so get_tool callers cannot bypass resilience."""
import asyncio
from typing import Any
from langchain_core.tools import BaseTool
from pydantic import Field
from .external_calls import CallPolicy, ExternalServiceError, FailureKind, decode_tool_result, invoke_external


class ManagedMCPTool(BaseTool):
    gateway: Any = Field(exclude=True)

    def _run(self, **kwargs):
        raise NotImplementedError('Use async MCP tools')

    async def _arun(self, **kwargs):
        return await self.invoke_bounded(kwargs)

    async def invoke_bounded(self, arguments, timeout=30, max_attempts=2):
        return await self.gateway.call(self.name, arguments, timeout=timeout, max_attempts=max_attempts)


class MCPGateway:
    def __init__(self, provider, load_tools, reset):
        self.provider, self.load_tools, self.reset = provider, load_tools, reset

    async def tools(self):
        # Discovery is also bounded, including the client's initialization lock.
        raw = await invoke_external(self.provider, 'tools/list', self.load_tools,
                                    policy=CallPolicy(total_timeout=20, attempt_timeout=15), recover=self.reset)
        return [ManagedMCPTool(name=t.name, description=t.description or t.name,
                               args_schema=t.args_schema, gateway=self) for t in raw]

    async def tool(self, name):
        return next((t for t in await self.tools() if t.name.lower() == name.lower()), None)

    async def call(self, name, arguments, timeout=30, max_attempts=2):
        async def invoke():
            tools = await self.load_tools()
            tool = next((t for t in tools if t.name.lower() == name.lower()), None)
            if tool is None:
                raise ExternalServiceError(self.provider, name, FailureKind.INVALID_REQUEST)
            result = await tool.ainvoke(arguments)
            return decode_tool_result(result, self.provider, name)
        # Only stable POI identity/details are cached briefly. Never cache weather,
        # hotels/quotes, searches, routes, failures, model output or persistence.
        ttl = 300 if self.provider == 'amap' and name in {'maps_search_detail', 'maps_geo', 'maps_regeocode'} else 0
        return await invoke_external(self.provider, name, invoke,
            policy=CallPolicy(total_timeout=timeout, attempt_timeout=min(20, timeout),
                              max_attempts=min(max_attempts, 2)), recover=self.reset,
            arguments=arguments, cache_ttl=ttl)

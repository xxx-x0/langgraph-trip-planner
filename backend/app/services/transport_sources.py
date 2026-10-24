"""Read-only capability probe. No fare adapter is enabled without a verified contract."""
import asyncio
from datetime import datetime, timezone
from langchain_mcp_adapters.client import MultiServerMCPClient
from .mcp_gateway import MCPGateway
from .external_calls import ExternalServiceError

FLIGHT_URL = 'https://mcp.rollinggo.cn/mcp/flight'
RAIL_URL = 'https://www.12306.cn/index/'


async def check_flight_source():
    # Per-probe client: no cached authentication failures or cross-request session state.
    client = MultiServerMCPClient({'flight': {'transport': 'streamable_http', 'url': FLIGHT_URL}})
    async def reset():
        pass
    gateway = MCPGateway('rollinggo_flight', client.get_tools, reset)
    checked = datetime.now(timezone.utc).isoformat()
    try:
        tools = await gateway.tools()
        names = [t.name for t in tools]
        return dict(status='contract_unverified', checked_at=checked, tools=names, offers=[],
                    message='接口可连接，但价格口径与航线覆盖尚未验证，暂不显示为可用报价。')
    except asyncio.CancelledError:
        raise
    except ExternalServiceError as error:
        return dict(status='unavailable', checked_at=checked, failure_kind=error.kind.value, offers=[],
                    message='航班查询暂不可用，未获得报价。你已录入和选择的方案不会改变。')


def source_links():
    return dict(flight_documentation='https://www.modelscope.ai/mcp/servers/RollingGo/RollingGo-Flight-MCP',
                rail=RAIL_URL, rail_status='manual',
                message='铁路尚无已核实授权接口，请在12306查询后录入。航班可从航空公司官方渠道查询后录入。')

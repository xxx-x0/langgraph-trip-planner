"""基于 LangGraph 的旅行规划 Agent 系统

重构说明:
- 使用 langchain-mcp-adapters 官方适配器替代 hello_agents.MCPTool
- 所有节点函数改为异步，工具调用使用 ainvoke
- 图执行使用 ainvoke
"""

import json
import operator
import asyncio
from typing import Dict, Any, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END

from ..services.llm_service import get_llm
from ..services.langchain_amap_tools import get_langchain_amap_service, get_mcp_tools
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
from ..config import get_settings


async def _invoke_tool_with_retry(tool: BaseTool, arguments: Dict[str, Any], max_retries: int = 3) -> Any:
    last_error = None
    for attempt in range(max_retries):
        try:
            result = await tool.ainvoke(arguments)
            return result
        except Exception as e:
            last_error = e
            error_name = type(e).__name__
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"⚠️ 工具调用失败 [{tool.name}] (尝试 {attempt + 1}/{max_retries}): {error_name}: {str(e)[:100]}")
                print(f"   等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ 工具调用最终失败 [{tool.name}] (已重试 {max_retries} 次): {error_name}: {str(e)[:100]}")
    raise last_error

async def _invoke_llm_with_retry(llm_with_tools, messages: list, max_retries: int = 3) -> Any:
    last_error = None
    for attempt in range(max_retries):
        try:
            result = await llm_with_tools.ainvoke(messages)
            return result
        except Exception as e:
            last_error = e
            error_name = type(e).__name__
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 3
                print(f"⚠️ LLM调用失败 (尝试 {attempt + 1}/{max_retries}): {error_name}: {str(e)[:100]}")
                print(f"   等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ LLM调用最终失败 (已重试 {max_retries} 次): {error_name}: {str(e)[:100]}")
    raise last_error

# ============ Agent提示词 (复用并适配 LangGraph) ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
你必须使用 maps_text_search 工具来搜索景点！不要自己编造景点信息！

**工具调用说明:**
使用 maps_text_search 工具时，你需要提供以下参数：
- keywords: 景点关键词（例如："历史文化"、"公园"、"博物馆"）
- city: 城市名称（例如："北京"、"上海"）

**示例:**
用户需求: "城市: 北京, 偏好: 历史文化"
你的动作: 调用 maps_text_search(keywords="历史文化", city="北京")

**注意:**
1. 必须使用提供的工具获取真实数据，不要直接编造回答。
2. 根据用户的偏好准确提取关键词进行搜索。
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
你必须使用 maps_weather 工具来查询天气！不要自己编造天气信息！

**工具调用说明:**
使用 maps_weather 工具时，你需要提供以下参数：
- city: 城市名称（例如："北京"、"上海"）

**示例:**
用户需求: "请查询城市: 广州 的天气"
你的动作: 调用 maps_weather(city="广州")

**注意:**
1. 必须使用提供的工具获取真实数据，不要直接编造回答。
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
你必须使用 maps_text_search 工具搜索酒店！不要自己编造酒店信息！

**工具调用说明:**
使用 maps_text_search 工具搜索酒店时，你需要提供以下参数：
- keywords: 包含住宿类型和"酒店"或"宾馆"的关键词（例如："经济型酒店"、"五星级酒店"）
- city: 城市名称（例如："北京"、"上海"）

**示例:**
用户需求: "城市: 上海, 住宿偏好: 经济型"
你的动作: 调用 maps_text_search(keywords="经济型酒店", city="上海")

**注意:**
1. 必须使用提供的工具获取真实数据，不要直接编造回答。
2. 结合用户的住宿偏好构建准确的搜索关键词。
"""

ROUTE_AGENT_PROMPT = """你是交通路线规划专家。你的任务是根据城市、用户的交通偏好，以及景点和酒店的位置，规划出合理的交通路线或建议。

**重要提示:**
你必须使用以下工具来规划路线！不要自己编造路线和时间！

路线规划工具需要经纬度坐标，你需要先使用 maps_geo 工具将地址转为坐标，再调用路线规划工具。

**第一步：地址转坐标（maps_geo）**
- address: 待解析的地址（必填）
- city: 指定查询的城市（可选）

**第二步：路线规划（选择一个）**
- maps_direction_walking (步行路线规划，100km以内)
- maps_direction_driving (驾车路线规划)
- maps_direction_transit_integrated (公交路线规划，含火车/公交/地铁)

路线规划参数：
- origin: 起点经纬度，格式为 "经度,纬度"（必填，从 maps_geo 获取）
- destination: 终点经纬度，格式为 "经度,纬度"（必填，从 maps_geo 获取）
- city: 起点城市（仅公交规划必填）
- cityd: 终点城市（仅公交规划必填）

**示例:**
用户需求: "在北京市，从故宫博物院到天安门，偏好步行"
你的动作:
1. 调用 maps_geo(address="故宫博物院", city="北京") 获取起点坐标
2. 调用 maps_geo(address="天安门", city="北京") 获取终点坐标
3. 调用 maps_direction_walking(origin="116.397428,39.916527", destination="116.397128,39.916527")

**注意:**
1. 必须使用提供的工具获取真实路线数据，不要直接编造回答。
2. 从提供的景点和酒店列表中提取准确的地址。
3. 路线工具需要经纬度坐标，不能直接传地址文本！必须先用 maps_geo 转换。
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息、天气信息和路线信息，生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
"""


# ============ LangGraph 状态类 (State) ============

class TripPlannerState(TypedDict):
    """LangGraph 状态类：管理整个旅行规划流程中的数据流转"""
    request: TripRequest
    attractions_info: str
    weather_info: str
    hotels_info: str
    route_info: str
    trip_plan: Optional[TripPlan]
    errors: List[str]
    messages: Annotated[List[BaseMessage], operator.add]


# ============ LangGraph 节点 (Nodes) ============

async def search_poi_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📍 执行节点: search_poi_node")
    request = state["request"]
    keywords = request.preferences[0] if request.preferences else "景点"

    service = get_langchain_amap_service()
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([search_tool])

    prompt = ATTRACTION_AGENT_PROMPT + f"\n请搜索城市: {request.city}, 关键词: {keywords}"
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=ATTRACTION_AGENT_PROMPT), HumanMessage(content=prompt)])

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
        return {"attractions_info": str(tool_result)}

    return {"attractions_info": response.content}


async def search_weather_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🌤️  执行节点: search_weather_node")
    request = state["request"]

    service = get_langchain_amap_service()
    weather_tool = await service.get_tool("maps_weather")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([weather_tool])

    prompt = WEATHER_AGENT_PROMPT + f"\n请查询城市: {request.city} 的天气。"
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=WEATHER_AGENT_PROMPT), HumanMessage(content=prompt)])

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_result = await _invoke_tool_with_retry(weather_tool, tool_call["args"])
        return {"weather_info": str(tool_result)}

    return {"weather_info": response.content}


async def search_hotel_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🏨 执行节点: search_hotel_node")
    request = state["request"]

    service = get_langchain_amap_service()
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([search_tool])

    prompt = HOTEL_AGENT_PROMPT + f"\n请搜索城市: {request.city}, 关键词: {request.accommodation} 酒店"
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=HOTEL_AGENT_PROMPT), HumanMessage(content=prompt)])

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
        return {"hotels_info": str(tool_result)}

    return {"hotels_info": response.content}


async def plan_route_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🗺️ 执行节点: plan_route_node")
    request = state["request"]
    attractions = state.get("attractions_info", "")
    hotels = state.get("hotels_info", "")

    service = get_langchain_amap_service()
    geo_tool = await service.get_tool("maps_geo")
    route_tools = [
        geo_tool,
        await service.get_tool("maps_direction_walking"),
        await service.get_tool("maps_direction_driving"),
        await service.get_tool("maps_direction_transit_integrated")
    ]
    llm = get_llm()
    llm_with_tools = llm.bind_tools(route_tools)

    prompt = f"""
请根据以下景点和酒店信息，为用户在 {request.city} 规划合理的交通路线或提供整体的交通建议。
用户偏好的交通方式是：{request.transportation}。

【景点信息】：
{attractions}

【酒店信息】：
{hotels}

你需要选择其中最相关的位置（或从酒店到某个主要景点），使用工具查询一次路线作为代表性建议。
注意：路线规划工具需要经纬度坐标，请先用 maps_geo 将地址转为坐标，再调用路线规划工具。
"""
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=ROUTE_AGENT_PROMPT), HumanMessage(content=prompt)])

    route_results = []
    for tool_call in response.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        tool = await service.get_tool(tool_name)
        if tool:
            tool_result = await _invoke_tool_with_retry(tool, tool_args)
            route_results.append(f"[{tool_name}]: {str(tool_result)}")
        else:
            route_results.append(f"未知工具: {tool_name}")

        if tool_name.startswith("maps_direction"):
            break

    if route_results:
        return {"route_info": "\n".join(route_results)}

    return {"route_info": response.content}


async def generate_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📋 执行节点: generate_plan_node")
    request = state["request"]
    attractions = state.get("attractions_info", "")
    weather = state.get("weather_info", "")
    hotels = state.get("hotels_info", "")
    routes = state.get("route_info", "")

    prompt = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}

**收集到的信息:**
[景点]: {attractions}
[天气]: {weather}
[酒店]: {hotels}
[路线]: {routes}
"""
    if request.free_text_input:
        prompt += f"\n**额外要求:** {request.free_text_input}"

    llm = get_llm()
    try:
        response = await _invoke_llm_with_retry(llm, [SystemMessage(content=PLANNER_AGENT_PROMPT), HumanMessage(content=prompt)])
        trip_plan = _parse_response(response.content, request)
        return {"trip_plan": trip_plan}
    except Exception as e:
        print(f"⚠️ 解析计划失败: {str(e)}")
        return {"trip_plan": None, "errors": [str(e)]}


def _parse_response(response_text: str, request: TripRequest) -> TripPlan:
    try:
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "{" in response_text and "}" in response_text:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            json_str = response_text[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON数据")

        data = json.loads(json_str)
        trip_plan = TripPlan(**data)
        return trip_plan
    except Exception as e:
        raise ValueError(f"解析 JSON 失败: {str(e)}")


def _create_fallback_plan(request: TripRequest) -> TripPlan:
    from datetime import datetime, timedelta

    start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

    days = []
    for i in range(request.travel_days):
        current_date = start_date + timedelta(days=i)

        day_plan = DayPlan(
            date=current_date.strftime("%Y-%m-%d"),
            day_index=i,
            description=f"第{i+1}天行程",
            transportation=request.transportation,
            accommodation=request.accommodation,
            attractions=[
                Attraction(
                    name=f"{request.city}景点{j+1}",
                    address=f"{request.city}市",
                    location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                    visit_duration=120,
                    description=f"这是{request.city}的著名景点",
                    category="景点"
                )
                for j in range(2)
            ],
            meals=[
                Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
            ]
        )
        days.append(day_plan)

    return TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=days,
        weather_info=[],
        overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。"
    )


# ============ 图构建逻辑 (Graph Builder) ============

def create_trip_planner_graph() -> StateGraph:
    workflow = StateGraph(TripPlannerState)

    workflow.add_node("search_poi", search_poi_node)
    workflow.add_node("search_weather", search_weather_node)
    workflow.add_node("search_hotel", search_hotel_node)
    workflow.add_node("plan_route", plan_route_node)
    workflow.add_node("generate_plan", generate_plan_node)

    workflow.add_edge(START, "search_poi")
    workflow.add_edge(START, "search_weather")
    workflow.add_edge(START, "search_hotel")

    workflow.add_edge("search_poi", "plan_route")
    workflow.add_edge("search_hotel", "plan_route")
    workflow.add_edge("search_weather", "plan_route")

    workflow.add_edge("plan_route", "generate_plan")
    workflow.add_edge("generate_plan", END)

    app = workflow.compile()
    return app


# ============ 主入口类 ============

class LangGraphTripPlanner:
    """基于 LangGraph 的旅行规划系统封装类"""

    def __init__(self):
        print("🔄 初始化 LangGraph 旅行规划系统...")
        self.app = create_trip_planner_graph()

    async def plan_trip(self, request: TripRequest) -> TripPlan:
        print(f"\n{'='*60}")
        print(f"🚀 开始 LangGraph 协作规划旅行...")
        print(f"目的地: {request.city} | 日期: {request.start_date} 至 {request.end_date}")
        print(f"{'='*60}\n")

        try:
            print("⏳ 预初始化 LLM 和 MCP 服务...")
            get_llm()
            await get_mcp_tools()
            print("✅ 服务预初始化完成")
        except Exception as e:
            print(f"⚠️ 服务预初始化失败: {e}")

        initial_state = {
            "request": request,
            "attractions_info": "",
            "weather_info": "",
            "hotels_info": "",
            "route_info": "",
            "trip_plan": None,
            "errors": [],
            "messages": []
        }

        try:
            final_state = await self.app.ainvoke(initial_state)
            trip_plan = final_state.get("trip_plan")

            if not trip_plan:
                print("⚠️ 警告：生成的计划为空，可能大模型解析失败。将使用备用方案生成计划。")
                return _create_fallback_plan(request)

            print(f"{'='*60}")
            print(f"✅ LangGraph 旅行计划生成完成!")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return _create_fallback_plan(request)


    async def plan_trip_stream(self, request: TripRequest):
        """流式生成旅行计划，通过 async generator 产出进度事件

        使用 LangGraph 的 astream 方法，每完成一个节点就产出进度事件，
        同时收集最终状态，无需额外调用 ainvoke。
        """
        print(f"\n{'='*60}")
        print(f"🚀 开始 LangGraph 流式协作规划旅行...")
        print(f"目的地: {request.city} | 日期: {request.start_date} 至 {request.end_date}")
        print(f"{'='*60}\n")

        try:
            print("⏳ 预初始化 LLM 和 MCP 服务...")
            get_llm()
            await get_mcp_tools()
            print("✅ 服务预初始化完成")
        except Exception as e:
            print(f"⚠️ 服务预初始化失败: {e}")

        yield {"type": "init", "message": "正在初始化服务...", "progress": 5}

        initial_state = {
            "request": request,
            "attractions_info": "",
            "weather_info": "",
            "hotels_info": "",
            "route_info": "",
            "trip_plan": None,
            "errors": [],
            "messages": []
        }

        NODE_INFO = {
            "search_poi": {"message": "🔍 正在搜索景点...", "progress": 20, "done_msg": "✅ 景点搜索完成"},
            "search_weather": {"message": "🌤️ 正在查询天气...", "progress": 20, "done_msg": "✅ 天气查询完成"},
            "search_hotel": {"message": "🏨 正在推荐酒店...", "progress": 20, "done_msg": "✅ 酒店推荐完成"},
            "plan_route": {"message": "🗺️ 正在规划路线...", "progress": 60, "done_msg": "✅ 路线规划完成"},
            "generate_plan": {"message": "📋 正在生成行程计划...", "progress": 80, "done_msg": "✅ 行程计划生成完成"},
        }

        completed_nodes = set()
        final_state = dict(initial_state)

        try:
            async for chunk in self.app.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        for key, value in node_output.items():
                            if key in final_state:
                                existing = final_state[key]
                                if isinstance(existing, list) and isinstance(value, list):
                                    existing.extend(value)
                                else:
                                    final_state[key] = value
                            else:
                                final_state[key] = value

                    if node_name in NODE_INFO and node_name not in completed_nodes:
                        completed_nodes.add(node_name)
                        info = NODE_INFO[node_name]
                        yield {
                            "type": "node_complete",
                            "node": node_name,
                            "message": info["done_msg"],
                            "progress": info["progress"],
                        }

            trip_plan = final_state.get("trip_plan")

            if not trip_plan:
                print("⚠️ 警告：生成的计划为空，使用备用方案")
                trip_plan = _create_fallback_plan(request)

            plan_dict = trip_plan.model_dump() if hasattr(trip_plan, 'model_dump') else trip_plan.dict()
            yield {"type": "complete", "message": "✅ 旅行计划生成完成!", "progress": 100, "data": plan_dict}

            print(f"{'='*60}")
            print(f"✅ LangGraph 流式旅行计划生成完成!")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ 流式生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "message": f"生成失败: {str(e)}", "progress": 0}


_langgraph_planner = None

def get_trip_planner_agent() -> LangGraphTripPlanner:
    global _langgraph_planner
    if _langgraph_planner is None:
        _langgraph_planner = LangGraphTripPlanner()
    return _langgraph_planner

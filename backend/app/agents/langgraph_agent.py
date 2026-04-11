"""基于 LangGraph 的旅行规划 Agent 系统

重构说明:
- 使用 langchain-mcp-adapters 官方适配器替代 hello_agents.MCPTool
- 所有节点函数改为异步，工具调用使用 ainvoke
- 图执行使用 ainvoke
"""

import json
import re
import math
import operator
import asyncio
import random
from typing import Dict, Any, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END

from ..services.llm_service import get_llm
from ..services.langchain_amap_tools import get_langchain_amap_service, get_mcp_tools
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel, CompanionInfo
from ..config import get_settings
from ..logger import get_logger

# 获取日志记录器
logger = get_logger(__name__)


async def _invoke_tool_with_retry(tool: BaseTool, arguments: Dict[str, Any], max_retries: int = 5) -> Any:
    last_error = None
    for attempt in range(max_retries):
        try:
            result = await tool.ainvoke(arguments)
            return result
        except Exception as e:
            last_error = e
            error_name = type(e).__name__
            if attempt < max_retries - 1:
                base_wait = min(2 ** attempt, 30)
                jitter = random.uniform(0, 3)
                wait_time = base_wait + jitter
                print(f"⚠️ 工具调用失败 [{tool.name}] (尝试 {attempt + 1}/{max_retries}): {error_name}: {str(e)[:100]}")
                print(f"   等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ 工具调用最终失败 [{tool.name}] (已重试 {max_retries} 次): {error_name}: {str(e)[:100]}")
    raise last_error

async def _invoke_llm_with_retry(llm_with_tools, messages: list, max_retries: int = 5) -> Any:
    last_error = None
    for attempt in range(max_retries):
        try:
            result = await llm_with_tools.ainvoke(messages)
            return result
        except Exception as e:
            last_error = e
            error_name = type(e).__name__
            if attempt < max_retries - 1:
                base_wait = min(2 ** attempt, 30)
                jitter = random.uniform(0, 3)
                wait_time = base_wait + jitter
                print(f"⚠️ LLM调用失败 (尝试 {attempt + 1}/{max_retries}): {error_name}: {str(e)[:100]}")
                print(f"   等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ LLM调用最终失败 (已重试 {max_retries} 次): {error_name}: {str(e)[:100]}")
    raise last_error

# ============ Agent提示词 (复用并适配 LangGraph) ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市、用户偏好、出行同伴和预算情况搜索合适的景点。

**重要提示:**
你必须使用 maps_text_search 工具来搜索景点！不要自己编造景点信息！

**工具调用说明:**
使用 maps_text_search 工具时，你需要提供以下参数：
- keywords: 景点关键词（例如："历史文化"、"公园"、"博物馆"、"亲子乐园"）
- city: 城市名称（例如："北京"、"上海"）

**同伴类型适配策略:**
- solo(独自出行): 搜索文化体验、独立探索类景点，如博物馆、历史街区、文艺书店
- couple(情侣): 搜索浪漫景点、观景台、特色街区、网红打卡地
- family(家庭亲子): 搜索亲子乐园、动物园、科技馆、主题乐园、公园等适合儿童的景点
- friends(朋友出行): 搜索刺激体验、团队活动、网红景点、夜生活区域
- elderly(带老人): 搜索平缓步道、园林、寺庙、文化古迹等体力要求低的景点
- group(团队出行): 搜索大型景区、可容纳团队的景点、标志性景点

**预算适配策略:**
- 如果有预算限制，优先搜索免费或低价景点（公园、历史街区、免费博物馆等）
- 如果预算充裕，可以包含收费较高的知名景点和主题乐园

**示例:**
用户需求: "城市: 北京, 偏好: 历史文化, 同伴: 家庭亲子"
你的动作: 调用 maps_text_search(keywords="亲子博物馆", city="北京") 和 maps_text_search(keywords="历史文化", city="北京")

**注意:**
1. 必须使用提供的工具获取真实数据，不要直接编造回答。
2. 根据用户的偏好和同伴类型准确提取关键词进行搜索。
3. 搜索结果中可能包含价格信息（如门票价格），请保留这些信息，后续需要用于预算计算。
4. 如果用户有预算限制，优先选择免费或低价景点。
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

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市、景点位置、用户住宿偏好、出行人数和预算推荐合适的酒店。

**重要提示:**
你必须使用 maps_text_search 工具搜索酒店！不要自己编造酒店信息！

**工具调用说明:**
使用 maps_text_search 工具搜索酒店时，你需要提供以下参数：
- keywords: 包含住宿类型和"酒店"或"宾馆"的关键词（例如："经济型酒店"、"五星级酒店"）
- city: 城市名称（例如："北京"、"上海"）

**同伴类型适配策略:**
- solo(独自出行): 搜索青旅、经济型酒店、民宿单间
- couple(情侣): 搜索精品酒店、浪漫主题酒店、舒适型酒店
- family(家庭亲子): 搜索家庭房、亲子主题酒店、有儿童设施的酒店
- friends(朋友出行): 搜索多人间、公寓式酒店、民宿
- elderly(带老人): 搜索有电梯、无障碍设施的舒适型酒店，避免偏远位置
- group(团队出行): 搜索大型酒店、有多人间的酒店、会议酒店

**预算适配策略:**
- 如果有预算限制，根据预算计算每晚可承受的酒店价格，搜索对应价位的酒店
- 例如：3天行程预算5000元，扣除门票约300元、餐饮约900元、交通约300元，酒店预算约3500元，每晚约1166元
- 搜索时使用价格区间关键词，如"经济型酒店"(100-300元)、"舒适型酒店"(300-600元)、"豪华酒店"(600元以上)

**示例:**
用户需求: "城市: 上海, 住宿偏好: 经济型, 出行人数: 2, 预算: 每晚300元以内"
你的动作: 调用 maps_text_search(keywords="经济型酒店", city="上海")

**注意:**
1. 必须使用提供的工具获取真实数据，不要直接编造回答。
2. 结合用户的住宿偏好、出行人数和预算构建准确的搜索关键词。
3. 搜索结果中可能包含价格信息（如酒店价格范围），请保留这些信息，后续需要用于预算计算。
4. 优先推荐搜索结果中价格在用户预算范围内的酒店。
"""

FOOD_AGENT_PROMPT = """你是美食推荐专家。你的任务是根据城市、用户美食偏好、出行人数和预算搜索真实餐厅信息。

**重要提示:**
你必须使用工具来搜索真实餐厅！不要自己编造餐厅信息！

**工具调用说明:**
1. maps_around_search - 周边搜索（搜索景点附近的餐厅）
   参数: keywords(关键词), location(中心点经纬度，格式"经度,纬度"), radius(搜索半径，单位米)

2. maps_text_search - 关键词搜索（搜索城市热门餐厅）
   参数: keywords(关键词), city(城市名称)

**搜索策略:**
- 景点周边餐厅: 使用 maps_around_search，以景点坐标为中心，搜索半径2000米内的餐厅
- 城市热门餐厅: 使用 maps_text_search，搜索城市特色菜系的热门餐厅

**同伴类型适配策略:**
- solo(独自出行): 搜索适合一人食的餐厅、吧台座位、快餐小吃
- couple(情侣): 搜索氛围餐厅、特色私房菜、网红餐厅
- family(家庭亲子): 搜索亲子友好餐厅、有儿童餐的餐厅、环境宽敞的餐厅
- friends(朋友出行): 搜索火锅、烧烤、大排档等适合聚餐的餐厅
- elderly(带老人): 搜索清淡菜系、环境安静的餐厅、老字号
- group(团队出行): 搜索包间餐厅、大型餐厅、自助餐

**预算适配策略:**
- 如果有预算限制，根据预算计算每餐可承受的人均消费
- 例如：3天2人行程预算5000元，餐饮预算约1500元(30%)，每日约500元，每餐约170元，人均约85元
- 搜索时加入价格关键词，如"平价美食"(人均50以下)、"特色小吃"(人均30-80)、"中档餐厅"(人均80-200)

**示例:**
用户需求: "城市: 成都, 美食偏好: 本地特色, 出行人数: 2, 人均预算: 80元, 景点坐标: 104.065735,30.659462"
你的动作:
1. 调用 maps_around_search(keywords="川菜", location="104.065735,30.659462", radius="2000") 搜索景点周边餐厅
2. 调用 maps_text_search(keywords="成都火锅", city="成都") 搜索城市热门餐厅

**注意:**
1. 必须使用工具获取真实数据，不要直接编造回答。
2. 根据用户偏好、同伴类型和预算构建准确的搜索关键词。
3. 每次搜索调用1-2个工具即可，不要过度调用。
4. 搜索结果中可能包含人均消费信息，请保留这些信息，后续需要用于预算计算。
5. 优先推荐搜索结果中价格在用户预算范围内的餐厅。
"""

ROUTE_AGENT_PROMPT = """你是交通路线规划专家。你的任务是根据城市、用户的交通偏好，以及景点和酒店的位置，规划出合理的交通路线或建议。

**重要提示:**
你必须使用路线规划工具来获取真实路线数据！不要自己编造路线和时间！

**路线规划工具（选择一个）:**
- maps_direction_walking (步行路线规划，100km以内)
- maps_direction_driving (驾车路线规划)
- maps_direction_transit_integrated (公交路线规划，含火车/公交/地铁)

**参数说明:**
- origin: 起点经纬度，格式为 "经度,纬度"（必填）
- destination: 终点经纬度，格式为 "经度,纬度"（必填）
- city: 起点城市（仅公交规划必填）
- cityd: 终点城市（仅公交规划可选）

**示例:**
调用 maps_direction_walking(origin="116.397428,39.916527", destination="116.397128,39.916527")

**注意:**
1. 如果输入中已包含经纬度坐标，直接使用坐标调用路线规划工具，不需要调用 maps_geo
2. 如果没有坐标，先用 maps_geo 工具将地址转为坐标，再调用路线规划工具
3. 必须调用工具获取真实数据，不要直接编造回答
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
        {
          "type": "breakfast",
          "name": "餐厅名称（必须来自搜索结果中的真实餐厅）",
          "address": "餐厅地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "description": "推荐理由",
          "cuisine": "菜系（如：川菜/粤菜/本地菜）",
          "rating": 4.5,
          "avg_cost": 80,
          "distance": "距离景点500米",
          "source": "nearby",
          "estimated_cost": 30
        },
        {
          "type": "lunch",
          "name": "餐厅名称（必须来自搜索结果中的真实餐厅）",
          "address": "餐厅地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "description": "推荐理由",
          "cuisine": "菜系",
          "rating": 4.5,
          "avg_cost": 80,
          "distance": "距离景点200米",
          "source": "nearby",
          "estimated_cost": 50
        },
        {
          "type": "dinner",
          "name": "餐厅名称（必须来自搜索结果中的真实餐厅）",
          "address": "餐厅地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "description": "推荐理由",
          "cuisine": "菜系",
          "rating": 4.5,
          "avg_cost": 120,
          "distance": "距离酒店1公里",
          "source": "popular",
          "estimated_cost": 80
        }
      ],
      "route_segments": [
        {
          "from_name": "酒店",
          "to_name": "故宫博物院",
          "distance": "3.5公里",
          "duration": "25分钟",
          "mode": "地铁",
          "detail": "乘坐地铁1号线天安门东站B口出，步行约5分钟到达"
        },
        {
          "from_name": "故宫博物院",
          "to_name": "天坛公园",
          "distance": "5.2公里",
          "duration": "30分钟",
          "mode": "公交",
          "detail": "乘坐公交2路从天安门东→天坛西门"
        },
        {
          "from_name": "天坛公园",
          "to_name": "酒店",
          "distance": "4.0公里",
          "duration": "20分钟",
          "mode": "地铁",
          "detail": "乘坐地铁5号线天坛东门站→酒店附近"
        }
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
    "total": 2060,
    "budget_limit": 5000,
    "is_within_budget": true
  },
  "companions": {
    "count": 2,
    "type": "couple"
  }
}
```

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. **餐饮推荐必须使用搜索结果中的真实餐厅**，不要编造餐厅名称和地址
7. **source字段说明**: nearby=景点周边餐厅, popular=城市热门餐厅
8. 早餐推荐景点或酒店附近的餐厅(source=nearby)，午餐推荐景点附近的餐厅(source=nearby)，晚餐推荐城市热门餐厅(source=popular)
9. **每个景点和餐厅的location字段必须包含经纬度坐标**，从搜索结果中提取真实坐标，不要留空
10. **每天必须包含route_segments路线段信息**，基于路线搜索结果和距离矩阵，为每天生成以下路线段:
    - 酒店→当天第1个景点
    - 景点1→景点2（如有多个景点）
    - 最后一个景点→酒店
    每段路线必须包含: from_name, to_name, distance, duration, mode, detail
    detail字段要写明具体的乘车/步行指引（如地铁几号线、哪站上下车、公交几路等），参考路线搜索结果
11. 提供实用的旅行建议
12. **必须包含预算信息**:
    - 景点门票价格(ticket_price) - 必须从搜索结果中提取真实价格，如果搜索结果中没有价格信息，使用你的知识估算但标注为估算值
    - 餐饮预估费用(estimated_cost) - 基于搜索结果中的avg_cost(人均消费)和出行人数计算，estimated_cost = avg_cost × 出行人数
    - 酒店预估费用(estimated_cost) - 从搜索结果中的price_range提取真实价格
    - 预算汇总(budget)包含各项总费用
    - 如果用户设置了预算上限(budget_limit)，必须填写is_within_budget字段

**预算约束规则（如果用户设置了预算上限）:**
- 总费用(total)必须尽量控制在预算上限(budget_limit)以内
- 如果搜索结果中的酒店/餐厅价格超出预算，优先选择价格更低的选项
- 预算分配建议：酒店40-50%、餐饮25-30%、门票15-20%、交通5-10%
- 如果无法在预算内完成规划，在overall_suggestions中说明原因并给出节省建议

**同伴类型适配规则:**
- solo(独自出行): 景点游览时间可灵活，餐饮推荐一人食友好的餐厅，estimated_cost按1人计算
- couple(情侣): 推荐浪漫氛围的景点和餐厅，estimated_cost按2人计算
- family(家庭亲子): 每天景点不宜过多(2个为宜)，选择适合儿童的景点，餐饮推荐有儿童餐的餐厅，estimated_cost按家庭人数计算
- friends(朋友出行): 可安排更多互动体验，餐饮推荐适合聚餐的餐厅，estimated_cost按人数计算
- elderly(带老人): 每天景点不宜过多(2个为宜)，选择体力要求低的景点，避免爬山等，餐饮推荐清淡易消化的
- group(团队出行): 选择可容纳团队的景点和餐厅，注意团队票优惠，estimated_cost按人数计算
"""


# ============ LangGraph 状态类 (State) ============

class TripPlannerState(TypedDict):
    """LangGraph 状态类：管理整个旅行规划流程中的数据流转"""
    request: TripRequest
    attractions_info: str
    weather_info: str
    hotels_info: str
    food_info: str
    cluster_info: str
    route_info: str
    trip_plan: Optional[TripPlan]
    errors: List[str]
    messages: Annotated[List[BaseMessage], operator.add]


# ============ LangGraph 节点 (Nodes) ============

async def search_poi_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📍 执行节点: search_poi_node")
    request = state["request"]
    keywords = request.preferences[0] if request.preferences else "景点"

    companion_keywords = ""
    if request.companions:
        companion_type_map = {
            "solo": "文化体验 独立探索",
            "couple": "浪漫景点 观景台",
            "family": "亲子乐园 动物园 科技馆",
            "friends": "网红景点 体验活动",
            "elderly": "园林 寺庙 文化古迹",
            "group": "大型景区 标志性景点"
        }
        companion_keywords = companion_type_map.get(request.companions.type, "")

    budget_hint = ""
    if request.budget:
        budget_hint = f"用户总预算上限为{request.budget}元，请优先搜索免费或低价景点。"

    service = get_langchain_amap_service()
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([search_tool])

    prompt = ATTRACTION_AGENT_PROMPT + f"\n请搜索城市: {request.city}, 关键词: {keywords}"
    if companion_keywords:
        prompt += f", 同伴适配关键词: {companion_keywords}"
    if request.companions:
        prompt += f"\n出行同伴: {request.companions.count}人, 类型: {request.companions.type}"
    if budget_hint:
        prompt += f"\n{budget_hint}"

    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=ATTRACTION_AGENT_PROMPT), HumanMessage(content=prompt)])

    if response.tool_calls:
        results = []
        for tool_call in response.tool_calls:
            tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
            results.append(str(tool_result))
        return {"attractions_info": "\n".join(results)}

    print("⚠️ search_poi_node: LLM未调用工具")
    return {"attractions_info": ""}


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
        results = []
        for tool_call in response.tool_calls:
            tool_result = await _invoke_tool_with_retry(weather_tool, tool_call["args"])
            results.append(str(tool_result))
        return {"weather_info": "\n".join(results)}

    print("⚠️ search_weather_node: LLM未调用工具")
    return {"weather_info": ""}


async def search_hotel_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🏨 执行节点: search_hotel_node")
    request = state["request"]

    service = get_langchain_amap_service()
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([search_tool])

    prompt = HOTEL_AGENT_PROMPT + f"\n请搜索城市: {request.city}, 关键词: {request.accommodation} 酒店"
    if request.companions:
        prompt += f"\n出行人数: {request.companions.count}人, 同伴类型: {request.companions.type}"
    if request.budget:
        hotel_budget = int(request.budget * 0.45)
        per_night = hotel_budget // max(request.travel_days, 1)
        prompt += f"\n预算约束: 总预算{request.budget}元，酒店预算约{hotel_budget}元，每晚约{per_night}元"

    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=HOTEL_AGENT_PROMPT), HumanMessage(content=prompt)])

    if response.tool_calls:
        results = []
        for tool_call in response.tool_calls:
            tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
            results.append(str(tool_result))
        return {"hotels_info": "\n".join(results)}

    print("⚠️ search_hotel_node: LLM未调用工具")
    return {"hotels_info": ""}


async def gather_search_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🔗 执行节点: gather_search_node (搜索结果汇总)")
    return {}


CITY_FOOD_MAP = {
    "北京": {"cuisine": "京菜", "keywords": ["烤鸭", "涮羊肉", "炸酱面", "京菜"]},
    "上海": {"cuisine": "本帮菜", "keywords": ["本帮菜", "小笼包", "生煎", "上海菜"]},
    "成都": {"cuisine": "川菜", "keywords": ["火锅", "川菜", "串串", "担担面"]},
    "重庆": {"cuisine": "渝菜", "keywords": ["火锅", "小面", "渝菜", "酸辣粉"]},
    "广州": {"cuisine": "粤菜", "keywords": ["早茶", "粤菜", "煲仔饭", "肠粉"]},
    "深圳": {"cuisine": "粤菜", "keywords": ["粤菜", "潮汕菜", "海鲜", "早茶"]},
    "西安": {"cuisine": "陕菜", "keywords": ["肉夹馍", "羊肉泡馍", "凉皮", "陕菜"]},
    "杭州": {"cuisine": "杭帮菜", "keywords": ["杭帮菜", "西湖醋鱼", "龙井虾仁", "东坡肉"]},
    "南京": {"cuisine": "金陵菜", "keywords": ["盐水鸭", "鸭血粉丝", "金陵菜", "小笼包"]},
    "长沙": {"cuisine": "湘菜", "keywords": ["臭豆腐", "湘菜", "剁椒鱼头", "茶颜悦色"]},
    "武汉": {"cuisine": "鄂菜", "keywords": ["热干面", "豆皮", "鄂菜", "武昌鱼"]},
    "厦门": {"cuisine": "闽南菜", "keywords": ["沙茶面", "海蛎煎", "闽南菜", "海鲜"]},
    "昆明": {"cuisine": "滇菜", "keywords": ["过桥米线", "滇菜", "汽锅鸡", "鲜花饼"]},
    "大理": {"cuisine": "滇菜", "keywords": ["白族菜", "饵丝", "滇菜", "酸辣鱼"]},
    "丽江": {"cuisine": "滇菜", "keywords": ["纳西菜", "滇菜", "腊排骨", "鸡豆凉粉"]},
    "苏州": {"cuisine": "苏帮菜", "keywords": ["苏帮菜", "松鼠桂鱼", "阳春面", "苏式汤面"]},
    "天津": {"cuisine": "津菜", "keywords": ["狗不理", "煎饼果子", "津菜", "麻花"]},
    "青岛": {"cuisine": "鲁菜", "keywords": ["海鲜", "啤酒", "鲁菜", "烧烤"]},
    "哈尔滨": {"cuisine": "东北菜", "keywords": ["锅包肉", "东北菜", "红肠", "杀猪菜"]},
    "拉萨": {"cuisine": "藏餐", "keywords": ["酥油茶", "藏餐", "糌粑", "牦牛肉"]},
    "乌鲁木齐": {"cuisine": "新疆菜", "keywords": ["大盘鸡", "烤羊肉", "新疆菜", "手抓饭"]},
}


def _get_food_keywords(city: str, food_preference: str) -> list:
    city_info = CITY_FOOD_MAP.get(city, {"cuisine": "本地菜", "keywords": ["特色菜", "美食"]})
    if food_preference == "本地特色" or food_preference == "无特殊要求":
        return city_info["keywords"][:2]
    preference_keywords = {
        "川菜": ["川菜", "火锅", "麻辣"],
        "粤菜": ["粤菜", "早茶", "海鲜"],
        "日料": ["日料", "寿司", "拉面"],
        "西餐": ["西餐", "牛排", "意面"],
        "小吃": ["小吃", "特色小吃", "路边摊"],
        "火锅": ["火锅", "涮锅"],
        "烧烤": ["烧烤", "烤肉"],
        "海鲜": ["海鲜", "大排档"],
    }
    return preference_keywords.get(food_preference, [food_preference])


async def search_food_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🍜 执行节点: search_food_node")
    request = state["request"]
    attractions_info = state.get("attractions_info", "")

    service = get_langchain_amap_service()
    around_tool = await service.get_tool("maps_around_search")
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([around_tool, search_tool])

    food_keywords = _get_food_keywords(request.city, request.food_preference)
    city_info = CITY_FOOD_MAP.get(request.city, {"cuisine": "本地菜"})

    prompt = FOOD_AGENT_PROMPT + f"""
请搜索城市: {request.city} 的餐厅信息。

**用户美食偏好:** {request.food_preference}
**城市特色菜系:** {city_info.get("cuisine", "本地菜")}
**推荐搜索关键词:** {', '.join(food_keywords)}
"""
    if request.companions:
        prompt += f"\n**出行人数:** {request.companions.count}人, **同伴类型:** {request.companions.type}"
    if request.budget:
        meal_budget = int(request.budget * 0.30)
        daily_meal = meal_budget // max(request.travel_days, 1)
        per_meal = daily_meal // 3
        person_count = request.companions.count if request.companions else 1
        per_person = per_meal // max(person_count, 1)
        prompt += f"\n**预算约束:** 总预算{request.budget}元，餐饮预算约{meal_budget}元，每日约{daily_meal}元，每餐约{per_meal}元，人均约{per_person}元"

    prompt += f"""

**景点信息（用于周边搜索）:**
{attractions_info[:2000]}

请执行以下搜索:
1. 使用 maps_around_search 搜索景点周边的餐厅（从景点信息中提取坐标）
2. 使用 maps_text_search 搜索城市热门餐厅（关键词: {food_keywords[0]})
"""
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=FOOD_AGENT_PROMPT), HumanMessage(content=prompt)])

    food_results = []
    for tool_call in response.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        tool = await service.get_tool(tool_name)
        if tool:
            tool_result = await _invoke_tool_with_retry(tool, tool_args)
            food_results.append(f"[{tool_name}]: {str(tool_result)}")

    if food_results:
        return {"food_info": "\n".join(food_results)}

    print("⚠️ search_food_node: LLM未调用工具，返回空数据")
    return {"food_info": ""}


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _cluster_attractions_by_proximity(attractions: List[Dict], num_days: int) -> List[List[Dict]]:
    n = len(attractions)
    if n == 0:
        return []
    if n <= num_days:
        return [[a] for a in attractions]

    dist_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_distance(
                attractions[i]["latitude"], attractions[i]["longitude"],
                attractions[j]["latitude"], attractions[j]["longitude"]
            )
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d

    clusters = [[i] for i in range(n)]

    while len(clusters) > num_days:
        min_dist = float("inf")
        merge_i, merge_j = 0, 1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                cluster_dist = min(
                    dist_matrix[a][b]
                    for a in clusters[i]
                    for b in clusters[j]
                )
                if cluster_dist < min_dist:
                    min_dist = cluster_dist
                    merge_i, merge_j = i, j

        clusters[merge_i] = clusters[merge_i] + clusters[merge_j]
        clusters.pop(merge_j)

    return [[attractions[i] for i in cluster] for cluster in clusters]


def _order_cluster_by_tsp(cluster: List[Dict]) -> List[Dict]:
    if len(cluster) <= 2:
        return cluster

    ordered = [cluster[0]]
    remaining = list(cluster[1:])

    while remaining:
        last = ordered[-1]
        nearest_idx = 0
        nearest_dist = float("inf")
        for i, attr in enumerate(remaining):
            d = _haversine_distance(last["latitude"], last["longitude"], attr["latitude"], attr["longitude"])
            if d < nearest_dist:
                nearest_dist = d
                nearest_idx = i
        ordered.append(remaining.pop(nearest_idx))

    return ordered


def _select_top_attractions(clusters: List[List[Dict]], max_per_day: int = 3) -> List[List[Dict]]:
    result = []
    for cluster in clusters:
        if len(cluster) <= max_per_day:
            result.append(cluster)
        else:
            if len(cluster) > 1:
                center_lat = sum(a["latitude"] for a in cluster) / len(cluster)
                center_lon = sum(a["longitude"] for a in cluster) / len(cluster)
                scored = []
                for attr in cluster:
                    d = _haversine_distance(center_lat, center_lon, attr["latitude"], attr["longitude"])
                    scored.append((attr, d))
                scored.sort(key=lambda x: x[1])
                result.append([s[0] for s in scored[:max_per_day]])
            else:
                result.append(cluster[:max_per_day])
    return result


def _format_cluster_info(clusters: List[List[Dict]], all_attractions: List[Dict], dist_matrix: List[List[float]], trimmed: bool = False) -> str:
    lines = ["=== 每日景点分组建议（基于地理位置聚类） ===", ""]

    if trimmed:
        lines.append("⚠️ 景点数量超过每天3个的上限，已按距离聚类中心最近的原则筛选，保留每天最多3个景点")
        lines.append("")

    for day_idx, cluster in enumerate(clusters):
        lines.append(f"第{day_idx + 1}天建议景点:")
        for order_idx, attr in enumerate(cluster):
            lines.append(f"  {order_idx + 1}. {attr['name']} ({attr['longitude']:.4f}, {attr['latitude']:.4f})")

        if len(cluster) > 1:
            max_dist = 0
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    ci = all_attractions.index(cluster[i])
                    cj = all_attractions.index(cluster[j])
                    max_dist = max(max_dist, dist_matrix[ci][cj])
            lines.append(f"  组内最大距离: {max_dist:.1f}km")
        lines.append("")

    selected_names = set()
    for cluster in clusters:
        for attr in cluster:
            selected_names.add(attr["name"])

    lines.append("=== 选中景点间距离矩阵 (km) ===")
    lines.append("")

    selected_attrs = [a for a in all_attractions if a["name"] in selected_names]
    if len(selected_attrs) > 1:
        name_col_width = max(len(a["name"]) for a in selected_attrs) + 2
        header = " " * name_col_width
        for attr in selected_attrs:
            header += f"{attr['name'][:6]:>8}"
        lines.append(header)

        for i, attr in enumerate(selected_attrs):
            ci = all_attractions.index(attr)
            row = f"{attr['name'][:name_col_width - 1]:<{name_col_width}}"
            for j, attr_j in enumerate(selected_attrs):
                if i == j:
                    row += f"{'--':>8}"
                else:
                    cj = all_attractions.index(attr_j)
                    row += f"{dist_matrix[ci][cj]:>7.1f}"
            lines.append(row)

    return "\n".join(lines)


def _extract_json_array(text: str) -> Optional[List[Dict]]:
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "[" in text:
        start = text.find("[")
        end = text.rfind("]") + 1
        text = text[start:end]

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    bracket_pattern = re.compile(r'\[[\s\S]*?\]', re.DOTALL)
    for match in bracket_pattern.finditer(text):
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            continue

    return None


def _extract_poi_names(text: str) -> List[Dict]:
    pois = []
    try:
        data = None
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    data = parsed
                elif isinstance(parsed, dict):
                    data = [parsed]
            except json.JSONDecodeError:
                pass

            if data is None:
                for line in text.split('\n'):
                    line = line.strip()
                    if line.startswith("'text':") or line.startswith('"text":'):
                        content = line.split(':', 1)[1].strip().strip(',').strip('"').strip("'")
                        try:
                            parsed = json.loads(content)
                            if isinstance(parsed, dict) and "pois" in parsed:
                                data = [parsed]
                                break
                        except json.JSONDecodeError:
                            continue

        if data is None:
            json_start = text.find('{')
            if json_start >= 0:
                json_end = text.rfind('}') + 1
                try:
                    parsed = json.loads(text[json_start:json_end])
                    if isinstance(parsed, dict) and "pois" in parsed:
                        data = [parsed]
                except json.JSONDecodeError:
                    pass

        if data:
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    try:
                        inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                        if isinstance(inner, dict) and "pois" in inner:
                            for poi in inner["pois"]:
                                if "name" in poi:
                                    pois.append({"name": poi["name"], "address": poi.get("address", "")})
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif isinstance(item, dict) and "pois" in item:
                    for poi in item["pois"]:
                        if "name" in poi:
                            pois.append({"name": poi["name"], "address": poi.get("address", "")})
    except Exception:
        pass

    return pois


def _extract_coordinates_regex(text: str) -> List[Dict]:
    attractions = []

    amap_location_pattern = re.compile(
        r'"?name"?\s*[:=]\s*["\']([^"\']+)["\'].*?'
        r'"?location"?\s*[:=]\s*["\']([\d.]+)\s*,\s*([\d.]+)["\']',
        re.DOTALL | re.IGNORECASE
    )
    for m in amap_location_pattern.finditer(text):
        name = m.group(1).strip()
        try:
            lon = float(m.group(2))
            lat = float(m.group(3))
            if 73 < lon < 136 and 3 < lat < 54:
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except ValueError:
            continue

    if attractions:
        return attractions

    name_lon_lat = re.compile(
        r'"?name"?\s*[:=]\s*["\']([^"\']+)["\'].*?'
        r'"?longitude"?\s*[:=]\s*["\']?([\d.]+)["\']?.*?'
        r'"?latitude"?\s*[:=]\s*["\']?([\d.]+)["\']?',
        re.DOTALL | re.IGNORECASE
    )
    for m in name_lon_lat.finditer(text):
        name = m.group(1).strip()
        try:
            lon = float(m.group(2))
            lat = float(m.group(3))
            if 73 < lon < 136 and 3 < lat < 54:
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except ValueError:
            continue

    if attractions:
        return attractions

    lon_lat_name = re.compile(
        r'"?longitude"?\s*[:=]\s*["\']?([\d.]+)["\']?.*?'
        r'"?latitude"?\s*[:=]\s*["\']?([\d.]+)["\']?.*?'
        r'"?name"?\s*[:=]\s*["\']([^"\']+)["\']',
        re.DOTALL | re.IGNORECASE
    )
    for m in lon_lat_name.finditer(text):
        name = m.group(3).strip()
        try:
            lon = float(m.group(1))
            lat = float(m.group(2))
            if 73 < lon < 136 and 3 < lat < 54:
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except ValueError:
            continue

    if attractions:
        return attractions

    location_pattern = re.compile(
        r'"?(?:location|坐标)"?\s*[:=]\s*\{[^}]*?"?lon(?:gitude)?"?\s*[:=]\s*["\']?([\d.]+)["\']?\s*,\s*"?lat(?:itude)?"?\s*[:=]\s*["\']?([\d.]+)["\']?',
        re.DOTALL | re.IGNORECASE
    )
    name_pattern = re.compile(r'"?name"?\s*[:=]\s*["\']([^"\']+)["\']', re.IGNORECASE)

    locations = list(location_pattern.finditer(text))
    names = name_pattern.findall(text)

    for i, m in enumerate(locations):
        try:
            lon = float(m.group(1))
            lat = float(m.group(2))
            if 73 < lon < 136 and 3 < lat < 54:
                name = names[i].strip() if i < len(names) else f"景点{i+1}"
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except (ValueError, IndexError):
            continue

    return attractions


async def cluster_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🗺️ 执行节点: cluster_attractions_node")

    if state.get("cluster_info"):
        print("  ⏭️ 聚类已完成，跳过重复执行")
        return {}

    attractions_info = state.get("attractions_info", "")
    request = state["request"]

    valid_attractions = _extract_coordinates_regex(attractions_info)
    if valid_attractions:
        print(f"📊 正则提取到 {len(valid_attractions)} 个景点坐标（跳过LLM提取）")
    else:
        poi_names = _extract_poi_names(attractions_info)
        if poi_names:
            print(f"📊 从POI数据提取到 {len(poi_names)} 个景点名称，调用maps_geo获取坐标...")
            try:
                service = get_langchain_amap_service()
                geo_tool = await service.get_tool("maps_geo")
                for poi in poi_names[:20]:
                    try:
                        geo_result = await _invoke_tool_with_retry(geo_tool, {"address": poi["name"], "city": request.city})
                        result_str = str(geo_result)
                        loc_match = re.search(r'"location"\s*:\s*"([\d.]+)\s*,\s*([\d.]+)"', result_str)
                        if not loc_match:
                            loc_match = re.search(r'([\d.]+)\s*,\s*([\d.]+)', result_str)
                        if loc_match:
                            lon = float(loc_match.group(1))
                            lat = float(loc_match.group(2))
                            if 73 < lon < 136 and 3 < lat < 54:
                                valid_attractions.append({"name": poi["name"], "longitude": lon, "latitude": lat})
                    except Exception as e:
                        print(f"  ⚠️ maps_geo查询{poi['name']}失败: {e}")
                if valid_attractions:
                    print(f"📊 maps_geo获取到 {len(valid_attractions)} 个景点坐标")
            except Exception as e:
                print(f"⚠️ maps_geo批量查询失败: {e}")

        if not valid_attractions:
            print(f"📊 正则未提取到坐标，数据前500字符: {attractions_info[:500]}")
            print("📊 尝试LLM提取...")
            llm = get_llm()
            extract_prompt = f"""从以下景点搜索结果中，提取所有景点的名称和经纬度坐标。
请以JSON数组格式返回，每个元素包含 name, longitude, latitude 三个字段。longitude和latitude必须是浮点数。

**重要**: 中国的经度范围约73-136，纬度范围约3-54。请确保提取的坐标在此范围内。

搜索结果:
{attractions_info[:4000]}

请直接返回JSON数组，不要包含其他文字。示例:
[{{"name": "故宫博物院", "longitude": 116.3974, "latitude": 39.9165}}]"""

            try:
                response = await _invoke_llm_with_retry(llm, [HumanMessage(content=extract_prompt)])
                attractions_list = _extract_json_array(response.content)

                if attractions_list:
                    valid_attractions = [
                        a for a in attractions_list
                        if isinstance(a.get("longitude"), (int, float)) and isinstance(a.get("latitude"), (int, float))
                        and 73 < a["longitude"] < 136 and 3 < a["latitude"] < 54
                    ]

                if not valid_attractions:
                    print("⚠️ LLM提取也失败，尝试从原始文本正则提取...")
                    valid_attractions = _extract_coordinates_regex(response.content)
            except Exception as e:
                print(f"⚠️ LLM坐标提取异常: {e}")

    if not valid_attractions:
        print("⚠️ 未能提取有效景点坐标，跳过聚类")
        return {"cluster_info": "景点坐标提取失败，请根据景点信息自行合理分配每日行程。"}

    print(f"📊 成功提取 {len(valid_attractions)} 个景点坐标")

    n = len(valid_attractions)
    dist_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_distance(
                valid_attractions[i]["latitude"], valid_attractions[i]["longitude"],
                valid_attractions[j]["latitude"], valid_attractions[j]["longitude"]
            )
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d

    clusters = _cluster_attractions_by_proximity(valid_attractions, request.travel_days)

    for i in range(len(clusters)):
        clusters[i] = _order_cluster_by_tsp(clusters[i])

    trimmed = False
    total_attractions = sum(len(c) for c in clusters)
    max_per_day = 3
    if total_attractions > request.travel_days * max_per_day:
        print(f"✂️ 景点数量({total_attractions})超过上限({request.travel_days * max_per_day})，开始筛选...")
        clusters = _select_top_attractions(clusters, max_per_day)
        trimmed = True

    cluster_info = _format_cluster_info(clusters, valid_attractions, dist_matrix, trimmed)
    final_count = sum(len(c) for c in clusters)
    print(f"✅ 景点聚类完成: {len(valid_attractions)} 个景点 → 筛选后 {final_count} 个，分为 {len(clusters)} 组")

    return {"cluster_info": cluster_info}


async def plan_route_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🗺️ 执行节点: plan_route_node")
    request = state["request"]
    hotels = state.get("hotels_info", "")
    cluster_info = state.get("cluster_info", "")

    if not hotels:
        print("⚠️ 酒店数据尚未就绪，路线规划可能不完整")
    if not state.get("weather_info"):
        print("⚠️ 天气数据尚未就绪")

    if not cluster_info or "失败" in cluster_info:
        print("⚠️ 聚类信息不可用，使用原始景点信息进行路线规划")
        cluster_info = f"（聚类不可用，请根据以下景点信息自行分组规划路线）\n景点搜索结果: {state.get('attractions_info', '')[:2000]}"

    service = get_langchain_amap_service()
    try:
        direction_tools = [
            await service.get_tool("maps_direction_walking"),
            await service.get_tool("maps_direction_driving"),
            await service.get_tool("maps_direction_transit_integrated")
        ]
    except Exception as e:
        print(f"⚠️ 路线工具加载失败: {e}")
        return {"route_info": f"路线工具加载失败，请根据距离矩阵自行估算交通时间。"}

    llm = get_llm()
    llm_with_tools = llm.bind_tools(direction_tools)

    prompt = f"""
请根据以下每日景点分组和酒店信息，为用户在 {request.city} 规划每天的交通路线。
用户偏好的交通方式是：{request.transportation}。

【每日景点分组（基于地理位置聚类）】：
{cluster_info}

【酒店信息】：
{hotels}

**重要：你必须调用路线规划工具来获取实际的路线数据！**

请执行以下操作：
1. 从景点分组中提取每天的起点和终点坐标
2. 根据用户交通偏好选择合适的工具：
   - 步行: maps_direction_walking
   - 驾车: maps_direction_driving  
   - 公交: maps_direction_transit_integrated
3. 调用工具时参数格式：
   - origin: "经度,纬度"（如 "116.3974,39.9165"）
   - destination: "经度,纬度"
   - city: "{request.city}"（公交必填）

请至少调用1次路线规划工具，为最长路段查询路线信息。
"""
    try:
        response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=ROUTE_AGENT_PROMPT), HumanMessage(content=prompt)])
    except Exception as e:
        print(f"⚠️ LLM路线规划调用失败: {e}")
        return {"route_info": f"路线规划LLM调用失败: {str(e)[:200]}，请根据距离矩阵自行估算交通时间。"}

    route_results = []
    direction_count = 0
    for tool_call in response.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        try:
            tool = await service.get_tool(tool_name)
            if tool:
                tool_result = await _invoke_tool_with_retry(tool, tool_args)
                route_results.append(f"[{tool_name}]: {str(tool_result)}")
            else:
                route_results.append(f"未知工具: {tool_name}")
        except Exception as e:
            print(f"⚠️ 路线工具[{tool_name}]调用失败: {e}")
            route_results.append(f"[{tool_name}] 调用失败: {str(e)[:100]}")

        if tool_name.startswith("maps_direction"):
            direction_count += 1
            if direction_count >= 3:
                break

    if route_results:
        return {"route_info": "\n".join(route_results)}

    print("⚠️ plan_route_node: LLM未调用路线规划工具，尝试直接调用")
    try:
        coords = _extract_coordinates_regex(cluster_info)
        if not coords:
            coords = _extract_coordinates_regex(state.get("attractions_info", ""))
    except Exception:
        coords = []

    if len(coords) >= 2:
        try:
            tool_name = "maps_direction_transit_integrated" if request.transportation in ["公共交通", "公交"] else "maps_direction_driving"
            direct_tool = await service.get_tool(tool_name)
            origin = f"{coords[0]['longitude']},{coords[0]['latitude']}"
            destination = f"{coords[-1]['longitude']},{coords[-1]['latitude']}"
            tool_args = {"origin": origin, "destination": destination, "city": request.city}
            print(f"  直接调用 {tool_name}: {origin} → {destination}")
            tool_result = await _invoke_tool_with_retry(direct_tool, tool_args)
            return {"route_info": f"[{tool_name}]: {str(tool_result)}"}
        except Exception as e:
            print(f"⚠️ 直接调用路线工具也失败: {e}")

    return {"route_info": ""}


async def generate_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📋 执行节点: generate_plan_node")
    request = state["request"]
    attractions = state.get("attractions_info", "")
    weather = state.get("weather_info", "")
    hotels = state.get("hotels_info", "")
    food = state.get("food_info", "")
    cluster = state.get("cluster_info", "")
    routes = state.get("route_info", "")

    prompt = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 美食偏好: {request.food_preference}
"""
    if request.budget:
        prompt += f"- **预算上限: {request.budget}元**（总费用必须尽量控制在此预算内）\n"
    if request.companions:
        companion_type_labels = {
            "solo": "独自出行", "couple": "情侣出行", "family": "家庭亲子",
            "friends": "朋友出行", "elderly": "带老人出行", "group": "团队出行"
        }
        type_label = companion_type_labels.get(request.companions.type, request.companions.type)
        prompt += f"- **出行人数: {request.companions.count}人**\n"
        prompt += f"- **同伴类型: {type_label}**\n"

    prompt += f"""
**收集到的信息:**
[景点]: {attractions}
[天气]: {weather}
[酒店]: {hotels}
[美食]: {food}
[景点聚类分组]: {cluster}
[路线]: {routes if routes else "路线搜索数据不可用，请根据景点间距离和交通方式自行估算路线信息"}

**关键要求:**
1. **严格按照[景点聚类分组]的建议安排每日景点**，将同一组的景点安排在同一天，不要随意打散
2. 每组内的景点按照聚类给出的顺序安排游览（已按最近邻排序）
3. 如果聚类分组中某天景点过多或过少，可以适当调整，但必须保持地理位置相近的景点在同一天
4. 每天的餐饮推荐要结合当天的景点位置（早餐和午餐选景点周边，晚餐可选城市热门）
5. **每个景点的location字段必须包含经纬度坐标**，从[景点]搜索结果中提取，不要留空或编造
6. **每天必须包含route_segments路线段**，即使路线搜索数据不可用，也要根据景点位置和交通方式估算距离和时间
7. **返回的JSON必须严格合法**：属性名用双引号，不要有尾随逗号，不要有注释
8. **价格数据必须从搜索结果中提取真实价格**，不要随意编造价格。搜索结果中通常包含:
   - 景点的门票价格信息
   - 酒店的价格范围信息
   - 餐厅的人均消费信息
   如果搜索结果中没有价格，再使用你的知识估算
9. **餐饮estimated_cost = avg_cost × 出行人数**
"""
    if request.budget:
        prompt += f"\n10. **预算硬约束: 总费用不得超过{request.budget}元**，如果搜索结果中的选项超出预算，必须选择更便宜的替代方案"
    if request.companions and request.companions.type == "family":
        prompt += f"\n11. **家庭亲子特殊要求: 每天最多安排2个景点，选择适合儿童的景点和有儿童餐的餐厅**"
    if request.companions and request.companions.type == "elderly":
        prompt += f"\n11. **带老人特殊要求: 每天最多安排2个景点，避免爬山和体力要求高的景点，选择平缓步道和文化类景点**"
    if request.free_text_input:
        prompt += f"\n**额外要求:** {request.free_text_input}"

    llm = get_llm()
    messages = [SystemMessage(content=PLANNER_AGENT_PROMPT), HumanMessage(content=prompt)]

    structured_llm = None
    try:
        structured_llm = llm.with_structured_output(TripPlan, method="function_calling")
        print("🔧 使用 Structured Output (function_calling) 模式生成计划")
    except Exception as e:
        print(f"⚠️ Structured Output 不可用，使用手动JSON解析: {e}")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if structured_llm is not None:
                try:
                    trip_plan = await structured_llm.ainvoke(messages)
                    if trip_plan is not None:
                        return {"trip_plan": _validate_plan_coordinates(trip_plan, request)}
                    print("⚠️ Structured Output 返回空结果，降级到手动解析")
                except Exception as e:
                    err_msg = str(e)
                    if "response_format" in err_msg or "unavailable" in err_msg or "400" in err_msg:
                        print(f"⚠️ Structured Output 不受API支持，降级到手动解析: {err_msg[:100]}")
                    else:
                        print(f"⚠️ Structured Output 调用失败，降级到手动解析: {err_msg[:100]}")
                structured_llm = None

            response = await _invoke_llm_with_retry(llm, messages)
            trip_plan = _parse_response(response.content, request)
            return {"trip_plan": trip_plan}
        except Exception as e:
            print(f"⚠️ 解析计划失败 (尝试 {attempt + 1}/{max_attempts}): {str(e)[:200]}")
            if attempt < max_attempts - 1:
                prompt = f"""上一次生成的JSON格式有误，解析失败。请重新生成，确保：
1. 所有属性名用双引号包裹
2. 不要有尾随逗号（如 "a": 1, }} 或 [1, ]）
3. 不要有注释
4. 确保JSON完整，不要截断

错误信息: {str(e)[:100]}

请根据以下信息重新生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 美食偏好: {request.food_preference}

**收集到的信息:**
[景点]: {attractions}
[天气]: {weather}
[酒店]: {hotels}
[美食]: {food}
[景点聚类分组]: {cluster}
[路线]: {routes if routes else "路线搜索数据不可用，请根据景点间距离和交通方式自行估算路线信息"}

**关键要求:**
1. 严格按照[景点聚类分组]的建议安排每日景点
2. 每个景点的location字段必须包含经纬度坐标
3. 每天必须包含route_segments路线段
4. 返回的JSON必须严格合法"""
                if request.free_text_input:
                    prompt += f"\n**额外要求:** {request.free_text_input}"
                messages = [SystemMessage(content=PLANNER_AGENT_PROMPT), HumanMessage(content=prompt)]
            else:
                print(f"❌ 解析计划最终失败，使用备用方案")
                return {"trip_plan": None, "errors": [str(e)]}


def _repair_json(json_str: str) -> str:
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    json_str = re.sub(r"'", '"', json_str)
    json_str = re.sub(r'\bNaN\b', 'null', json_str)
    json_str = re.sub(r'\bInfinity\b', 'null', json_str)
    json_str = re.sub(r'\b-infinity\b', 'null', json_str, flags=re.IGNORECASE)
    json_str = re.sub(r'(\{|,)\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', json_str)
    return json_str


def _validate_plan_coordinates(trip_plan: TripPlan, request: TripRequest = None) -> TripPlan:
    for day in trip_plan.days:
        for attr in day.attractions:
            if attr.location is not None:
                lon = attr.location.longitude
                lat = attr.location.latitude
                if not (73 < lon < 136 and 3 < lat < 54):
                    attr.location = None
        for meal in day.meals:
            if meal.location is not None:
                lon = meal.location.longitude
                lat = meal.location.latitude
                if not (73 < lon < 136 and 3 < lat < 54):
                    meal.location = None

    if trip_plan.budget and request and request.budget:
        trip_plan.budget.budget_limit = request.budget
        trip_plan.budget.is_within_budget = trip_plan.budget.total <= request.budget

    if request and request.companions and not trip_plan.companions:
        trip_plan.companions = request.companions

    return trip_plan


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

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            print("⚠️ JSON解析失败，尝试修复...")
            repaired = _repair_json(json_str)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                print("⚠️ JSON修复后仍解析失败，尝试逐步截断...")
                data = None
                for end_offset in range(len(json_str) - 1, max(len(json_str) // 2, 100), -1):
                    if json_str[end_offset] == '}':
                        try:
                            candidate = json_str[:end_offset + 1] + "]}" if '"days"' in json_str[:end_offset] else json_str[:end_offset + 1]
                            data = json.loads(_repair_json(candidate))
                            break
                        except json.JSONDecodeError:
                            continue
                if data is None:
                    raise ValueError("JSON截断修复也失败")

        trip_plan = TripPlan(**data)
        return _validate_plan_coordinates(trip_plan, request)
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
                Meal(type="breakfast", name=f"当地特色早餐", description="当地特色早餐", cuisine="本地菜", source="nearby"),
                Meal(type="lunch", name=f"午餐推荐", description="午餐推荐", cuisine="本地菜", source="nearby"),
                Meal(type="dinner", name=f"晚餐推荐", description="晚餐推荐", cuisine="本地菜", source="popular")
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
    workflow.add_node("gather_search", gather_search_node)
    workflow.add_node("cluster_attractions", cluster_attractions_node)
    workflow.add_node("search_food", search_food_node)
    workflow.add_node("plan_route", plan_route_node)
    workflow.add_node("generate_plan", generate_plan_node)

    workflow.add_edge(START, "search_poi")
    workflow.add_edge(START, "search_weather")
    workflow.add_edge(START, "search_hotel")

    # workflow.add_edge("search_poi", "gather_search")
    # workflow.add_edge("search_weather", "gather_search")
    # workflow.add_edge("search_hotel", "gather_search")

    workflow.add_edge(["search_poi", "search_weather", "search_hotel"], "gather_search")

    workflow.add_edge("gather_search", "cluster_attractions")
    workflow.add_edge("cluster_attractions", "search_food")
    workflow.add_edge("search_food", "plan_route")
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
            "food_info": "",
            "cluster_info": "",
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
            "food_info": "",
            "cluster_info": "",
            "route_info": "",
            "trip_plan": None,
            "errors": [],
            "messages": []
        }

        NODE_INFO = {
            "search_poi": {"message": "🔍 正在搜索景点...", "progress": 10, "done_msg": "✅ 景点搜索完成"},
            "search_weather": {"message": "🌤️ 正在查询天气...", "progress": 10, "done_msg": "✅ 天气查询完成"},
            "search_hotel": {"message": "🏨 正在推荐酒店...", "progress": 10, "done_msg": "✅ 酒店推荐完成"},
            "gather_search": {"message": "🔗 汇总搜索结果...", "progress": 15, "done_msg": "✅ 搜索结果汇总完成"},
            "cluster_attractions": {"message": "📊 正在聚类分析景点...", "progress": 30, "done_msg": "✅ 景点聚类完成"},
            "search_food": {"message": "🍜 正在搜索美食...", "progress": 45, "done_msg": "✅ 美食搜索完成"},
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

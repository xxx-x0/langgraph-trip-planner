"""基于 LangGraph 的旅行规划 Agent 系统

重构说明:
- 使用 langchain-mcp-adapters 官方适配器替代 hello_agents.MCPTool
- 所有节点函数改为异步，工具调用使用 ainvoke
- 图执行使用 ainvoke
"""

import json
import re
import math
import asyncio
import random
from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, START, END

from ..services.llm_service import get_llm
from ..services.langchain_amap_tools import get_langchain_amap_service, get_mcp_tools
from ..models import (
    TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel, CompanionInfo,
    POIInfo, WeatherData, HotelData, FoodData, ClusterGroup, RouteSegmentData, TripPlannerState
)
from ..config import get_settings
from ..logger import get_logger, log_print

# 获取日志记录器
logger = get_logger(__name__)


def _tool_result_to_str(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(result)


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
                log_print(f"⚠️ 工具调用失败 [{tool.name}] (尝试 {attempt + 1}/{max_retries}): {error_name}: {str(e)[:100]}")
                log_print(f"   等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                log_print(f"❌ 工具调用最终失败 [{tool.name}] (已重试 {max_retries} 次): {error_name}: {str(e)[:100]}")
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
                log_print(f"⚠️ LLM调用失败 (尝试 {attempt + 1}/{max_retries}): {error_name}: {str(e)[:100]}")
                log_print(f"   等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                log_print(f"❌ LLM调用最终失败 (已重试 {max_retries} 次): {error_name}: {str(e)[:100]}")
    raise last_error

# ============ Agent提示词 (复用并适配 LangGraph) ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市、用户偏好、出行同伴和预算情况搜索合适的景点。

**重要提示:**
你必须使用 maps_text_search 工具来搜索景点！不要自己编造景点信息！

**工具调用说明:**
使用 maps_text_search 工具时，你需要提供以下参数：
- keywords: 景点关键词（例如："历史文化"、"公园"、"博物馆"、"亲子乐园"）
- city: 城市名称（例如："北京"、"上海"）

**关键词规则（非常重要！）:**
1. keywords必须包含"景点"、"公园"、"风景区"、"博物馆"、"寺"、"园"等景点类后缀词，确保搜索结果都是真正的景点
2. 禁止使用"浪漫景点"、"网红景点"等模糊词，这些会搜出婚纱店、SPA等非景点场所
3. 正确示例: "观景台 景点"、"湖 公园"、"古镇 风景区"、"博物馆"、"寺庙 园林"
4. 错误示例: "浪漫景点"、"网红打卡"、"情侣景点"（会搜出非景点结果）

**同伴类型适配策略:**
- solo(独自出行): 搜索"博物馆 景点"、"历史街区 风景区"、"文艺 公园"
- couple(情侣): 搜索"观景台 景点"、"湖 公园"、"古镇 风景区"、"特色街区 景点"
- family(家庭亲子): 搜索"亲子乐园 景点"、"动物园 公园"、"科技馆 博物馆"、"主题乐园 景点"
- friends(朋友出行): 搜索"主题乐园 景点"、"风景区 公园"、"特色街区 景点"
- elderly(带老人): 搜索"园林 公园"、"寺庙 景点"、"文化古迹 风景区"、"公园 景点"
- group(团队出行): 搜索"大型景区 风景区"、"标志性景点 公园"、"名胜古迹 景点"

**多次搜索:**
请调用2-3次工具，使用不同的关键词组合搜索，以获取更丰富的景点结果。

**预算适配策略:**
- 如果有预算限制，优先搜索免费或低价景点（公园、历史街区、免费博物馆等）
- 如果预算充裕，可以包含收费较高的知名景点和主题乐园

**示例:**
用户需求: "城市: 北京, 偏好: 历史文化, 同伴: 家庭亲子"
你的动作: 
1. 调用 maps_text_search(keywords="亲子 博物馆 景点", city="北京")
2. 调用 maps_text_search(keywords="公园 景点", city="北京")

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

FOOD_AGENT_PROMPT = """你是美食推荐专家。你的任务是根据城市、用户美食偏好、出行人数和预算搜索真实餐厅信息，整合多维度数据生成全面的美食推荐。

**重要提示:**
你必须使用工具来搜索真实餐厅！不要自己编造餐厅信息！

**工具调用说明:**
1. maps_around_search - 周边搜索（搜索景点附近的餐厅）
   参数: keywords(关键词), location(中心点经纬度，格式"经度,纬度"), radius(搜索半径，单位米)

2. maps_text_search - 关键词搜索（搜索城市热门餐厅）
   参数: keywords(关键词), city(城市名称)

**搜索策略（多维度覆盖）:**
- 景点周边餐厅: 使用 maps_around_search，以景点坐标为中心，搜索半径2000米内的餐厅（用于早餐和午餐推荐）
- 城市热门餐厅: 使用 maps_text_search，搜索城市特色菜系的热门餐厅（用于晚餐推荐）
- 特色小吃/夜市: 使用 maps_text_search，搜索城市特色小吃和夜市（用于零食和夜宵推荐）
- 如果提供了多个景点坐标，优先搜索不同区域的周边餐厅，确保覆盖面广

**同伴类型适配策略:**
- solo(独自出行): 搜索适合一人食的餐厅、吧台座位、快餐小吃、便利店美食
- couple(情侣): 搜索氛围餐厅、特色私房菜、网红餐厅、景观餐厅
- family(家庭亲子): 搜索亲子友好餐厅、有儿童餐的餐厅、环境宽敞的餐厅、连锁品牌餐厅
- friends(朋友出行): 搜索火锅、烧烤、大排档等适合聚餐的餐厅、网红打卡店
- elderly(带老人): 搜索清淡菜系、环境安静的餐厅、老字号、易消化的菜品
- group(团队出行): 搜索包间餐厅、大型餐厅、自助餐、可预约的餐厅

**预算适配策略:**
- 如果有预算限制，根据预算计算每餐可承受的人均消费
- 例如：3天2人行程预算5000元，餐饮预算约1500元(30%)，每日约500元，每餐约170元，人均约85元
- 搜索时加入价格关键词，如"平价美食"(人均50以下)、"特色小吃"(人均30-80)、"中档餐厅"(人均80-200)
- 预算有限时，午餐推荐景点周边平价餐厅，晚餐可适当放宽选择城市特色

**饮食文化参考:**
- 不同城市有不同的饮食文化和用餐习惯，搜索时注意结合当地特色
- 注意当地特色食材和时令美食
- 尊重当地用餐习俗和禁忌

**示例:**
用户需求: "城市: 成都, 美食偏好: 本地特色, 出行人数: 2, 人均预算: 80元, 景点坐标: 104.065735,30.659462"
你的动作:
1. 调用 maps_around_search(keywords="川菜", location="104.065735,30.659462", radius="2000") 搜索景点周边餐厅
2. 调用 maps_text_search(keywords="成都火锅", city="成都") 搜索城市热门餐厅
3. 调用 maps_text_search(keywords="成都特色小吃", city="成都") 搜索城市特色小吃

**注意:**
1. 必须使用工具获取真实数据，不要直接编造回答。
2. 根据用户偏好、同伴类型和预算构建准确的搜索关键词。
3. 每次搜索调用2-4个工具，确保覆盖周边餐厅、热门餐厅和特色小吃三个维度。
4. 搜索结果中可能包含人均消费信息，请保留这些信息，后续需要用于预算计算。
5. 优先推荐搜索结果中价格在用户预算范围内的餐厅。
6. 如果提供了多个景点坐标，至少对1-2个不同区域的坐标执行周边搜索。
7. 注意区分不同用餐场景：早餐(酒店/景点周边)、午餐(景点周边)、晚餐(城市热门)、夜宵(特色小吃)。
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
13. **visit_duration(游览时长)必须合理**:
    - 大型景点(故宫/长城/颐和园等): 180-240分钟
    - 中型景点(博物馆/公园/寺庙等): 90-150分钟
    - 小型景点(街区/广场/观景台等): 45-90分钟
    - 不要所有景点都设为120分钟，要根据景点实际规模给出合理时长

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


# ============ LangGraph 节点 (Nodes) ============

def _parse_poi_result(result_str: str) -> List[POIInfo]:
    """解析POI搜索结果为结构化数据，提取价格和评分"""
    pois = []
    try:
        data = json.loads(result_str)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    try:
                        inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                        if isinstance(inner, dict) and "pois" in inner:
                            for poi in inner["pois"]:
                                location = None
                                if "location" in poi:
                                    try:
                                        lon, lat = poi["location"].split(",")
                                        location = Location(longitude=float(lon), latitude=float(lat))
                                    except (ValueError, AttributeError):
                                        pass

                                cost = None
                                rating = None
                                biz_ext = poi.get("biz_ext", {})
                                if isinstance(biz_ext, dict):
                                    cost = biz_ext.get("cost") or biz_ext.get("price")
                                    rating = biz_ext.get("rating")
                                if not rating:
                                    rating = poi.get("rating")

                                pois.append(POIInfo(
                                    id=poi.get("id", ""),
                                    name=poi.get("name", ""),
                                    type=poi.get("type", ""),
                                    address=poi.get("address", ""),
                                    location=location,
                                    typecode=poi.get("typecode"),
                                    photo=poi.get("photo"),
                                    cost=str(cost) if cost else None,
                                    rating=str(rating) if rating else None
                                ))
                    except (json.JSONDecodeError, TypeError):
                        continue
    except json.JSONDecodeError:
        pass
    return pois


async def search_poi_node(state: TripPlannerState) -> Dict[str, Any]:
    log_print("📍 执行节点: search_poi_node")
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

    results = []
    all_pois = []

    if response.tool_calls:
        log_print(f"  📝 LLM调用了 {len(response.tool_calls)} 个工具")
        for i, tool_call in enumerate(response.tool_calls):
            log_print(f"  🔧 工具调用 {i+1}: {tool_call.get('name', 'unknown')} - 参数: {tool_call.get('args', {})}")
            tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
            result_str = _tool_result_to_str(tool_result)
            log_print(f"  📦 工具返回结果长度: {len(result_str)} 字符")
            results.append(result_str)
            pois = _parse_poi_result(result_str)
            log_print(f"  📍 从结果中解析到 {len(pois)} 个POI")
            all_pois.extend(pois)
        log_print(f"  ✅ LLM调用后总共解析到 {len(all_pois)} 个POI")

    # 备用策略：如果LLM调用失败或返回空结果，直接使用预设关键词搜索
    if not all_pois:
        log_print("  🔄 LLM调用失败或返回空结果，启用备用搜索策略...")
        fallback_keywords = ["景点", "旅游", "公园"]
        if companion_keywords:
            fallback_keywords.insert(0, companion_keywords.split()[0])

        for keyword in fallback_keywords[:2]:
            try:
                log_print(f"  🔍 备用搜索: {request.city} - {keyword}")
                tool_result = await _invoke_tool_with_retry(search_tool, {"keywords": keyword, "city": request.city})
                result_str = _tool_result_to_str(tool_result)
                results.append(result_str)
                pois = _parse_poi_result(result_str)
                log_print(f"  📍 备用搜索解析到 {len(pois)} 个POI")
                all_pois.extend(pois)
                if len(all_pois) >= 5:
                    break
            except Exception as e:
                log_print(f"  ⚠️ 备用搜索失败: {e}")
                continue

    log_print(f"  ✅ 最终总共解析到 {len(all_pois)} 个POI")
    pois_with_coords = sum(1 for p in all_pois if p.get("location"))
    log_print(f"  📍 其中 {pois_with_coords}/{len(all_pois)} 个POI有坐标信息")

    # 补充坐标：对没有location的POI调用maps_geo
    if pois_with_coords < len(all_pois):
        log_print(f"  🔄 补充坐标: {len(all_pois) - pois_with_coords} 个POI缺少坐标，调用maps_geo...")
        try:
            geo_tool = await service.get_tool("maps_geo")
            for poi in all_pois:
                if not poi.get("location") and poi.get("name"):
                    try:
                        geo_result = await _invoke_tool_with_retry(geo_tool, {"address": poi["name"], "city": request.city})
                        result_str = _tool_result_to_str(geo_result)
                        loc_match = re.search(r'"location"\s*:\s*"([\d.]+)\s*,\s*([\d.]+)"', result_str)
                        if not loc_match:
                            loc_match = re.search(r'([\d.]+)\s*,\s*([\d.]+)', result_str)
                        if loc_match:
                            lon = float(loc_match.group(1))
                            lat = float(loc_match.group(2))
                            if 73 < lon < 136 and 3 < lat < 54:
                                poi["location"] = Location(longitude=lon, latitude=lat)
                    except Exception as e:
                        log_print(f"  ⚠️ maps_geo查询{poi.get('name', '未知')}失败: {type(e).__name__}")
            pois_with_coords = sum(1 for p in all_pois if p.get("location"))
            log_print(f"  📍 补充后 {pois_with_coords}/{len(all_pois)} 个POI有坐标")
        except Exception as e:
            log_print(f"  ⚠️ maps_geo工具获取失败: {e}")

    return {
        "attractions_info": "\n".join(results),
        "attractions": all_pois
    }


def _parse_weather_result(result_str: str) -> List[WeatherData]:
    """解析天气结果为结构化数据"""
    weather_list = []
    try:
        data = json.loads(result_str)
    except json.JSONDecodeError:
        log_print(f"  ⚠️ 天气数据JSON解析失败，前200字符: {result_str[:200]}")
        return weather_list

    def _extract_weather_from_dict(inner: dict):
        if "forecasts" in inner:
            for forecast in inner["forecasts"]:
                if not isinstance(forecast, dict):
                    continue
                if "casts" in forecast:
                    for cast in forecast["casts"]:
                        if isinstance(cast, dict):
                            weather_list.append(WeatherData(
                                date=cast.get("date", ""),
                                day_weather=cast.get("dayweather", ""),
                                night_weather=cast.get("nightweather", ""),
                                day_temp=int(cast.get("daytemp", 0)) if cast.get("daytemp") else 0,
                                night_temp=int(cast.get("nighttemp", 0)) if cast.get("nighttemp") else 0,
                                wind_direction=cast.get("daywind", ""),
                                wind_power=cast.get("daypower", "")
                            ))
                elif "dayweather" in forecast or "daytemp" in forecast:
                    weather_list.append(WeatherData(
                        date=forecast.get("date", ""),
                        day_weather=forecast.get("dayweather", ""),
                        night_weather=forecast.get("nightweather", ""),
                        day_temp=int(forecast.get("daytemp", 0)) if forecast.get("daytemp") else 0,
                        night_temp=int(forecast.get("nighttemp", 0)) if forecast.get("nighttemp") else 0,
                        wind_direction=forecast.get("daywind", ""),
                        wind_power=forecast.get("daypower", "")
                    ))
        elif "casts" in inner:
            for cast in inner["casts"]:
                if isinstance(cast, dict):
                    weather_list.append(WeatherData(
                        date=cast.get("date", ""),
                        day_weather=cast.get("dayweather", ""),
                        night_weather=cast.get("nightweather", ""),
                        day_temp=int(cast.get("daytemp", 0)) if cast.get("daytemp") else 0,
                        night_temp=int(cast.get("nighttemp", 0)) if cast.get("nighttemp") else 0,
                        wind_direction=cast.get("daywind", ""),
                        wind_power=cast.get("daypower", "")
                    ))
        elif "lives" in inner:
            for live in inner["lives"]:
                if isinstance(live, dict):
                    weather_list.append(WeatherData(
                        date=live.get("date", ""),
                        day_weather=live.get("weather", ""),
                        night_weather=live.get("weather", ""),
                        day_temp=int(float(live.get("temperature", "0"))),
                        night_temp=int(float(live.get("temperature", "0"))),
                        wind_direction=live.get("winddirection", ""),
                        wind_power=live.get("windpower", "")
                    ))

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "text" in item:
                try:
                    inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                    if isinstance(inner, dict):
                        _extract_weather_from_dict(inner)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
            elif isinstance(item, dict):
                _extract_weather_from_dict(item)
    elif isinstance(data, dict):
        _extract_weather_from_dict(data)

    if not weather_list:
        log_print(f"  ⚠️ 天气数据未匹配已知格式，数据前300字符: {result_str[:300]}")

    return weather_list


async def search_weather_node(state: TripPlannerState) -> Dict[str, Any]:
    log_print("🌤️  执行节点: search_weather_node")
    request = state["request"]

    service = get_langchain_amap_service()
    weather_tool = await service.get_tool("maps_weather")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([weather_tool])

    prompt = WEATHER_AGENT_PROMPT + f"\n请查询城市: {request.city} 的天气。"
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=WEATHER_AGENT_PROMPT), HumanMessage(content=prompt)])

    results = []
    all_weather = []

    if response.tool_calls:
        log_print(f"  📝 LLM调用了 {len(response.tool_calls)} 个工具")
        for i, tool_call in enumerate(response.tool_calls):
            log_print(f"  🔧 工具调用 {i+1}: {tool_call.get('name', 'unknown')} - 参数: {tool_call.get('args', {})}")
            tool_result = await _invoke_tool_with_retry(weather_tool, tool_call["args"])
            result_str = _tool_result_to_str(tool_result)
            log_print(f"  📦 工具返回结果长度: {len(result_str)} 字符")
            results.append(result_str)
            weather_data = _parse_weather_result(result_str)
            log_print(f"  🌤️ 从结果中解析到 {len(weather_data)} 天天气")
            all_weather.extend(weather_data)
        log_print(f"  ✅ LLM调用后总共解析到 {len(all_weather)} 天天气")

    # 备用策略：如果LLM调用失败或返回空结果，直接查询天气
    if not all_weather:
        log_print("  🔄 LLM调用失败或返回空结果，启用备用天气查询策略...")
        try:
            log_print(f"  🔍 备用查询: {request.city} 天气")
            tool_result = await _invoke_tool_with_retry(weather_tool, {"city": request.city})
            result_str = _tool_result_to_str(tool_result)
            results.append(result_str)
            weather_data = _parse_weather_result(result_str)
            log_print(f"  🌤️ 备用查询解析到 {len(weather_data)} 天天气")
            all_weather.extend(weather_data)
        except Exception as e:
            log_print(f"  ⚠️ 备用天气查询失败: {e}")

    # 截取行程天数对应的天气
    if len(all_weather) > request.travel_days:
        log_print(f"  ✂️ 天气预报{len(all_weather)}天，截取前{request.travel_days}天")
        all_weather = all_weather[:request.travel_days]

    log_print(f"  ✅ 最终总共解析到 {len(all_weather)} 天天气")
    return {
        "weather_info": "\n".join(results) if results else f"{request.city}天气查询失败",
        "weather": all_weather
    }


def _parse_hotel_result(result_str: str) -> List[HotelData]:
    """解析酒店结果为结构化数据"""
    hotels = []
    try:
        data = json.loads(result_str)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    try:
                        inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                        if isinstance(inner, dict) and "pois" in inner:
                            for poi in inner["pois"]:
                                location = None
                                if "location" in poi:
                                    try:
                                        lon, lat = poi["location"].split(",")
                                        location = Location(longitude=float(lon), latitude=float(lat))
                                    except (ValueError, AttributeError):
                                        pass
                                hotels.append(HotelData(
                                    id=poi.get("id", ""),
                                    name=poi.get("name", ""),
                                    address=poi.get("address", ""),
                                    location=location,
                                    price_range=None,
                                    rating=None,
                                    type=None,
                                    photos=[poi.get("photo")] if poi.get("photo") else []
                                ))
                    except (json.JSONDecodeError, TypeError):
                        continue
    except json.JSONDecodeError:
        pass
    return hotels


async def search_hotel_node(state: TripPlannerState) -> Dict[str, Any]:
    log_print("🏨 执行节点: search_hotel_node")
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

    results = []
    all_hotels = []

    if response.tool_calls:
        log_print(f"  📝 LLM调用了 {len(response.tool_calls)} 个工具")
        for i, tool_call in enumerate(response.tool_calls):
            log_print(f"  🔧 工具调用 {i+1}: {tool_call.get('name', 'unknown')} - 参数: {tool_call.get('args', {})}")
            tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
            result_str = _tool_result_to_str(tool_result)
            log_print(f"  📦 工具返回结果长度: {len(result_str)} 字符")
            results.append(result_str)
            hotels = _parse_hotel_result(result_str)
            log_print(f"  🏨 从结果中解析到 {len(hotels)} 个酒店")
            all_hotels.extend(hotels)
        log_print(f"  ✅ LLM调用后总共解析到 {len(all_hotels)} 个酒店")

    # 备用策略：如果LLM调用失败或返回空结果，直接使用预设关键词搜索
    if not all_hotels:
        log_print("  🔄 LLM调用失败或返回空结果，启用备用酒店搜索策略...")
        fallback_keywords = ["酒店", "宾馆", "住宿"]

        for keyword in fallback_keywords[:2]:
            try:
                log_print(f"  🔍 备用搜索: {request.city} - {keyword}")
                tool_result = await _invoke_tool_with_retry(search_tool, {"keywords": keyword, "city": request.city})
                result_str = _tool_result_to_str(tool_result)
                results.append(result_str)
                hotels = _parse_hotel_result(result_str)
                log_print(f"  🏨 备用搜索解析到 {len(hotels)} 个酒店")
                all_hotels.extend(hotels)
                if len(all_hotels) >= 3:
                    break
            except Exception as e:
                log_print(f"  ⚠️ 备用搜索失败: {e}")
                continue

    log_print(f"  ✅ 最终总共解析到 {len(all_hotels)} 个酒店")

    hotels_with_coords = sum(1 for h in all_hotels if h.get("location"))
    if hotels_with_coords < len(all_hotels):
        log_print(f"  🔄 补充坐标: {len(all_hotels) - hotels_with_coords} 个酒店缺少坐标，调用maps_geo...")
        try:
            geo_tool = await service.get_tool("maps_geo")
            for hotel in all_hotels:
                if not hotel.get("location") and hotel.get("name"):
                    try:
                        geo_result = await _invoke_tool_with_retry(geo_tool, {"address": hotel["name"], "city": request.city})
                        result_str = _tool_result_to_str(geo_result)
                        loc_match = re.search(r'"location"\s*:\s*"([\d.]+)\s*,\s*([\d.]+)"', result_str)
                        if not loc_match:
                            loc_match = re.search(r'([\d.]+)\s*,\s*([\d.]+)', result_str)
                        if loc_match:
                            lon = float(loc_match.group(1))
                            lat = float(loc_match.group(2))
                            if 73 < lon < 136 and 3 < lat < 54:
                                hotel["location"] = Location(longitude=lon, latitude=lat)
                    except Exception:
                        pass
            hotels_with_coords = sum(1 for h in all_hotels if h.get("location"))
            log_print(f"  📍 补充后 {hotels_with_coords}/{len(all_hotels)} 个酒店有坐标")
        except Exception as e:
            log_print(f"  ⚠️ maps_geo工具获取失败: {e}")

    return {
        "hotels_info": "\n".join(results),
        "hotels": all_hotels
    }


async def gather_search_node(state: TripPlannerState) -> Dict[str, Any]:
    log_print("🔗 执行节点: gather_search_node (搜索结果汇总)")
    return {}


async def fetch_poi_details_node(state: TripPlannerState) -> Dict[str, Any]:
    """获取POI详细信息（真实价格），使用maps_search_detail工具"""
    log_print("💰 执行节点: fetch_poi_details_node (获取POI真实价格)")
    attractions = state.get("attractions", [])
    hotels = state.get("hotels", [])

    service = get_langchain_amap_service()
    detail_tool = None
    try:
        detail_tool = await service.get_tool("maps_search_detail")
    except Exception as e:
        log_print(f"  ⚠️ 获取maps_search_detail工具失败: {e}")

    if not detail_tool:
        log_print("  ⚠️ maps_search_detail工具不可用，跳过详情获取")
        return {}

    all_pois = []
    for poi in attractions:
        if poi.get("id"):
            all_pois.append(("attraction", poi))
    for poi in hotels:
        if poi.get("id"):
            all_pois.append(("hotel", poi))

    unique_ids = set()
    unique_pois = []
    for poi_type, poi in all_pois:
        poi_id = poi.get("id", "")
        if poi_id not in unique_ids:
            unique_ids.add(poi_id)
            unique_pois.append((poi_type, poi))

    detail_count = 0
    max_details = 15
    for poi_type, poi in unique_pois[:max_details]:
        try:
            detail_result = await _invoke_tool_with_retry(detail_tool, {"id": poi.get("id")})
            detail_str = _tool_result_to_str(detail_result)
            detail_data = None
            try:
                parsed = json.loads(detail_str)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "text" in item:
                            inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                            if isinstance(inner, dict):
                                detail_data = inner
                                break
                elif isinstance(parsed, dict):
                    detail_data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

            if detail_data:
                cost = None
                rating = None
                biz_ext = detail_data.get("biz_ext", {})
                if isinstance(biz_ext, dict):
                    cost = biz_ext.get("cost") or biz_ext.get("price")
                    rating = biz_ext.get("rating")
                if not rating:
                    rating = detail_data.get("rating")
                if not cost:
                    deep_type = detail_data.get("deep_type", "")
                    if deep_type == "HOTEL":
                        hotel_ext = detail_data.get("hotel_exct", {})
                        if isinstance(hotel_ext, dict):
                            cost = hotel_ext.get("price") or hotel_ext.get("lowest_price")
                    elif deep_type == "SCENIC":
                        scenic_ext = detail_data.get("scenic_exct", {})
                        if isinstance(scenic_ext, dict):
                            cost = scenic_ext.get("ticket_price") or scenic_ext.get("price")

                if cost:
                    poi["cost"] = str(cost)
                if rating:
                    poi["rating"] = str(rating)

                detail_count += 1

            await asyncio.sleep(0.1)
        except Exception as e:
            log_print(f"  ⚠️ 获取POI详情失败 [{poi.get('name', '未知')}]: {e}")
            continue

    log_print(f"  ✅ 成功获取 {detail_count}/{min(len(unique_pois), max_details)} 个POI的真实价格")
    return {"attractions": attractions, "hotels": hotels}


def _parse_food_result(result_str: str) -> List[FoodData]:
    """解析美食搜索结果为结构化数据，提取菜系、评分、人均消费等"""
    foods = []
    try:
        data = json.loads(result_str)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    try:
                        inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                        if isinstance(inner, dict) and "pois" in inner:
                            for poi in inner["pois"]:
                                location = None
                                if "location" in poi:
                                    try:
                                        lon, lat = poi["location"].split(",")
                                        location = Location(longitude=float(lon), latitude=float(lat))
                                    except (ValueError, AttributeError):
                                        pass

                                cuisine = None
                                poi_type = poi.get("type", "")
                                if poi_type:
                                    type_parts = poi_type.split(";")
                                    for part in type_parts:
                                        for kw in ["菜", "餐", "料理", "火锅", "烧烤", "面", "小吃", "海鲜", "日料", "西餐"]:
                                            if kw in part:
                                                cuisine = part.strip()
                                                break
                                        if cuisine:
                                            break

                                rating = None
                                avg_cost = None
                                biz_ext = poi.get("biz_ext", {})
                                if isinstance(biz_ext, dict):
                                    rating_raw = biz_ext.get("rating")
                                    if rating_raw:
                                        try:
                                            rating = float(rating_raw)
                                        except (ValueError, TypeError):
                                            pass
                                    cost_raw = biz_ext.get("cost") or biz_ext.get("price")
                                    if cost_raw:
                                        try:
                                            avg_cost = int(float(str(cost_raw).replace("元", "").strip()))
                                        except (ValueError, TypeError):
                                            pass
                                if not rating:
                                    rating_raw = poi.get("rating")
                                    if rating_raw:
                                        try:
                                            rating = float(rating_raw)
                                        except (ValueError, TypeError):
                                            pass

                                photos = []
                                if poi.get("photo"):
                                    photos.append(poi.get("photo"))
                                if poi.get("photos"):
                                    try:
                                        extra = poi["photos"]
                                        if isinstance(extra, list):
                                            photos.extend([p for p in extra if isinstance(p, str) and p not in photos])
                                    except Exception:
                                        pass

                                foods.append(FoodData(
                                    id=poi.get("id", ""),
                                    name=poi.get("name", ""),
                                    address=poi.get("address", "") or poi.get("pname", "") + poi.get("cityname", "") + poi.get("adname", ""),
                                    location=location,
                                    cuisine=cuisine,
                                    rating=rating,
                                    avg_cost=avg_cost,
                                    photos=photos
                                ))
                    except (json.JSONDecodeError, TypeError):
                        continue
    except json.JSONDecodeError:
        pass
    return foods


CITY_FOOD_MAP = {
    "北京": {"cuisine": "京菜", "keywords": ["烤鸭", "涮羊肉", "炸酱面", "京菜"], "must_try": ["烤鸭", "涮羊肉", "炸酱面"], "food_culture": "北京饮食融合宫廷菜与市井小吃，讲究原汁原味，四季分明", "dining_etiquette": "烤鸭建议配薄饼和葱丝，涮羊肉蘸麻酱"},
    "上海": {"cuisine": "本帮菜", "keywords": ["本帮菜", "小笼包", "生煎", "上海菜"], "must_try": ["小笼包", "生煎", "红烧肉"], "food_culture": "上海本帮菜浓油赤酱，偏甜鲜，早餐文化丰富", "dining_etiquette": "小笼包先开窗后喝汤，生煎底朝上"},
    "成都": {"cuisine": "川菜", "keywords": ["火锅", "川菜", "串串", "担担面"], "must_try": ["火锅", "担担面", "龙抄手"], "food_culture": "成都以麻辣鲜香著称，有'美食之都'称号，夜市文化丰富", "dining_etiquette": "火锅建议选牛油底料，微辣起步"},
    "重庆": {"cuisine": "渝菜", "keywords": ["火锅", "小面", "渝菜", "酸辣粉"], "must_try": ["火锅", "小面", "酸辣粉"], "food_culture": "重庆火锅以麻辣为主，小面是早餐灵魂，江湖菜豪放", "dining_etiquette": "火锅蘸油碟解辣，小面可加各种浇头"},
    "广州": {"cuisine": "粤菜", "keywords": ["早茶", "粤菜", "煲仔饭", "肠粉"], "must_try": ["早茶", "煲仔饭", "肠粉"], "food_culture": "广州'食在广州'，早茶文化深厚，讲究食材新鲜和烹饪技艺", "dining_etiquette": "早茶一盅两件，先点茶后点菜"},
    "深圳": {"cuisine": "粤菜", "keywords": ["粤菜", "潮汕菜", "海鲜", "早茶"], "must_try": ["潮汕牛肉火锅", "海鲜", "早茶"], "food_culture": "深圳汇聚全国美食，潮汕菜和海鲜为特色", "dining_etiquette": "潮汕牛肉火锅涮8秒即可"},
    "西安": {"cuisine": "陕菜", "keywords": ["肉夹馍", "羊肉泡馍", "凉皮", "陕菜"], "must_try": ["肉夹馍", "羊肉泡馍", "凉皮"], "food_culture": "西安以面食为主，回民街小吃丰富，碳水天堂", "dining_etiquette": "泡馍要自己掰，越小越入味"},
    "杭州": {"cuisine": "杭帮菜", "keywords": ["杭帮菜", "西湖醋鱼", "龙井虾仁", "东坡肉"], "must_try": ["西湖醋鱼", "东坡肉", "龙井虾仁"], "food_culture": "杭帮菜清淡精致，注重时令和刀工", "dining_etiquette": "西湖醋鱼趁热吃，龙井虾仁配茶"},
    "南京": {"cuisine": "金陵菜", "keywords": ["盐水鸭", "鸭血粉丝", "金陵菜", "小笼包"], "must_try": ["盐水鸭", "鸭血粉丝", "汤包"], "food_culture": "南京无鸭不成席，鸭文化深入骨髓", "dining_etiquette": "盐水鸭冷吃最佳，鸭血粉丝加辣油"},
    "长沙": {"cuisine": "湘菜", "keywords": ["臭豆腐", "湘菜", "剁椒鱼头", "茶颜悦色"], "must_try": ["臭豆腐", "剁椒鱼头", "糖油粑粑"], "food_culture": "长沙嗜辣，夜宵文化发达，茶饮文化兴起", "dining_etiquette": "臭豆腐配辣椒和萝卜干"},
    "武汉": {"cuisine": "鄂菜", "keywords": ["热干面", "豆皮", "鄂菜", "武昌鱼"], "must_try": ["热干面", "豆皮", "武昌鱼"], "food_culture": "武汉早餐文化'过早'丰富，热干面是灵魂", "dining_etiquette": "热干面拌匀趁热吃，豆皮要现做"},
    "厦门": {"cuisine": "闽南菜", "keywords": ["沙茶面", "海蛎煎", "闽南菜", "海鲜"], "must_try": ["沙茶面", "海蛎煎", "土笋冻"], "food_culture": "厦门海鲜和闽南小吃为主，沙茶是灵魂调料", "dining_etiquette": "海鲜现点现做，沙茶面汤底可续"},
    "昆明": {"cuisine": "滇菜", "keywords": ["过桥米线", "滇菜", "汽锅鸡", "鲜花饼"], "must_try": ["过桥米线", "汽锅鸡", "鲜花饼"], "food_culture": "昆明食材丰富，野生菌和鲜花入菜，口味酸辣", "dining_etiquette": "过桥米线先荤后素，野生菌必须煮熟"},
    "大理": {"cuisine": "滇菜", "keywords": ["白族菜", "饵丝", "滇菜", "酸辣鱼"], "must_try": ["饵丝", "酸辣鱼", "乳扇"], "food_culture": "大理白族饮食酸辣为主，乳制品独特", "dining_etiquette": "饵丝可煮可拌，乳扇烤着吃"},
    "丽江": {"cuisine": "滇菜", "keywords": ["纳西菜", "滇菜", "腊排骨", "鸡豆凉粉"], "must_try": ["腊排骨", "鸡豆凉粉", "纳西烤鱼"], "food_culture": "丽江纳西族饮食，腊味和野生菌为特色", "dining_etiquette": "腊排骨火锅配当地蔬菜"},
    "苏州": {"cuisine": "苏帮菜", "keywords": ["苏帮菜", "松鼠桂鱼", "阳春面", "苏式汤面"], "must_try": ["松鼠桂鱼", "苏式汤面", "蟹粉豆腐"], "food_culture": "苏州菜精细讲究，甜咸适中，时令性强", "dining_etiquette": "苏式面浇头现炒最佳"},
    "天津": {"cuisine": "津菜", "keywords": ["狗不理", "煎饼果子", "津菜", "麻花"], "must_try": ["煎饼果子", "狗不理包子", "麻花"], "food_culture": "天津小吃文化丰富，早餐是灵魂", "dining_etiquette": "煎饼果子必须加薄脆"},
    "青岛": {"cuisine": "鲁菜", "keywords": ["海鲜", "啤酒", "鲁菜", "烧烤"], "must_try": ["海鲜", "啤酒", "烤鱿鱼"], "food_culture": "青岛海鲜配啤酒是标配，鲁菜咸鲜为主", "dining_etiquette": "啤酒配海鲜，注意痛风"},
    "哈尔滨": {"cuisine": "东北菜", "keywords": ["锅包肉", "东北菜", "红肠", "杀猪菜"], "must_try": ["锅包肉", "红肠", "杀猪菜"], "food_culture": "哈尔滨东北菜量大实惠，俄式影响深远", "dining_etiquette": "东北菜份量大，点菜注意适量"},
    "拉萨": {"cuisine": "藏餐", "keywords": ["酥油茶", "藏餐", "糌粑", "牦牛肉"], "must_try": ["酥油茶", "牦牛肉", "糌粑"], "food_culture": "拉萨藏餐以牦牛肉和奶制品为主，高热量", "dining_etiquette": "酥油茶咸口为主，初到高原少食多餐"},
    "乌鲁木齐": {"cuisine": "新疆菜", "keywords": ["大盘鸡", "烤羊肉", "新疆菜", "手抓饭"], "must_try": ["大盘鸡", "烤羊肉串", "手抓饭"], "food_culture": "新疆菜以牛羊肉为主，香料丰富，份量十足", "dining_etiquette": "大盘鸡配皮带面，手抓饭用手或勺"},
    "三亚": {"cuisine": "海南菜", "keywords": ["海鲜", "椰子鸡", "海南菜", "清补凉"], "must_try": ["椰子鸡", "海鲜", "清补凉"], "food_culture": "三亚海鲜和热带水果丰富，椰子入菜多", "dining_etiquette": "海鲜市场买后加工，注意比价"},
    "桂林": {"cuisine": "桂菜", "keywords": ["桂林米粉", "啤酒鱼", "桂菜", "螺蛳"], "must_try": ["桂林米粉", "啤酒鱼", "螺蛳粉"], "food_culture": "桂林米粉文化深厚，酸辣口味为主", "dining_etiquette": "米粉干捞或汤粉皆可，加酸豆角"},
    "郑州": {"cuisine": "豫菜", "keywords": ["烩面", "胡辣汤", "豫菜", "焖饼"], "must_try": ["烩面", "胡辣汤", "焖饼"], "food_culture": "郑州以面食为主，胡辣汤是早餐标配", "dining_etiquette": "胡辣汤配油条或水煎包"},
    "福州": {"cuisine": "闽菜", "keywords": ["佛跳墙", "鱼丸", "闽菜", "肉燕"], "must_try": ["佛跳墙", "鱼丸", "肉燕"], "food_culture": "福州闽菜以汤菜见长，口味清淡鲜甜", "dining_etiquette": "鱼丸和肉燕是汤品，先喝汤"},
    "大连": {"cuisine": "辽菜", "keywords": ["海鲜", "烧烤", "辽菜", "东北菜"], "must_try": ["海鲜", "烤鱿鱼", "锅包肉"], "food_culture": "大连海鲜新鲜实惠，日式和俄式影响", "dining_etiquette": "海鲜当季最佳，秋蟹最肥"},
    "沈阳": {"cuisine": "辽菜", "keywords": ["老边饺子", "辽菜", "东北菜", "烧烤"], "must_try": ["老边饺子", "锅包肉", "鸡架"], "food_culture": "沈阳东北菜和烧烤文化发达，鸡架是特色", "dining_etiquette": "鸡架配老雪花啤酒"},
    "济南": {"cuisine": "鲁菜", "keywords": ["鲁菜", "把子肉", "甜沫", "油旋"], "must_try": ["把子肉", "甜沫", "油旋"], "food_culture": "济南鲁菜发源地，咸鲜为主，早餐文化丰富", "dining_etiquette": "把子肉配米饭，甜沫是咸口"},
    "太原": {"cuisine": "晋菜", "keywords": ["刀削面", "晋菜", "过油肉", "莜面"], "must_try": ["刀削面", "过油肉", "莜面栲栳栳"], "food_culture": "太原面食种类繁多，醋文化深厚", "dining_etiquette": "面食配山西老陈醋"},
    "兰州": {"cuisine": "陇菜", "keywords": ["牛肉面", "陇菜", "手抓羊肉", "酿皮"], "must_try": ["牛肉面", "手抓羊肉", "酿皮"], "food_culture": "兰州牛肉面是灵魂，清真饮食为主", "dining_etiquette": "牛肉面讲究一清二白三红四绿五黄"},
    "贵阳": {"cuisine": "黔菜", "keywords": ["酸汤鱼", "丝娃娃", "黔菜", "肠旺面"], "must_try": ["酸汤鱼", "丝娃娃", "肠旺面"], "food_culture": "贵阳酸辣口味独特，酸汤是灵魂", "dining_etiquette": "丝娃娃自己包，蘸水是关键"},
    "南宁": {"cuisine": "桂菜", "keywords": ["老友粉", "酸嘢", "桂菜", "柠檬鸭"], "must_try": ["老友粉", "酸嘢", "柠檬鸭"], "food_culture": "南宁粉文化丰富，酸嘢开胃解腻", "dining_etiquette": "老友粉趁热吃，酸嘢可当零食"},
    "呼和浩特": {"cuisine": "蒙餐", "keywords": ["手把肉", "蒙餐", "奶茶", "烧麦"], "must_try": ["手把肉", "奶茶", "烧麦"], "food_culture": "呼和浩特蒙餐以牛羊肉和奶制品为主", "dining_etiquette": "奶茶咸口，手把肉蘸韭菜花"},
    "银川": {"cuisine": "清真菜", "keywords": ["手抓羊肉", "清真菜", "羊杂碎", "盖碗茶"], "must_try": ["手抓羊肉", "羊杂碎", "盖碗茶"], "food_culture": "银川清真饮食为主，羊肉品质极佳", "dining_etiquette": "手抓羊肉配蒜，盖碗茶慢品"},
    "西宁": {"cuisine": "青藏菜", "keywords": ["牦牛肉", "青藏菜", "酿皮", "甜醅"], "must_try": ["牦牛肉", "酿皮", "甜醅"], "food_culture": "西宁多民族饮食融合，牦牛肉和面食为主", "dining_etiquette": "高原少食多餐，注意适应海拔"},
    "黄山": {"cuisine": "徽菜", "keywords": ["臭鳜鱼", "徽菜", "毛豆腐", "黄山烧饼"], "must_try": ["臭鳜鱼", "毛豆腐", "黄山烧饼"], "food_culture": "黄山徽菜重油重色重火功，发酵食品独特", "dining_etiquette": "臭鳜鱼闻臭吃香，毛豆腐煎着吃"},
}


def _get_food_keywords(city: str, food_preference: str) -> list:
    city_info = CITY_FOOD_MAP.get(city, {"cuisine": "本地菜", "keywords": ["特色菜", "美食"], "must_try": ["特色菜"]})
    if food_preference == "本地特色" or food_preference == "无特殊要求":
        keywords = city_info["keywords"][:2]
        must_try = city_info.get("must_try", [])
        if must_try:
            keywords = keywords + must_try[:1]
        return keywords
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
    log_print("🍜 执行节点: search_food_node")
    request = state["request"]
    attractions_info = state.get("attractions_info", "")
    attractions = state.get("attractions", [])
    clusters = state.get("clusters", [])

    service = get_langchain_amap_service()
    around_tool = await service.get_tool("maps_around_search")
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([around_tool, search_tool])

    food_keywords = _get_food_keywords(request.city, request.food_preference)
    city_info = CITY_FOOD_MAP.get(request.city, {"cuisine": "本地菜"})

    attraction_coords = []
    for cluster in clusters:
        center = cluster.get("center")
        if center:
            attraction_coords.append(f"{center.longitude},{center.latitude}")
    if not attraction_coords:
        for attr in attractions[:5]:
            loc = attr.get("location")
            if loc:
                lon = loc.longitude if hasattr(loc, 'longitude') else loc.get('longitude')
                lat = loc.latitude if hasattr(loc, 'latitude') else loc.get('latitude')
                if lon and lat:
                    attraction_coords.append(f"{lon},{lat}")

    coords_text = ""
    if attraction_coords:
        coords_text = "**景点坐标列表（用于周边搜索）:**\n" + "\n".join(
            f"  坐标{i+1}: {coord}" for i, coord in enumerate(attraction_coords[:6])
        )
    else:
        coords_text = f"**景点原始信息:**\n{attractions_info[:1500]}"

    prompt = FOOD_AGENT_PROMPT + f"""
请搜索城市: {request.city} 的餐厅信息。

**用户美食偏好:** {request.food_preference}
**城市特色菜系:** {city_info.get("cuisine", "本地菜")}
**推荐搜索关键词:** {', '.join(food_keywords)}
"""
    if city_info.get("must_try"):
        prompt += f"\n**城市必吃美食:** {', '.join(city_info['must_try'])}"
    if city_info.get("food_culture"):
        prompt += f"\n**城市饮食文化:** {city_info['food_culture']}"
    if city_info.get("dining_etiquette"):
        prompt += f"\n**用餐提示:** {city_info['dining_etiquette']}"
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

{coords_text}

请执行以下搜索:
1. 使用 maps_around_search 搜索景点周边的餐厅（使用上方坐标列表中的坐标）
2. 使用 maps_text_search 搜索城市热门餐厅（关键词: {food_keywords[0]})
3. 使用 maps_text_search 搜索城市特色小吃或夜市（关键词: {request.city}特色小吃）
"""

    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=FOOD_AGENT_PROMPT), HumanMessage(content=prompt)])

    results = []
    all_foods = []

    if response.tool_calls:
        log_print(f"  📝 LLM调用了 {len(response.tool_calls)} 个工具")
        for i, tool_call in enumerate(response.tool_calls):
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            log_print(f"  🔧 工具调用 {i+1}: {tool_name} - 参数: {tool_args}")

            tool = await service.get_tool(tool_name)
            if tool:
                tool_result = await _invoke_tool_with_retry(tool, tool_args)
                result_str = _tool_result_to_str(tool_result)
                log_print(f"  📦 工具返回结果长度: {len(result_str)} 字符")
                results.append(f"[{tool_name}]: {result_str}")
                foods = _parse_food_result(result_str)
                log_print(f"  🍜 从结果中解析到 {len(foods)} 个餐厅")
                all_foods.extend(foods)
        log_print(f"  ✅ LLM调用后总共解析到 {len(all_foods)} 个餐厅")

    if not all_foods:
        log_print("  🔄 LLM调用失败或返回空结果，启用备用美食搜索策略...")
        fallback_keywords = food_keywords[:2] if food_keywords else ["美食", "餐厅"]

        for keyword in fallback_keywords[:2]:
            try:
                log_print(f"  🔍 备用搜索: {request.city} - {keyword}")
                tool_result = await _invoke_tool_with_retry(search_tool, {"keywords": keyword, "city": request.city})
                result_str = _tool_result_to_str(tool_result)
                results.append(f"[maps_text_search]: {result_str}")
                foods = _parse_food_result(result_str)
                log_print(f"  🍜 备用搜索解析到 {len(foods)} 个餐厅")
                all_foods.extend(foods)
                if len(all_foods) >= 5:
                    break
            except Exception as e:
                log_print(f"  ⚠️ 备用搜索失败: {e}")
                continue

        if attraction_coords and len(all_foods) < 5:
            try:
                coord = attraction_coords[0]
                log_print(f"  🔍 备用周边搜索: 坐标 {coord}")
                tool_result = await _invoke_tool_with_retry(around_tool, {"keywords": "餐厅", "location": coord, "radius": "2000"})
                result_str = _tool_result_to_str(tool_result)
                results.append(f"[maps_around_search]: {result_str}")
                foods = _parse_food_result(result_str)
                log_print(f"  🍜 备用周边搜索解析到 {len(foods)} 个餐厅")
                all_foods.extend(foods)
            except Exception as e:
                log_print(f"  ⚠️ 备用周边搜索失败: {e}")

    unique_ids = set()
    unique_foods = []
    for food in all_foods:
        food_id = food.get("id", "")
        if food_id and food_id not in unique_ids:
            unique_ids.add(food_id)
            unique_foods.append(food)
        elif not food_id:
            unique_foods.append(food)

    unique_foods.sort(key=lambda x: x.get("rating") or 0, reverse=True)

    try:
        from hello_agents.tools.builtin.search_tool import SearchTool
        web_search_tool = SearchTool()
        web_query = f"{request.city} 美食攻略 必吃 {request.food_preference}"
        log_print(f"  🔍 网络搜索: {web_query}")
        web_result = await asyncio.to_thread(web_search_tool.run, {"input": web_query, "mode": "text"})
        if web_result:
            web_text = str(web_result)[:3000]
            results.append(f"[web_search]: {web_text}")
            log_print(f"  📦 网络搜索结果长度: {len(web_text)} 字符")
    except ImportError:
        log_print("  ⚠️ SearchTool 不可用，跳过网络搜索")
    except Exception as e:
        log_print(f"  ⚠️ 网络搜索失败: {e}")

    food_detail_count = 0
    max_food_details = 10
    foods_needing_detail = [f for f in unique_foods if f.get("id") and not f.get("avg_cost")]
    if foods_needing_detail:
        try:
            detail_tool = await service.get_tool("maps_search_detail")
            if detail_tool:
                log_print(f"  🔍 获取 {min(len(foods_needing_detail), max_food_details)} 个餐厅详情...")
                for food_item in foods_needing_detail[:max_food_details]:
                    try:
                        detail_result = await _invoke_tool_with_retry(detail_tool, {"id": food_item.get("id")})
                        detail_str = _tool_result_to_str(detail_result)
                        detail_data = None
                        try:
                            parsed = json.loads(detail_str)
                            if isinstance(parsed, list):
                                for item in parsed:
                                    if isinstance(item, dict) and "text" in item:
                                        inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                                        if isinstance(inner, dict):
                                            detail_data = inner
                                            break
                            elif isinstance(parsed, dict):
                                detail_data = parsed
                        except (json.JSONDecodeError, TypeError):
                            pass

                        if detail_data:
                            biz_ext = detail_data.get("biz_ext", {})
                            if isinstance(biz_ext, dict):
                                cost_raw = biz_ext.get("cost") or biz_ext.get("price")
                                if cost_raw:
                                    try:
                                        food_item["avg_cost"] = int(float(str(cost_raw).replace("元", "").strip()))
                                    except (ValueError, TypeError):
                                        pass
                                rating_raw = biz_ext.get("rating")
                                if rating_raw and not food_item.get("rating"):
                                    try:
                                        food_item["rating"] = float(rating_raw)
                                    except (ValueError, TypeError):
                                        pass
                            food_detail_count += 1
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        log_print(f"  ⚠️ 获取餐厅详情失败 [{food_item.get('name', '未知')}]: {e}")
                        continue
                log_print(f"  ✅ 成功获取 {food_detail_count} 个餐厅的详情")
        except Exception as e:
            log_print(f"  ⚠️ 获取maps_search_detail工具失败: {e}")

    log_print(f"  ✅ 最终去重后共 {len(unique_foods)} 个餐厅")
    return {
        "food_info": "\n".join(results) if results else "",
        "foods": unique_foods
    }


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
    log_print("🗺️ 执行节点: cluster_attractions_node")

    if state.get("cluster_info"):
        log_print("  ⏭️ 聚类已完成，跳过重复执行")
        return {}

    attractions_info = state.get("attractions_info", "")
    structured_attractions = state.get("attractions", [])
    request = state["request"]

    valid_attractions = []

    def _get_loc_coord(loc: Any) -> Optional[tuple]:
        """从 Location 对象或 dict 中提取经纬度，兼容两种格式"""
        if loc is None:
            return None
        try:
            if hasattr(loc, 'longitude') and hasattr(loc, 'latitude'):
                return (float(loc.longitude), float(loc.latitude))
            if isinstance(loc, dict):
                lon = loc.get("longitude") or loc.get("lon")
                lat = loc.get("latitude") or loc.get("lat")
                if lon is not None and lat is not None:
                    return (float(lon), float(lat))
            if isinstance(loc, str) and "," in loc:
                parts = loc.split(",")
                return (float(parts[0]), float(parts[1]))
        except (ValueError, TypeError, AttributeError):
            pass
        return None

    if structured_attractions:
        log_print(f"📊 尝试从结构化attractions中提取坐标，共 {len(structured_attractions)} 个...")
        for poi in structured_attractions:
            loc = poi.get("location")
            coord = _get_loc_coord(loc)
            if coord:
                lon, lat = coord
                if 73 < lon < 136 and 3 < lat < 54:
                    valid_attractions.append({
                        "name": poi.get("name", "未知景点"),
                        "longitude": lon,
                        "latitude": lat
                    })
        if valid_attractions:
            log_print(f"📊 从结构化数据提取到 {len(valid_attractions)} 个景点坐标")

    # 如果结构化数据没有坐标，尝试从文本中提取
    if not valid_attractions:
        valid_attractions = _extract_coordinates_regex(attractions_info)
        if valid_attractions:
            log_print(f"📊 正则提取到 {len(valid_attractions)} 个景点坐标")

    # 如果正则提取失败，尝试从POI名称调用maps_geo获取坐标
    # 仅在坐标不足时才调用 maps_geo，避免不必要的 API 调用
    min_required = request.travel_days * 2
    if len(valid_attractions) < min_required:
        poi_names = _extract_poi_names(attractions_info)
        # 过滤掉已有坐标的景点名称
        existing_names = {a["name"] for a in valid_attractions}
        missing_pois = [p for p in poi_names if p["name"] not in existing_names]
        if missing_pois:
            need_count = min_required - len(valid_attractions)
            log_print(f"📊 坐标不足({len(valid_attractions)}/{min_required})，调用maps_geo补充 {min(len(missing_pois), need_count)} 个坐标...")
            try:
                service = get_langchain_amap_service()
                geo_tool = await service.get_tool("maps_geo")
                for poi in missing_pois[:need_count]:
                    try:
                        geo_result = await _invoke_tool_with_retry(geo_tool, {"address": poi["name"], "city": request.city})
                        result_str = _tool_result_to_str(geo_result)
                        loc_match = re.search(r'"location"\s*:\s*"([\d.]+)\s*,\s*([\d.]+)"', result_str)
                        if not loc_match:
                            loc_match = re.search(r'([\d.]+)\s*,\s*([\d.]+)', result_str)
                        if loc_match:
                            lon = float(loc_match.group(1))
                            lat = float(loc_match.group(2))
                            if 73 < lon < 136 and 3 < lat < 54:
                                valid_attractions.append({"name": poi["name"], "longitude": lon, "latitude": lat})
                    except Exception as e:
                        log_print(f"  ⚠️ maps_geo查询{poi['name']}失败: {e}")
                if len(valid_attractions) > 0:
                    log_print(f"📊 maps_geo补充后共 {len(valid_attractions)} 个景点坐标")
            except Exception as e:
                log_print(f"⚠️ maps_geo批量查询失败: {e}")
    else:
        log_print(f"📊 已有 {len(valid_attractions)} 个坐标(需{min_required}个)，跳过maps_geo调用")

    # 最后尝试LLM提取
    if not valid_attractions and attractions_info:
        log_print(f"📊 正则未提取到坐标，数据前500字符: {attractions_info[:500]}")
        log_print("📊 尝试LLM提取...")
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
                log_print("⚠️ LLM提取也失败，尝试从原始文本正则提取...")
                valid_attractions = _extract_coordinates_regex(response.content)
        except Exception as e:
            log_print(f"⚠️ LLM坐标提取异常: {e}")

    if not valid_attractions:
        log_print("⚠️ 未能提取有效景点坐标，跳过聚类")
        return {"cluster_info": "景点坐标提取失败，请根据景点信息自行合理分配每日行程。"}

    log_print(f"📊 成功提取 {len(valid_attractions)} 个景点坐标")

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
        log_print(f"✂️ 景点数量({total_attractions})超过上限({request.travel_days * max_per_day})，开始筛选...")
        clusters = _select_top_attractions(clusters, max_per_day)
        trimmed = True

    cluster_info = _format_cluster_info(clusters, valid_attractions, dist_matrix, trimmed)
    final_count = sum(len(c) for c in clusters)
    log_print(f"✅ 景点聚类完成: {len(valid_attractions)} 个景点 → 筛选后 {final_count} 个，分为 {len(clusters)} 组")

    return {"cluster_info": cluster_info}


async def plan_route_node(state: TripPlannerState) -> Dict[str, Any]:
    log_print("🗺️ 执行节点: plan_route_node")
    request = state["request"]
    hotels = state.get("hotels_info", "")
    cluster_info = state.get("cluster_info", "")

    if not hotels:
        log_print("⚠️ 酒店数据尚未就绪，路线规划可能不完整")
    if not state.get("weather_info"):
        log_print("⚠️ 天气数据尚未就绪")

    if not cluster_info or "失败" in cluster_info:
        log_print("⚠️ 聚类信息不可用，使用原始景点信息进行路线规划")
        cluster_info = f"（聚类不可用，请根据以下景点信息自行分组规划路线）\n景点搜索结果: {state.get('attractions_info', '')[:2000]}"

    service = get_langchain_amap_service()
    try:
        direction_tools = [
            await service.get_tool("maps_direction_walking"),
            await service.get_tool("maps_direction_driving"),
            await service.get_tool("maps_direction_transit_integrated")
        ]
    except Exception as e:
        log_print(f"⚠️ 路线工具加载失败: {e}")
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
        log_print(f"⚠️ LLM路线规划调用失败: {e}")
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
                route_results.append(f"[{tool_name}]: {_tool_result_to_str(tool_result)}")
            else:
                route_results.append(f"未知工具: {tool_name}")
        except Exception as e:
            log_print(f"⚠️ 路线工具[{tool_name}]调用失败: {e}")
            route_results.append(f"[{tool_name}] 调用失败: {str(e)[:100]}")

        if tool_name.startswith("maps_direction"):
            direction_count += 1
            if direction_count >= 3:
                break

    if route_results:
        log_print(f"  ✅ 路线规划完成，获取到 {len(route_results)} 条路线信息")
        return {"route_info": "\n".join(route_results)}

    log_print("⚠️ plan_route_node: LLM未调用路线规划工具，尝试直接调用")

    # 尝试从多个来源提取坐标
    coords = []
    sources = [
        ("cluster_info", cluster_info),
        ("attractions_info", state.get("attractions_info", "")),
        ("structured_attractions", state.get("attractions", []))
    ]

    for source_name, source_data in sources:
        if not coords:
            try:
                if source_name == "structured_attractions" and isinstance(source_data, list):
                    # 从结构化数据提取
                    for poi in source_data:
                        if poi.get("location"):
                            loc = poi["location"]
                            try:
                                lon = float(loc.get("longitude", 0))
                                lat = float(loc.get("latitude", 0))
                                if 73 < lon < 136 and 3 < lat < 54:
                                    coords.append({
                                        "name": poi.get("name", "景点"),
                                        "longitude": lon,
                                        "latitude": lat
                                    })
                            except (ValueError, TypeError):
                                continue
                    if coords:
                        log_print(f"  📍 从结构化attractions提取到 {len(coords)} 个坐标")
                elif isinstance(source_data, str) and source_data:
                    coords = _extract_coordinates_regex(source_data)
                    if coords:
                        log_print(f"  📍 从{source_name}提取到 {len(coords)} 个坐标")
            except Exception as e:
                log_print(f"  ⚠️ 从{source_name}提取坐标失败: {e}")

    if len(coords) >= 2:
        try:
            tool_name = "maps_direction_transit_integrated" if request.transportation in ["公共交通", "公交"] else "maps_direction_driving"
            direct_tool = await service.get_tool(tool_name)
            origin = f"{coords[0]['longitude']},{coords[0]['latitude']}"
            destination = f"{coords[-1]['longitude']},{coords[-1]['latitude']}"
            tool_args = {"origin": origin, "destination": destination, "city": request.city}
            log_print(f"  直接调用 {tool_name}: {origin} → {destination}")
            tool_result = await _invoke_tool_with_retry(direct_tool, tool_args)
            log_print(f"  ✅ 直接调用成功")
            return {"route_info": f"[{tool_name}]: {_tool_result_to_str(tool_result)}"}
        except Exception as e:
            log_print(f"⚠️ 直接调用路线工具也失败: {e}")

    log_print("⚠️ 无法获取有效坐标进行路线规划")
    return {"route_info": "路线规划：未能获取景点坐标信息，请根据实际位置自行规划交通路线。"}


async def generate_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    log_print("📋 执行节点: generate_plan_node")
    request = state["request"]
    attractions = state.get("attractions_info", "")
    weather = state.get("weather_info", "")
    hotels = state.get("hotels_info", "")
    food = state.get("food_info", "")
    cluster = state.get("cluster_info", "")
    routes = state.get("route_info", "")

    structured_attractions = state.get("attractions", [])
    structured_hotels = state.get("hotels", [])
    structured_foods = state.get("foods", [])

    price_info = ""
    poi_with_prices = []
    for poi in structured_attractions:
        if poi.get("cost"):
            poi_type = poi.get("type", "")
            poi_with_prices.append(f"  - {poi.get('name', '未知')}: {poi.get('cost')}元{'(门票)' if poi_type and '景点' in poi_type else '(人均)'}")
    for poi in structured_hotels:
        if poi.get("cost"):
            poi_with_prices.append(f"  - {poi.get('name', '未知')}: {poi.get('cost')}元/晚")
    for food_item in structured_foods:
        if food_item.get("avg_cost"):
            cuisine_label = food_item.get("cuisine", "未知菜系")
            poi_with_prices.append(f"  - {food_item.get('name', '未知')}: 人均{food_item.get('avg_cost')}元 ({cuisine_label})")

    if poi_with_prices:
        price_info = "\n**已确认的真实价格（必须优先使用）:**\n" + "\n".join(poi_with_prices)

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

    food_summary = ""
    if structured_foods:
        nearby_foods = [f for f in structured_foods if f.get("location")]
        popular_foods = [f for f in structured_foods if not f.get("location")]
        food_lines = []
        for f in structured_foods[:20]:
            parts = [f.get("name", "")]
            if f.get("cuisine"):
                parts.append(f"菜系:{f['cuisine']}")
            if f.get("avg_cost"):
                parts.append(f"人均:{f['avg_cost']}元")
            if f.get("rating"):
                parts.append(f"评分:{f['rating']}")
            if f.get("address"):
                parts.append(f"地址:{f['address']}")
            loc = f.get("location")
            if loc:
                lon = loc.longitude if hasattr(loc, 'longitude') else loc.get('longitude', '')
                lat = loc.latitude if hasattr(loc, 'latitude') else loc.get('latitude', '')
                if lon and lat:
                    parts.append(f"坐标:{lon},{lat}")
            food_lines.append("  - " + " | ".join(parts))
        if food_lines:
            food_summary = "\n**结构化餐厅数据（优先使用）:**\n" + "\n".join(food_lines)
            if nearby_foods:
                food_summary += f"\n（其中{len(nearby_foods)}家有坐标，适合作为source=nearby推荐）"
            if popular_foods:
                food_summary += f"\n（其中{len(popular_foods)}家无坐标，适合作为source=popular推荐）"

    prompt += f"""
**收集到的信息:**
[景点]: {attractions}
[天气]: {weather}
[酒店]: {hotels}
[美食]: {food}
[景点聚类分组]: {cluster}
[路线]: {routes if routes else "路线搜索数据不可用，请根据景点间距离和交通方式自行估算路线信息"}
{price_info}
{food_summary}

**关键要求:**
1. **严格按照[景点聚类分组]的建议安排每日景点**，将同一组的景点安排在同一天，不要随意打散
2. 每组内的景点按照聚类给出的顺序安排游览（已按最近邻排序）
3. 如果聚类分组中某天景点过多或过少，可以适当调整，但必须保持地理位置相近的景点在同一天
4. 每天的餐饮推荐要结合当天的景点位置（早餐和午餐选景点周边，晚餐可选城市热门）
5. **每个景点的location字段必须包含经纬度坐标**，从[景点]搜索结果中提取，不要留空或编造
6. **每天必须包含route_segments路线段**，即使路线搜索数据不可用，也要根据景点位置和交通方式估算距离和时间
7. **返回的JSON必须严格合法**：属性名用双引号，不要有尾随逗号，不要有注释
8. **价格数据必须优先使用已获取的真实价格**！以下POI已通过详情查询获取到真实价格，必须优先使用:
   - 如果POI信息中包含cost字段，这就是真实价格，必须直接使用
   - 景点的cost字段即门票价格，酒店的cost字段即每晚价格，餐厅的cost字段即人均消费
   - 只有当POI没有cost字段时，才从搜索结果文本中提取价格
   - 如果搜索结果中也没有价格，再使用你的知识估算，但必须在描述中标注"价格仅供参考"
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
        log_print("🔧 使用 Structured Output (function_calling) 模式生成计划")
    except Exception as e:
        log_print(f"⚠️ Structured Output 不可用，使用手动JSON解析: {e}")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if structured_llm is not None:
                try:
                    trip_plan = await structured_llm.ainvoke(messages)
                    if trip_plan is not None:
                        return {"trip_plan": _validate_plan_coordinates(trip_plan, request)}
                    log_print("⚠️ Structured Output 返回空结果，降级到手动解析")
                except Exception as e:
                    err_msg = str(e)
                    if "response_format" in err_msg or "unavailable" in err_msg or "400" in err_msg:
                        log_print(f"⚠️ Structured Output 不受API支持，降级到手动解析: {err_msg[:100]}")
                    else:
                        log_print(f"⚠️ Structured Output 调用失败，降级到手动解析: {err_msg[:100]}")
                structured_llm = None

            response = await _invoke_llm_with_retry(llm, messages)
            trip_plan = _parse_response(response.content, request)
            return {"trip_plan": trip_plan}
        except Exception as e:
            log_print(f"⚠️ 解析计划失败 (尝试 {attempt + 1}/{max_attempts}): {str(e)[:200]}")
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
                log_print(f"❌ 解析计划最终失败，使用备用方案")
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

    calc_attractions = sum(attr.ticket_price for day in trip_plan.days for attr in day.attractions)
    calc_hotels = sum(day.hotel.estimated_cost for day in trip_plan.days if day.hotel)
    calc_meals = sum(meal.estimated_cost for day in trip_plan.days for meal in day.meals)

    if trip_plan.budget is None:
        trip_plan.budget = Budget()

    if calc_attractions > 0 or calc_hotels > 0 or calc_meals > 0:
        if trip_plan.budget.total_attractions == 0 and calc_attractions > 0:
            trip_plan.budget.total_attractions = calc_attractions
        if trip_plan.budget.total_hotels == 0 and calc_hotels > 0:
            trip_plan.budget.total_hotels = calc_hotels
        if trip_plan.budget.total_meals == 0 and calc_meals > 0:
            trip_plan.budget.total_meals = calc_meals

        recalc_total = (
            trip_plan.budget.total_attractions
            + trip_plan.budget.total_hotels
            + trip_plan.budget.total_meals
            + trip_plan.budget.total_transportation
        )
        if trip_plan.budget.total == 0 and recalc_total > 0:
            trip_plan.budget.total = recalc_total

    if request and request.budget:
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
            log_print("⚠️ JSON解析失败，尝试修复...")
            repaired = _repair_json(json_str)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                log_print("⚠️ JSON修复后仍解析失败，尝试逐步截断...")
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
    workflow.add_node("fetch_poi_details", fetch_poi_details_node)
    workflow.add_node("cluster_attractions", cluster_attractions_node)
    workflow.add_node("search_food", search_food_node)
    workflow.add_node("plan_route", plan_route_node)
    workflow.add_node("generate_plan", generate_plan_node)

    workflow.add_edge(START, "search_poi")
    workflow.add_edge(START, "search_weather")
    workflow.add_edge(START, "search_hotel")

    workflow.add_edge(["search_poi", "search_weather", "search_hotel"], "gather_search")

    workflow.add_edge("gather_search", "fetch_poi_details")
    workflow.add_edge("fetch_poi_details", "cluster_attractions")
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
        log_print("🔄 初始化 LangGraph 旅行规划系统...")
        self.app = create_trip_planner_graph()

    async def plan_trip(self, request: TripRequest) -> TripPlan:
        log_print(f"\n{'='*60}")
        log_print(f"🚀 开始 LangGraph 协作规划旅行...")
        log_print(f"目的地: {request.city} | 日期: {request.start_date} 至 {request.end_date}")
        log_print(f"{'='*60}\n")

        try:
            log_print("⏳ 预初始化 LLM 和 MCP 服务...")
            get_llm()
            await get_mcp_tools()
            log_print("✅ 服务预初始化完成")
        except Exception as e:
            log_print(f"⚠️ 服务预初始化失败: {e}")

        initial_state = {
            "request": request,
            # 结构化数据
            "attractions": [],
            "weather": [],
            "hotels": [],
            "foods": [],
            "clusters": [],
            "routes": [],
            # 原始字符串（兼容）
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
                log_print("⚠️ 警告：生成的计划为空，可能大模型解析失败。将使用备用方案生成计划。")
                return _create_fallback_plan(request)

            log_print(f"{'='*60}")
            log_print(f"✅ LangGraph 旅行计划生成完成!")
            log_print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            log_print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return _create_fallback_plan(request)


    async def plan_trip_stream(self, request: TripRequest):
        """流式生成旅行计划，通过 async generator 产出进度事件

        使用 LangGraph 的 astream 方法，每完成一个节点就产出进度事件，
        同时收集最终状态，无需额外调用 ainvoke。
        """
        log_print(f"\n{'='*60}")
        log_print(f"🚀 开始 LangGraph 流式协作规划旅行...")
        log_print(f"目的地: {request.city} | 日期: {request.start_date} 至 {request.end_date}")
        log_print(f"{'='*60}\n")

        try:
            log_print("⏳ 预初始化 LLM 和 MCP 服务...")
            get_llm()
            await get_mcp_tools()
            log_print("✅ 服务预初始化完成")
        except Exception as e:
            log_print(f"⚠️ 服务预初始化失败: {e}")

        yield {"type": "init", "message": "正在初始化服务...", "progress": 5}

        initial_state = {
            "request": request,
            # 结构化数据
            "attractions": [],
            "weather": [],
            "hotels": [],
            "foods": [],
            "clusters": [],
            "routes": [],
            # 原始字符串（兼容）
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
                log_print("⚠️ 警告：生成的计划为空，使用备用方案")
                trip_plan = _create_fallback_plan(request)

            plan_dict = trip_plan.model_dump() if hasattr(trip_plan, 'model_dump') else trip_plan.dict()
            yield {"type": "complete", "message": "✅ 旅行计划生成完成!", "progress": 100, "data": plan_dict}

            log_print(f"{'='*60}")
            log_print(f"✅ LangGraph 流式旅行计划生成完成!")
            log_print(f"{'='*60}\n")

        except Exception as e:
            log_print(f"❌ 流式生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "message": f"生成失败: {str(e)}", "progress": 0}


_langgraph_planner = None

def get_trip_planner_agent() -> LangGraphTripPlanner:
    global _langgraph_planner
    if _langgraph_planner is None:
        _langgraph_planner = LangGraphTripPlanner()
    return _langgraph_planner

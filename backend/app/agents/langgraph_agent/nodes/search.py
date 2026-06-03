import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..exceptions import NonRetryableError, _invoke_llm_with_retry, _invoke_tool_with_retry
from ..prompts import WEATHER_AGENT_PROMPT, HOTEL_AGENT_PROMPT
from ..state import TripPlannerState
from ....services.attractions_cache_service import CachedAttraction, get_attractions_cache_service
from ....services.langchain_amap_tools import get_langchain_amap_service
from ....services.llm_service import get_llm
from ....services.preferences_service import format_preference_hint


class FreeTextAnalysis(BaseModel):
    attractions: List[str] = Field(default_factory=list, description="用户指定的景点名称")
    food_preferences: List[str] = Field(default_factory=list, description="用户提到的美食/餐饮偏好")
    accommodation_preferences: List[str] = Field(default_factory=list, description="用户提到的住宿偏好")
    general_suggestions: List[str] = Field(default_factory=list, description="用户的非具体意见或建议")


class _HotelDescriptionTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments: List[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.fragments.append(text)


def _clean_hotel_description(description: Any) -> str:
    parser = _HotelDescriptionTextParser()
    parser.feed(str(description))
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.fragments)).strip()


FREE_TEXT_ANALYSIS_PROMPT = """你是一个旅行需求分析专家。请分析用户的额外要求文本，将其分类为以下四类：

1. **attractions**: 用户明确想去的景点、地标、公园、博物馆等具体地点
2. **food_preferences**: 用户提到的美食、餐饮偏好（如"吃广式早茶"、"品尝火锅"）
3. **accommodation_preferences**: 用户提到的住宿要求（如"住江景房"、"要带泳池的酒店"）
4. **general_suggestions**: 用户的其他非具体意见或建议（如"行程不要太赶"、"多留点自由时间"）

请严格按照以下JSON格式返回：
```json
{
  "attractions": ["景点1", "景点2"],
  "food_preferences": ["美食1"],
  "accommodation_preferences": ["住宿要求1"],
  "general_suggestions": ["建议1"]
}
```

注意：
- 只提取用户明确提到的内容，不要推测
- "吃XX"、"品尝XX"、"喝XX"属于food_preferences，不是attractions
- 如果某类没有内容，返回空数组
- 景点名称保持用户原始表述"""


async def analyze_free_text(free_text: str) -> Dict[str, List[str]]:
    if not free_text or not free_text.strip():
        return {"attractions": [], "food_preferences": [], "accommodation_preferences": [], "general_suggestions": []}

    llm = get_llm()
    messages = [
        SystemMessage(content=FREE_TEXT_ANALYSIS_PROMPT),
        HumanMessage(content=f"请分析以下用户额外要求：\n{free_text}"),
    ]

    try:
        response = await _invoke_llm_with_retry(llm, messages, max_retries=1, per_attempt_timeout=15.0)
        content = response.content.strip()

        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "{" in content:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            json_str = content[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON")

        data = json.loads(json_str)
        result = {
            "attractions": data.get("attractions", []),
            "food_preferences": data.get("food_preferences", []),
            "accommodation_preferences": data.get("accommodation_preferences", []),
            "general_suggestions": data.get("general_suggestions", []),
        }
        print(f"🧠 额外要求分析结果: 景点={result['attractions']}, 美食={result['food_preferences']}, 住宿={result['accommodation_preferences']}, 建议={result['general_suggestions']}")
        return result
    except Exception as e:
        print(f"⚠️ LLM分析额外要求失败，降级到简单提取: {str(e)[:100]}")
        attractions = []
        known_landmarks = [
            "广州塔", "圣心大教堂", "长隆野生动物园", "长隆欢乐世界", "长隆水上乐园",
            "故宫", "天安门", "长城", "天坛", "颐和园", "圆明园", "西湖", "外滩",
            "东方明珠", "迪士尼", "兵马俑", "大雁塔", "布达拉宫", "九寨沟",
            "张家界", "黄山", "泰山", "鼓浪屿", "武夷山", "丽江古城",
            "拙政园", "虎丘", "周庄", "乌镇", "千岛湖", "灵隐寺",
            "珠江夜游", "白云山", "越秀公园", "陈家祠", "北京路",
            "夫子庙", "中山陵", "黄鹤楼", "东湖", "武汉大学",
        ]
        for landmark in known_landmarks:
            if landmark in free_text:
                attractions.append(landmark)
        return {"attractions": attractions, "food_preferences": [], "accommodation_preferences": [], "general_suggestions": []}


def _extract_must_visit_attractions(free_text: str) -> List[str]:
    if not free_text:
        return []
    names = set()
    trigger_patterns = [
        r"想去(.+)",
        r"一定要去(.+)",
        r"必须去(.+)",
        r"特别想去(.+)",
        r"希望去(.+)",
        r"想要去(.+)",
    ]
    for pattern in trigger_patterns:
        matches = re.findall(pattern, free_text)
        for match in matches:
            parts = re.split(r"[，,、；;和还有以及\s]+", match)
            for name in parts:
                name = name.strip().rstrip("。.！!？?")
                if name and 2 <= len(name) <= 20:
                    names.add(name)
    known_landmarks = [
        "广州塔", "圣心大教堂", "长隆野生动物园", "长隆欢乐世界", "长隆水上乐园",
        "故宫", "天安门", "长城", "天坛", "颐和园", "圆明园", "西湖", "外滩",
        "东方明珠", "迪士尼", "兵马俑", "大雁塔", "布达拉宫", "九寨沟",
        "张家界", "黄山", "泰山", "鼓浪屿", "武夷山", "丽江古城",
        "拙政园", "虎丘", "周庄", "乌镇", "千岛湖", "灵隐寺",
        "珠江夜游", "白云山", "越秀公园", "陈家祠", "北京路",
        "小蛮腰", "海心沙", "花城广场", "沙面", "上下九",
        "夫子庙", "中山陵", "明孝陵", "玄武湖", "雨花台",
        "黄鹤楼", "东湖", "户部巷", "归元寺", "武汉大学",
    ]
    for landmark in known_landmarks:
        if landmark in free_text:
            names.add(landmark)
    return list(names)


def _get_preference_hint(state: TripPlannerState) -> str:
    preferences = state.get("user_preferences")
    if preferences:
        return "\n\n" + format_preference_hint(preferences)
    return ""


def _preferences_to_categories(preferences: List[str]) -> List[str] | None:
    rules = [
        (("历史", "文化", "博物馆", "古迹", "人文", "艺术", "美术"), "历史文化"),
        (("自然", "户外", "公园", "山", "湖", "海", "徒步"), "自然风光"),
        (("都市", "地标", "城市", "建筑"), "现代都市"),
        (("休闲", "娱乐", "游乐", "夜生活"), "休闲娱乐"),
        (("购物", "商场", "买"), "购物"),
        (("美食", "小吃", "夜市", "餐饮"), "美食街区"),
        (("亲子", "儿童", "家庭", "动物园", "乐园"), "亲子"),
        (("宗教", "寺", "庙", "教堂", "祈福", "朝圣"), "宗教"),
    ]
    categories: list[str] = []
    for preference in preferences or []:
        for keywords, category in rules:
            if any(keyword in preference for keyword in keywords) and category not in categories:
                categories.append(category)
    return categories or None


def _poi_location(poi: CachedAttraction) -> str:
    if poi.longitude is None or poi.latitude is None:
        return ""
    return f"{poi.longitude},{poi.latitude}"


def _format_pois_as_attractions_info(pois: List[CachedAttraction]) -> str:
    payload = {
        "pois": [
            {
                "id": poi.poi_id or "",
                "name": poi.name,
                "address": poi.address or "",
                "location": _poi_location(poi),
                "type": poi.amap_type or poi.category or "",
                "biz_ext": {
                    "rating": "" if poi.rating is None else str(poi.rating),
                    "cost": poi.ticket_price or "",
                    "opentime_today": poi.open_hours or "",
                    "tel": poi.tel or "",
                },
                "photos": [{"url": poi.image_url}] if poi.image_url else [],
            }
            for poi in pois
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def _poi_to_selected(poi: CachedAttraction) -> dict[str, Any]:
    return {
        "name": poi.name,
        "description": poi.description or poi.category or poi.address or "",
        "category": poi.category or "其他",
        "open_hours": poi.open_hours,
        "tel": poi.tel,
    }


async def search_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🔍 执行节点: search_attractions_node")
    request = state["request"]
    service = get_attractions_cache_service()
    categories = _preferences_to_categories(request.preferences or [])
    min_count = max(request.travel_days * 3, 15)

    try:
        pool = await service.get_attractions(city=request.city, min_count=min_count, categories=categories)

        analysis = await analyze_free_text(request.free_text_input or "")
        must_visit_names = analysis.get("attractions", []) or _extract_must_visit_attractions(request.free_text_input or "")

        must_visit_pois: list[CachedAttraction] = []
        remaining_pool = list(pool)
        for name in must_visit_names:
            existing = next((poi for poi in remaining_pool if poi.name == name or name in poi.name), None)
            if existing:
                must_visit_pois.append(existing)
                remaining_pool = [poi for poi in remaining_pool if poi.name != existing.name]
                continue

            found = await service.find_by_name(request.city, name)
            if found:
                must_visit_pois.append(found)

        combined: list[CachedAttraction] = []
        seen: set[str] = set()
        for poi in must_visit_pois + remaining_pool:
            if poi.name in seen:
                continue
            combined.append(poi)
            seen.add(poi.name)

        if not combined:
            return {
                "selected_pois": [],
                "attractions_info": "",
                "errors": ["search_attractions: 未找到可用景点"],
            }

        print(f"🔍 景点查询完成: {len(combined)} 个景点")
        return {
            "selected_pois": [_poi_to_selected(poi) for poi in combined],
            "attractions_info": _format_pois_as_attractions_info(combined),
        }
    except NonRetryableError as e:
        print(f"❌ search_attractions_node 不可重试错误: {e}")
        return {
            "selected_pois": [],
            "attractions_info": "",
            "errors": [f"search_attractions: 不可重试错误 - {str(e)[:200]}"],
        }
    except Exception as e:
        print(f"❌ search_attractions_node 异常: {e}")
        return {
            "selected_pois": [],
            "attractions_info": "",
            "errors": [f"search_attractions: 查询失败 - {str(e)[:200]}"],
        }


async def search_weather_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🌤️  执行节点: search_weather_node")
    request = state["request"]

    try:
        service = get_langchain_amap_service()
        weather_tool = await service.get_tool("maps_weather")
        if weather_tool is None:
            return {
                "weather_info": "",
                "errors": ["search_weather: maps_weather 工具不可用"],
            }
        llm = get_llm()
        llm_with_tools = llm.bind_tools([weather_tool])

        prompt = WEATHER_AGENT_PROMPT + f"\n请查询城市: {request.city} 的天气。" + _get_preference_hint(state)
        response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=WEATHER_AGENT_PROMPT), HumanMessage(content=prompt)])

        results = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                try:
                    tool_result = await _invoke_tool_with_retry(weather_tool, tool_call["args"])
                    results.append(str(tool_result))
                except NonRetryableError as e:
                    print(f"⚠️ search_weather 工具调用不可重试: {e}")
                    return {
                        "weather_info": "",
                        "errors": [f"search_weather: 工具调用不可重试 - {str(e)[:200]}"],
                    }
                except Exception as e:
                    print(f"⚠️ search_weather 工具调用失败: {e}")
                    results.append(f"[工具调用失败: {str(e)[:100]}]")

        if not results:
            print("⚠️ search_weather_node: LLM未调用工具，直接查询天气...")
            try:
                direct_result = await _invoke_tool_with_retry(
                    weather_tool,
                    {"city": request.city},
                    max_retries=2,
                    per_attempt_timeout=15.0,
                )
                results.append(str(direct_result))
                print("  ✅ 直接查询天气成功")
            except Exception as e:
                print(f"⚠️ search_weather 直接查询也失败: {e}")
                return {
                    "weather_info": "",
                    "errors": ["search_weather: LLM未调用工具且直接查询也失败"],
                }

        return {"weather_info": "\n".join(results)}
    except NonRetryableError as e:
        print(f"❌ search_weather_node 不可重试错误: {e}")
        return {
            "weather_info": "",
            "errors": [f"search_weather: 不可重试错误 - {str(e)[:200]}"],
        }
    except Exception as e:
        print(f"❌ search_weather_node 异常: {e}")
        return {
            "weather_info": "",
            "errors": [f"search_weather: 查询失败 - {str(e)[:200]}"],
        }


def _accommodation_to_star_ratings(accommodation: str) -> list:
    if "经济" in accommodation:
        return [2, 3]
    elif "舒适" in accommodation:
        return [3, 4]
    elif "豪华" in accommodation:
        return [4, 5]
    return []


async def search_hotel_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🏨 执行节点: search_hotel_node")
    request = state["request"]

    try:
        from ....services.aigohotel_mcp_service import get_aigohotel_service
        aigohotel_service = get_aigohotel_service()
        if not aigohotel_service:
            return {
                "hotels_info": "",
                "errors": ["search_hotel: AIGoHotel 服务未配置"],
            }

        try:
            await aigohotel_service.get_tools()
            search_tool = await aigohotel_service.get_tool("SearchHotels")
            if not search_tool:
                search_tool = await aigohotel_service.get_tool("find-hotels")
            if not search_tool:
                return {
                    "hotels_info": "",
                    "errors": ["search_hotel: AIGoHotel SearchHotels 工具不可用"],
                }
            print("  ✅ AIGoHotel 搜索工具已加载")
        except Exception as e:
            print(f"  ❌ AIGoHotel 初始化失败: {e}")
            return {
                "hotels_info": "",
                "errors": [f"search_hotel: AIGoHotel 初始化失败 - {str(e)[:200]}"],
            }

        llm = get_llm()
        llm_with_tools = llm.bind_tools([search_tool])

        origin_query = f"搜索{request.city}的酒店"
        if request.accommodation:
            origin_query = f"搜索{request.city}{request.accommodation}酒店"

        star_ratings = _accommodation_to_star_ratings(request.accommodation or "")

        hotel_hint = f"\n请搜索城市: {request.city}, 关键词: {request.accommodation} 酒店"
        if request.start_date:
            hotel_hint += f", 入住日期: {request.start_date}"
        if request.travel_days:
            hotel_hint += f", 住宿天数: {request.travel_days}晚"
        if star_ratings:
            hotel_hint += f", 请务必设置 starRatings={star_ratings}"
        hotel_hint += _get_preference_hint(state)

        prompt = HOTEL_AGENT_PROMPT + hotel_hint
        response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=HOTEL_AGENT_PROMPT), HumanMessage(content=prompt)])

        results = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name", "")
                try:
                    tool_result = await _invoke_tool_with_retry(search_tool, tool_call["args"])
                    results.append(str(tool_result))
                    print(f"  ✅ AIGoHotel 工具调用成功: {tool_name}")
                except NonRetryableError as e:
                    print(f"  ⚠️ AIGoHotel 工具调用不可重试: {e}")
                except Exception as e:
                    print(f"  ⚠️ AIGoHotel 工具调用失败: {e}")

        if not results:
            print("⚠️ search_hotel_node: LLM未调用工具，直接搜索...")
            try:
                aigohotel_args = {
                    "place": request.city,
                    "placeType": "城市",
                    "originQuery": origin_query,
                    "size": 5,
                    "withHotelAmenities": True,
                    "withRoomAmenities": True,
                }
                if star_ratings:
                    aigohotel_args["filterOptions"] = {"starRatings": star_ratings}
                if request.start_date:
                    aigohotel_args["checkInParam"] = {
                        "checkInDate": request.start_date,
                        "stayNights": max(request.travel_days, 1),
                    }
                direct_result = await _invoke_tool_with_retry(
                    search_tool,
                    aigohotel_args,
                    max_retries=2,
                    per_attempt_timeout=30.0,
                )
                results.append(str(direct_result))
                print("  ✅ AIGoHotel 直接搜索成功")
            except Exception as e:
                print(f"  ⚠️ AIGoHotel 直接搜索失败: {e}")

        analysis = await analyze_free_text(request.free_text_input or "")
        must_attractions = analysis.get("attractions", [])
        if must_attractions:
            print(f"🏨 搜索用户指定景点附近酒店: {must_attractions}")
            for attr_name in must_attractions[:3]:
                try:
                    nearby_args = {
                        "place": attr_name,
                        "placeType": "景点",
                        "originQuery": f"搜索{attr_name}附近的酒店",
                        "size": 3,
                        "withHotelAmenities": True,
                        "withRoomAmenities": True,
                    }
                    if star_ratings:
                        nearby_args["starRatings"] = star_ratings
                    if request.start_date:
                        nearby_args["checkIn"] = request.start_date
                    if request.travel_days:
                        nearby_args["stayNights"] = request.travel_days
                    nearby_result = await _invoke_tool_with_retry(
                        search_tool,
                        nearby_args,
                        max_retries=2,
                        per_attempt_timeout=30.0,
                    )
                    results.append(str(nearby_result))
                    print(f"  ✅ 搜索到{attr_name}附近酒店")
                except Exception as e:
                    print(f"  ⚠️ 搜索{attr_name}附近酒店失败: {e}")

        if not results:
            return {
                "hotels_info": "",
                "errors": ["search_hotel: 酒店搜索无结果"],
            }

        hotels_info = "\n".join(results)
        print(f"🏨 酒店搜索完成: AIGoHotel {len(results)}条结果")
        return {
            "hotels_info": hotels_info,
            "aigohotel_raw_results": hotels_info,
        }
    except NonRetryableError as e:
        print(f"❌ search_hotel_node 不可重试错误: {e}")
        return {
            "hotels_info": "",
            "errors": [f"search_hotel: 不可重试错误 - {str(e)[:200]}"],
        }
    except Exception as e:
        print(f"❌ search_hotel_node 异常: {e}")
        return {
            "hotels_info": "",
            "errors": [f"search_hotel: 搜索失败 - {str(e)[:200]}"],
        }


async def gather_search_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🔗 执行节点: gather_search_node (搜索结果汇总)")
    errors = state.get("errors", [])
    attractions = state.get("attractions_info", "")
    weather = state.get("weather_info", "")
    hotels = state.get("hotels_info", "")

    if not attractions:
        print("⚠️ gather_search: 景点搜索结果为空")
    if not weather:
        print("⚠️ gather_search: 天气查询结果为空")
    if not hotels:
        print("⚠️ gather_search: 酒店搜索结果为空")

    if errors:
        print(f"🚨 gather_search: 汇总时检测到 {len(errors)} 个错误")
        for err in errors[-5:]:
            print(f"   - {err[:200]}")

    return {}


def _unwrap_mcp_payload(raw: Any) -> Any:
    """剥离 MCP 工具返回的多层包裹（text wrapper → JSON 字符串 → dict）。"""
    import ast
    data = raw
    for _ in range(4):
        if isinstance(data, str):
            stripped = data.strip()
            if not stripped:
                return data
            try:
                data = json.loads(stripped)
                continue
            except (json.JSONDecodeError, TypeError):
                try:
                    data = ast.literal_eval(stripped)
                    continue
                except (ValueError, SyntaxError):
                    return data
        if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
            inner = data[0]["text"]
            if isinstance(inner, str):
                data = inner
                continue
            data = inner
            continue
        break
    return data


def _parse_aigohotel_hotels(raw: Any) -> List[Dict[str, Any]]:
    """从 AIGoHotel SearchHotels 返回中尽力提取酒店字段，输出 Hotel 兼容 dict 列表。"""
    data = _unwrap_mcp_payload(raw)
    hotels_raw: List[Any] = []
    if isinstance(data, dict):
        for key in ("hotels", "data", "result", "results", "items"):
            val = data.get(key)
            if isinstance(val, list) and val:
                hotels_raw = val
                break
            if isinstance(val, dict):
                inner = val.get("hotels") or val.get("items") or val.get("list")
                if isinstance(inner, list):
                    hotels_raw = inner
                    break
        if not hotels_raw:
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    hotels_raw = v
                    break
    elif isinstance(data, list):
        hotels_raw = data

    parsed: List[Dict[str, Any]] = []
    for h in hotels_raw:
        if not isinstance(h, dict):
            continue
        name = h.get("name") or h.get("hotelName") or h.get("title") or h.get("hotel_name")
        if not name:
            continue
        item: Dict[str, Any] = {"name": str(name)}

        address = h.get("address") or h.get("addr") or h.get("location_desc")
        if address:
            item["address"] = str(address)

        lon = lat = None
        loc = h.get("location") or h.get("position") or h.get("coordinate") or h.get("coordinates")
        if isinstance(loc, dict):
            lon = loc.get("longitude") or loc.get("lng") or loc.get("lon")
            lat = loc.get("latitude") or loc.get("lat")
        elif isinstance(loc, str) and "," in loc:
            parts = loc.split(",")
            if len(parts) >= 2:
                lon, lat = parts[0], parts[1]
        if lon is None:
            lon = h.get("longitude") or h.get("lng") or h.get("lon")
            lat = h.get("latitude") or h.get("lat")
        if lon is not None and lat is not None:
            try:
                lon_f = float(lon)
                lat_f = float(lat)
                if 73 < lon_f < 136 and 3 < lat_f < 54:
                    item["location"] = {"longitude": lon_f, "latitude": lat_f}
            except (TypeError, ValueError):
                pass

        star = h.get("starRating") or h.get("star") or h.get("stars") or h.get("star_rating")
        if star is not None:
            try:
                item["star_rating"] = float(star)
            except (TypeError, ValueError):
                pass

        hotel_id = h.get("hotelId") or h.get("hotel_id") or h.get("id")
        if hotel_id is not None:
            item["hotel_id"] = hotel_id

        price_obj = h.get("price")
        if isinstance(price_obj, dict):
            current_price = price_obj.get("lowestPrice") or price_obj.get("price")
            if price_obj.get("hasPrice", current_price is not None) and current_price is not None:
                try:
                    item["price"] = float(current_price)
                except (TypeError, ValueError):
                    pass
            currency = price_obj.get("currency")
            if currency:
                item["currency"] = str(currency)

        for src_key, dst_key in (("price", "price"), ("totalPrice", "price"), ("originalPrice", "original_price")):
            v = h.get(src_key)
            if isinstance(v, dict):
                continue
            if v is not None and dst_key not in item:
                try:
                    item[dst_key] = float(v)
                except (TypeError, ValueError):
                    pass

        item.setdefault("currency", str(h.get("currency") or "CNY"))

        ham = h.get("hotelAmenities") or h.get("hotel_amenities") or h.get("amenities")
        if isinstance(ham, list):
            item["hotel_amenities"] = [str(a) for a in ham if a]
        ram = h.get("roomAmenities") or h.get("room_amenities")
        if isinstance(ram, list):
            item["room_amenities"] = [str(a) for a in ram if a]

        desc = h.get("description") or h.get("intro") or h.get("summary")
        if desc:
            cleaned_desc = _clean_hotel_description(desc)
            if cleaned_desc:
                item["description"] = cleaned_desc[:500]

        img = h.get("imageUrl") or h.get("image") or h.get("photo") or h.get("mainImage")
        if img:
            item["image_url"] = str(img)
        durl = h.get("bookingUrl") or h.get("detailUrl") or h.get("url") or h.get("link")
        if durl:
            item["detail_url"] = str(durl)

        dim = h.get("distanceInMeter") or h.get("distanceInMeters") or h.get("distance_in_meters")
        if dim is not None:
            try:
                item["distance_in_meters"] = int(float(dim))
            except (TypeError, ValueError):
                pass

        rating = h.get("rating") or h.get("score") or h.get("commentScore") or h.get("comment_score")
        if rating is not None:
            item["rating"] = str(rating)

        hotel_type = h.get("type") or h.get("hotelType") or h.get("category")
        if hotel_type:
            item["type"] = str(hotel_type)

        if "price" in item and item.get("price"):
            try:
                item["estimated_cost"] = int(float(item["price"]))
            except (TypeError, ValueError):
                pass
        if "estimated_cost" not in item:
            star = item.get("star_rating")
            if star and star > 0:
                item["estimated_cost"] = int(star * 200)
            else:
                item["estimated_cost"] = 500

        parsed.append(item)
    return parsed


def _cluster_centroid(cluster: List[Dict[str, Any]]) -> tuple[float, float] | None:
    """计算聚类质心 (lon, lat)，无坐标返回 None。"""
    coords = [(c.get("longitude"), c.get("latitude")) for c in cluster if c.get("longitude") and c.get("latitude")]
    if not coords:
        return None
    avg_lon = sum(lon for lon, _ in coords) / len(coords)
    avg_lat = sum(lat for _, lat in coords) / len(coords)
    return avg_lon, avg_lat


def _cluster_outer_radius_km(cluster: List[Dict[str, Any]], centroid: tuple[float, float]) -> float:
    from ..utils.geo import _haversine_distance
    lon_c, lat_c = centroid
    max_d = 0.0
    for c in cluster:
        if c.get("longitude") and c.get("latitude"):
            d = _haversine_distance(lat_c, lon_c, c["latitude"], c["longitude"])
            max_d = max(max_d, d)
    return max_d


def _enrich_hotels_with_distance(hotels: List[Dict[str, Any]], centroid: tuple[float, float]) -> None:
    """给每家酒店补上"到当日质心"的真实距离（如果有坐标）。"""
    from ..utils.geo import _haversine_distance
    lon_c, lat_c = centroid
    for h in hotels:
        loc = h.get("location")
        if isinstance(loc, dict) and loc.get("longitude") and loc.get("latitude"):
            d_km = _haversine_distance(lat_c, lon_c, loc["latitude"], loc["longitude"])
            h["_centroid_distance_km"] = d_km
            h["distance_in_meters"] = int(d_km * 1000)
            h["distance"] = f"距当日中心 {d_km:.1f} 公里"


def _rank_day_hotels(hotels: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """按 (有星级, 星级 desc, 距离 asc) 排序，去重保留 top_n。"""
    def sort_key(h: Dict[str, Any]):
        star = h.get("star_rating")
        dist = h.get("_centroid_distance_km", 999.0)
        return (
            0 if star is not None else 1,
            -(star or 0),
            dist,
        )
    seen_names: set[str] = set()
    deduped = []
    for h in sorted(hotels, key=sort_key):
        name = h.get("name", "").strip()
        if name and name not in seen_names:
            seen_names.add(name)
            deduped.append(h)
    return deduped[:top_n]


def _format_hotels_by_day_text(hotels_by_day: List[List[Dict[str, Any]]]) -> str:
    """把酒店候选格式化为给 macro_planner 看的文本。

    所有天共享同一份候选时（行程级搜索的常态），只打印一次，避免重复噪声。
    """
    if not hotels_by_day:
        return ""

    def _names_sig(day_hotels: List[Dict[str, Any]]) -> tuple:
        return tuple(h.get("name", "") for h in day_hotels)

    sigs = {_names_sig(d) for d in hotels_by_day}
    shared = len(sigs) == 1 and hotels_by_day[0]

    lines: List[str] = []

    def _format_one_block(day_hotels: List[Dict[str, Any]], header: str) -> None:
        lines.append(header)
        if not day_hotels:
            lines.append("  （无候选）")
            return
        for j, h in enumerate(day_hotels, 1):
            star = h.get("star_rating")
            price = h.get("price")
            dist = h.get("distance") or ""
            addr = h.get("address") or ""
            loc = h.get("location") or {}
            loc_str = ""
            if isinstance(loc, dict) and loc.get("longitude"):
                loc_str = f" 坐标({loc['longitude']:.5f},{loc['latitude']:.5f})"
            parts = [f"  {j}. {h['name']}"]
            if star is not None:
                parts.append(f"{star}星")
            if price is not None:
                parts.append(f"¥{int(price)}")
            if dist:
                parts.append(dist)
            if addr:
                parts.append(addr)
            lines.append(" | ".join(parts) + loc_str)

    if shared:
        _format_one_block(hotels_by_day[0], f"=== 候选酒店（全程 {len(hotels_by_day)} 天共用同一份候选） ===")
    else:
        for i, day_hotels in enumerate(hotels_by_day):
            _format_one_block(day_hotels, f"=== 第{i + 1}天候选酒店 ===")
    return "\n".join(lines)


async def _aigohotel_search_for_day(
    search_tool: Any,
    rep_name: str,
    city: str,
    accommodation: str,
    centroid: tuple[float, float],
    radius_km: float,
    star_ratings: List[int],
    check_in: str | None,
) -> List[Dict[str, Any]]:
    """对单日聚类调一次 AIGoHotel SearchHotels（景点级），返回已解析+距离增强的酒店列表。"""
    distance_m = int(max(radius_km + 2.0, 2.0) * 1000)
    distance_m = min(distance_m, 20000)
    args: Dict[str, Any] = {
        "place": rep_name,
        "placeType": "景点",
        "originQuery": f"搜索{city}{rep_name}附近的{accommodation or ''}酒店".strip(),
        "size": 8,
        "withHotelAmenities": True,
        "withRoomAmenities": True,
        "filterOptions": {"distanceInMeter": distance_m},
    }
    if star_ratings:
        args["filterOptions"]["starRatings"] = star_ratings
    if check_in:
        args["checkInParam"] = {"checkInDate": check_in, "stayNights": 1}

    try:
        raw = await _invoke_tool_with_retry(search_tool, args, max_retries=1, per_attempt_timeout=30.0)
    except Exception as e:
        print(f"  ⚠️ AIGoHotel 景点搜索失败 [{rep_name}]: {str(e)[:120]}")
        return []

    hotels = _parse_aigohotel_hotels(raw)
    _enrich_hotels_with_distance(hotels, centroid)
    return hotels


async def _aigohotel_city_fallback(
    search_tool: Any,
    city: str,
    accommodation: str,
    star_ratings: List[int],
    check_in: str | None,
    stay_nights: int,
) -> List[Dict[str, Any]]:
    """城市级兜底搜索，用于当日聚类无坐标或景点搜索失败时。"""
    args: Dict[str, Any] = {
        "place": city,
        "placeType": "城市",
        "originQuery": f"搜索{city}{accommodation or ''}酒店".strip(),
        "size": 8,
        "withHotelAmenities": True,
        "withRoomAmenities": True,
    }
    if star_ratings:
        args["filterOptions"] = {"starRatings": star_ratings}
    if check_in:
        args["checkInParam"] = {"checkInDate": check_in, "stayNights": stay_nights}

    try:
        raw = await _invoke_tool_with_retry(search_tool, args, max_retries=2, per_attempt_timeout=30.0)
    except Exception as e:
        print(f"  ⚠️ AIGoHotel 城市级兜底失败 [{city}]: {str(e)[:120]}")
        return []
    return _parse_aigohotel_hotels(raw)



async def search_hotels_by_day_node(state: TripPlannerState) -> Dict[str, Any]:
    """为整段行程搜索一次酒店，写入 hotels_by_day + hotels_info。

    同一城市多天行程通常入住同一家酒店，因此：
    1. 计算所有聚类的"行程质心"
    2. 以行程质心附近代表景点调一次 AIGoHotel（placeType=景点）
    3. 城市级兜底（placeType=城市）
    4. 同一份候选列表分发给所有天，让 macro_planner 自然选同一家
    """
    print("🏨 执行节点: search_hotels_by_day_node (行程级)")
    request = state["request"]
    clusters: List[List[Dict[str, Any]]] = state.get("clusters_data") or []
    travel_days = request.travel_days

    from ....services.aigohotel_mcp_service import get_aigohotel_service
    aigohotel_service = get_aigohotel_service()
    if not aigohotel_service:
        return {
            "hotels_info": "",
            "hotels_by_day": [[] for _ in range(travel_days)],
            "errors": ["search_hotels_by_day: AIGoHotel 服务未配置"],
        }

    try:
        await aigohotel_service.get_tools()
        search_tool = await aigohotel_service.get_tool("SearchHotels")
        if not search_tool:
            search_tool = await aigohotel_service.get_tool("find-hotels")
        if not search_tool:
            return {
                "hotels_info": "",
                "hotels_by_day": [[] for _ in range(travel_days)],
                "errors": ["search_hotels_by_day: SearchHotels 工具不可用"],
            }
    except Exception as e:
        return {
            "hotels_info": "",
            "hotels_by_day": [[] for _ in range(travel_days)],
            "errors": [f"search_hotels_by_day: AIGoHotel 初始化失败 - {str(e)[:200]}"],
        }

    accommodation = request.accommodation or ""
    star_ratings = _accommodation_to_star_ratings(accommodation)

    # 计算行程质心：所有聚类所有景点坐标的均值
    all_coords: List[Dict[str, Any]] = []
    for cluster in clusters:
        all_coords.extend(cluster)

    trip_centroid = _cluster_centroid(all_coords) if all_coords else None

    ranked: List[Dict[str, Any]] = []

    if trip_centroid and all_coords:
        # 找到离质心最近的景点作为搜索锚点
        from ..utils.geo import _haversine_distance
        best_poi = min(
            all_coords,
            key=lambda p: _haversine_distance(trip_centroid[1], trip_centroid[0], p.get("latitude", 0), p.get("longitude", 0)) if p.get("longitude") and p.get("latitude") else 999,
        )
        rep_name = best_poi.get("name", request.city)

        # 搜索半径：覆盖最远聚类 + 2km 余量
        max_radius_km = _cluster_outer_radius_km(all_coords, trip_centroid) if all_coords else 5.0
        distance_m = int(max(max_radius_km + 2.0, 3.0) * 1000)
        distance_m = min(distance_m, 20000)

        print(f" 🔎 行程质心: ({trip_centroid[0]:.4f}, {trip_centroid[1]:.4f}), 锚点景点: '{rep_name}', 搜索半径: {distance_m}m")

        hotels = await _aigohotel_search_for_day(
            search_tool, rep_name, request.city, accommodation,
            trip_centroid, max_radius_km, star_ratings,
            request.start_date,
        )
        if hotels:
            _enrich_hotels_with_distance(hotels, trip_centroid)
            ranked = _rank_day_hotels(hotels, top_n=5)

    # 降级：景点级搜索无结果 -> 城市级兜底
    if not ranked:
        print(" ⚠️ 景点级搜索无结果，使用城市级兜底")
        city_hotels = await _aigohotel_city_fallback(
            search_tool, request.city, accommodation, star_ratings,
            request.start_date, max(travel_days, 1),
        )
        if city_hotels and trip_centroid:
            _enrich_hotels_with_distance(city_hotels, trip_centroid)
        ranked = _rank_day_hotels(city_hotels, top_n=5) if city_hotels else []

    # 同一份候选分发给所有天
    hotels_by_day = [ranked for _ in range(travel_days)]
    hotels_info = _format_hotels_by_day_text(hotels_by_day)
    print(f"✅ 行程级酒店搜索完成: {len(ranked)} 家候选, 分配给 {travel_days} 天")

    return {
        "hotels_info": hotels_info,
        "hotels_by_day": hotels_by_day,
        "aigohotel_raw_results": hotels_info,
    }

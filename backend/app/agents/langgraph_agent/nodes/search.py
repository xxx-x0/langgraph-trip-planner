import re
import json
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from ..exceptions import _invoke_llm_with_retry, _invoke_tool_with_retry, NonRetryableError
from ..prompts import WEB_SEARCH_ATTRACTION_PROMPT, EXTRACT_ATTRACTIONS_PROMPT, WEATHER_AGENT_PROMPT, HOTEL_AGENT_PROMPT
from ..state import TripPlannerState
from ..utils.parsing import _extract_poi_names
from ....services.langchain_amap_tools import get_langchain_amap_service
from ....services.llm_service import get_llm
from ....services.preferences_service import format_preference_hint

_DDG_AVAILABLE = False
try:
    from langchain_community.tools import DuckDuckGoSearchResults
    _DDG_AVAILABLE = True
except ImportError:
    print("⚠️ duckduckgo-search 未安装，景点搜索将降级使用高德API。请运行: pip install duckduckgo-search")

_BING_AVAILABLE = False
try:
    from ....services.bing_mcp_service import get_bing_service
    _BING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 必应 MCP 服务导入失败: {e}")


class FreeTextAnalysis(BaseModel):
    attractions: List[str] = Field(default_factory=list, description="用户指定的景点名称")
    food_preferences: List[str] = Field(default_factory=list, description="用户提到的美食/餐饮偏好")
    accommodation_preferences: List[str] = Field(default_factory=list, description="用户提到的住宿偏好")
    general_suggestions: List[str] = Field(default_factory=list, description="用户的非具体意见或建议")


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
        r'想去(.+)',
        r'一定要去(.+)',
        r'必须去(.+)',
        r'特别想去(.+)',
        r'希望去(.+)',
        r'想要去(.+)',
    ]
    for pattern in trigger_patterns:
        matches = re.findall(pattern, free_text)
        for match in matches:
            parts = re.split(r'[，,、；;和还有以及\s]+', match)
            for name in parts:
                name = name.strip().rstrip('。.！!？?')
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


async def web_search_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🔍 执行节点: web_search_attractions_node")
    request = state["request"]
    city = request.city
    preferences = request.preferences or []
    companions = request.companions
    budget = request.budget

    if not _DDG_AVAILABLE:
        print("⚠️ DuckDuckGo不可用，降级使用高德搜索景点")
        try:
            service = get_langchain_amap_service()
            search_tool = await service.get_tool("maps_text_search")
            if search_tool:
                keywords = preferences[0] if preferences else "景点"
                fallback_result = await _invoke_tool_with_retry(
                    search_tool,
                    {"keywords": keywords, "city": city},
                    max_retries=2,
                    per_attempt_timeout=15.0,
                )
                return {
                    "raw_search_results": "",
                    "attractions_info": str(fallback_result),
                }
        except Exception as e:
            print(f"⚠️ 降级高德搜索也失败: {e}")
        return {
            "raw_search_results": "",
            "errors": ["web_search_attractions: DuckDuckGo不可用且降级搜索失败"],
        }

    try:
        travel_days = request.travel_days
        search_queries = []

        search_queries.extend([
            f"{city} 必去景点 top10",
            f"{city} 旅游攻略 必去",
            f"{city} 最值得去的景点",
        ])

        if travel_days >= 3:
            search_queries.extend([
                f"{city} 十大景点",
                f"{city} 旅游景点推荐",
            ])

        if travel_days >= 5:
            search_queries.extend([
                f"{city} 冷门景点 小众",
                f"{city} 周边景点推荐",
            ])

        if preferences:
            companion_label = ""
            if companions:
                companion_map = {
                    "solo": "一个人",
                    "couple": "情侣",
                    "family": "亲子",
                    "friends": "朋友",
                    "elderly": "老人",
                    "group": "团队",
                }
                companion_label = companion_map.get(companions.type, "")

            for pref in preferences[:3]:
                if companion_label:
                    search_queries.append(f"{city} {pref} {companion_label} 景点推荐")
                search_queries.append(f"{city} {pref} 必去景点")
                search_queries.append(f"{city} {pref} 旅游攻略")

        if budget is not None and budget < 3000:
            search_queries.append(f"{city} 免费景点")
            search_queries.append(f"{city} 低价景点推荐")

        analysis = await analyze_free_text(request.free_text_input or "")
        must_visit = analysis.get("attractions", [])
        if must_visit:
            for name in must_visit[:3]:
                search_queries.append(f"{name} {city} 旅游攻略")

        all_results = []

        # 1. 必应 MCP 搜索 (优先)
        bing_service = get_bing_service() if _BING_AVAILABLE else None
        bing_success_count = 0
        if bing_service:
            print("  🔍 尝试使用必应 MCP 搜索...")
            for query in search_queries[:6]:
                try:
                    result = await bing_service.search(query=query, count=5)
                    result_str = str(result) if not isinstance(result, str) else result
                    if result_str and len(result_str) > 20:
                        all_results.append(f"=== [必应] 搜索词: {query} ===\n{result_str}")
                        bing_success_count += 1
                        print(f"  ✅ 必应搜索成功: {query}")
                except Exception as e:
                    print(f"  ⚠️ 必应搜索失败({query}): {e}")
            if bing_success_count > 0:
                print(f"  ✅ 必应 MCP 共获取 {bing_success_count} 条结果")
        else:
            print("  ⚠️ 必应 MCP 未配置或导入失败，跳过")

        # 2. DuckDuckGo 搜索 (补充)
        ddg_success_count = 0
        if _DDG_AVAILABLE:
            print("  🔍 尝试使用 DuckDuckGo 搜索补充...")
            ddg_tool = DuckDuckGoSearchResults(max_results=5)
            for query in search_queries[:6]:
                try:
                    result = await _invoke_tool_with_retry(
                        ddg_tool,
                        {"query": query},
                        max_retries=1,
                        per_attempt_timeout=15.0,
                    )
                    result_str = str(result)
                    if result_str and len(result_str) > 20:
                        all_results.append(f"=== [DuckDuckGo] 搜索词: {query} ===\n{result_str}")
                        ddg_success_count += 1
                        print(f"  ✅ DuckDuckGo搜索成功: {query}")
                except Exception as e:
                    print(f"  ⚠️ DuckDuckGo搜索失败({query}): {e}")
            print(f"  ✅ DuckDuckGo 共获取 {ddg_success_count} 条结果")
        else:
            print("  ⚠️ DuckDuckGo 未安装，跳过")

        if not all_results:
            return {
                "raw_search_results": "",
                "errors": ["web_search_attractions: 所有搜索引擎均无结果"],
            }

        raw_results = "\n\n".join(all_results)
        print(f"🔍 搜索完成: 必应{bing_success_count}条, DuckDuckGo{ddg_success_count}条, 共{len(all_results)}条结果")
        return {"raw_search_results": raw_results}
    except NonRetryableError as e:
        print(f"❌ web_search_attractions_node 不可重试错误: {e}")
        return {
            "raw_search_results": "",
            "errors": [f"web_search_attractions: 不可重试错误 - {str(e)[:200]}"],
        }
    except Exception as e:
        print(f"❌ web_search_attractions_node 异常: {e}")
        return {
            "raw_search_results": "",
            "errors": [f"web_search_attractions: 搜索失败 - {str(e)[:200]}"],
        }


async def extract_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🧠 执行节点: extract_attractions_node")
    raw_results = state.get("raw_search_results", "")
    request = state["request"]

    if not raw_results:
        print("⚠️ extract_attractions: 搜索结果为空，降级到高德搜索")
        try:
            service = get_langchain_amap_service()
            search_tool = await service.get_tool("maps_text_search")
            if search_tool:
                keywords = request.preferences[0] if request.preferences else "景点"
                fallback_result = await _invoke_tool_with_retry(
                    search_tool,
                    {"keywords": keywords, "city": request.city},
                    max_retries=2,
                    per_attempt_timeout=15.0,
                )
                return {
                    "selected_pois": [],
                    "attractions_info": str(fallback_result),
                }
        except Exception as e:
            print(f"⚠️ 降级高德搜索也失败: {e}")
        return {
            "selected_pois": [],
            "errors": ["extract_attractions: 搜索结果为空且降级搜索失败"],
        }

    try:
        llm = get_llm()
        travel_days = request.travel_days
        max_count = travel_days * 3
        preferences = request.preferences or []
        pref_hint = f"\n用户偏好: {', '.join(preferences)}" if preferences else "\n用户无特殊偏好（按通用景点提取）"

        prompt = f"旅行天数: {travel_days}天，最多提取{max_count}个景点（但只提取搜索结果中明确提到的，不要凑数）。{pref_hint}\n\n以下是搜索结果:\n{raw_results[:15000]}"
        response = await _invoke_llm_with_retry(
            llm,
            [SystemMessage(content=EXTRACT_ATTRACTIONS_PROMPT), HumanMessage(content=prompt)],
            max_retries=2,
            per_attempt_timeout=30.0,
        )

        content = response.content.strip()
        pois = []

        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "[" in content:
            json_start = content.find("[")
            json_end = content.rfind("]") + 1
            json_str = content[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON")

        pois = json.loads(json_str)
        if not isinstance(pois, list):
            pois = []

        valid_pois = []
        for poi in pois:
            if isinstance(poi, dict) and poi.get("name"):
                valid_pois.append({
                    "name": poi["name"],
                    "description": poi.get("description", ""),
                })

        if not valid_pois:
            print("⚠️ extract_attractions: LLM未提取到有效景点，降级到高德搜索")
            try:
                service = get_langchain_amap_service()
                search_tool = await service.get_tool("maps_text_search")
                if search_tool:
                    keywords = request.preferences[0] if request.preferences else "景点"
                    fallback_result = await _invoke_tool_with_retry(
                        search_tool,
                        {"keywords": keywords, "city": request.city},
                        max_retries=2,
                        per_attempt_timeout=15.0,
                    )
                    return {
                        "selected_pois": [],
                        "attractions_info": str(fallback_result),
                    }
            except Exception as e:
                print(f"⚠️ 降级高德搜索也失败: {e}")

        print(f"🧠 LLM提取到 {len(valid_pois)} 个核心景点: {[p['name'] for p in valid_pois]}")

        # 自动补充：如果提取到的景点数量不足，用高德搜索补充
        min_attractions = travel_days * 2
        if len(valid_pois) < min_attractions:
            print(f"⚠️ 景点数量不足({len(valid_pois)} < {min_attractions})，尝试用高德搜索补充...")
            try:
                service = get_langchain_amap_service()
                search_tool = await service.get_tool("maps_text_search")
                if search_tool:
                    keywords = request.preferences[0] if request.preferences else "景点"
                    fallback_result = await _invoke_tool_with_retry(
                        search_tool,
                        {"keywords": keywords, "city": request.city},
                        max_retries=2,
                        per_attempt_timeout=15.0,
                    )
                    fallback_str = str(fallback_result)
                    from ..utils.parsing import _extract_poi_names
                    extra_pois = _extract_poi_names(fallback_str)
                    existing_names = {p["name"] for p in valid_pois}
                    added = 0
                    for poi in extra_pois:
                        if poi.get("name") and poi["name"] not in existing_names:
                            valid_pois.append({
                                "name": poi["name"],
                                "description": poi.get("address", "") or "高德推荐景点",
                            })
                            existing_names.add(poi["name"])
                            added += 1
                            if len(valid_pois) >= min_attractions:
                                break
                    if added > 0:
                        print(f"  ✅ 高德补充了 {added} 个景点，现在共 {len(valid_pois)} 个")
            except Exception as e:
                print(f"  ⚠️ 高德补充搜索失败: {e}")

        return {"selected_pois": valid_pois}
    except NonRetryableError as e:
        print(f"❌ extract_attractions_node 不可重试错误: {e}")
        return {
            "selected_pois": [],
            "errors": [f"extract_attractions: 不可重试错误 - {str(e)[:200]}"],
        }
    except Exception as e:
        print(f"❌ extract_attractions_node 异常: {e}")
        return {
            "selected_pois": [],
            "errors": [f"extract_attractions: 提取失败 - {str(e)[:200]}"],
        }


async def geocode_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    print("📍 执行节点: geocode_attractions_node")
    selected_pois = state.get("selected_pois", [])
    request = state["request"]

    if state.get("attractions_info"):
        print("  ⏭️ 已有attractions_info（降级搜索结果），跳过地理编码")
        return {}

    if not selected_pois:
        return {
            "attractions_info": "",
            "errors": ["geocode_attractions: 无景点需要地理编码"],
        }

    try:
        service = get_langchain_amap_service()
        search_tool = await service.get_tool("maps_text_search")
        detail_tool = await service.get_tool("maps_search_detail")

        results = []
        failed_pois = []

        for poi in selected_pois:
            name = poi["name"]
            found = False

            for attempt_name in [name, re.sub(r'(风景名胜区|风景区|景区|旅游区|度假区|步行街|商业街)$', '', name)]:
                if not attempt_name or (attempt_name == name and found):
                    continue
                try:
                    search_result = await _invoke_tool_with_retry(
                        search_tool,
                        {"keywords": attempt_name, "city": request.city},
                        max_retries=2,
                        per_attempt_timeout=15.0,
                    )
                    result_str = str(search_result)
                    poi_list = _extract_poi_names(result_str)

                    if poi_list:
                        best_poi = poi_list[0]
                        if detail_tool and best_poi.get("id"):
                            try:
                                detail_result = await _invoke_tool_with_retry(
                                    detail_tool,
                                    {"id": best_poi["id"]},
                                    max_retries=1,
                                    per_attempt_timeout=10.0,
                                )
                                detail_str = str(detail_result)
                                if len(detail_str) > 20:
                                    results.append(detail_str)
                                    print(f"  ✅ maps_search_detail获取坐标: {name} (id={best_poi['id']})")
                                    found = True
                                    break
                            except Exception as e:
                                print(f"  ⚠️ maps_search_detail失败({name}): {e}")

                        results.append(result_str)
                        print(f"  ✅ 高德搜索到景点: {name}")
                        found = True
                        break
                    elif len(result_str) > 20 and "没有找到" not in result_str:
                        results.append(result_str)
                        print(f"  ✅ 高德搜索到景点(未解析POI): {name}")
                        found = True
                        break
                except Exception as e:
                    print(f"  ⚠️ 搜索景点{attempt_name}失败: {e}")

            if not found:
                failed_pois.append(name)

        if failed_pois:
            print(f"⚠️ 以下景点未在高德中找到: {failed_pois}")

        if not results:
            return {
                "attractions_info": "",
                "errors": ["geocode_attractions: 所有景点高德搜索失败"],
            }

        attractions_info = "\n".join(results)
        print(f"📍 高德搜索完成: {len(results)}/{len(selected_pois)} 个景点成功搜索到")
        return {"attractions_info": attractions_info}
    except NonRetryableError as e:
        print(f"❌ geocode_attractions_node 不可重试错误: {e}")
        return {
            "attractions_info": "",
            "errors": [f"geocode_attractions: 不可重试错误 - {str(e)[:200]}"],
        }
    except Exception as e:
        print(f"❌ geocode_attractions_node 异常: {e}")
        return {
            "attractions_info": "",
            "errors": [f"geocode_attractions: 地理编码失败 - {str(e)[:200]}"],
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
                print(f"  ✅ 直接查询天气成功")
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
                    aigohotel_args["starRatings"] = star_ratings
                if request.start_date:
                    aigohotel_args["checkIn"] = request.start_date
                if request.travel_days:
                    aigohotel_args["stayNights"] = request.travel_days
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
